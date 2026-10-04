from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import sentry_sdk

from app.models import (
    Business,
    CustomerRequest,
    IngredientNeed,
    KitchenPlan,
    KitchenPlanItem,
    OrderStatus,
    PlanStatus,
    PlanWarning,
    Product,
    utc_now,
)
from app.repository import Repository
from app.services.demand import DemandService
from app.services.forecasting import is_usually_closed, same_weekday

ALLOWED_TRANSITIONS: dict[PlanStatus, set[PlanStatus]] = {
    PlanStatus.DRAFT: {PlanStatus.APPROVED, PlanStatus.REJECTED, PlanStatus.MODIFIED},
    PlanStatus.MODIFIED: {PlanStatus.APPROVED, PlanStatus.REJECTED, PlanStatus.MODIFIED},
    PlanStatus.APPROVED: set(),
    PlanStatus.REJECTED: set(),
}
OPEN_STATUSES = {PlanStatus.DRAFT, PlanStatus.MODIFIED}
PREORDER_STATUSES = {OrderStatus.PENDING, OrderStatus.CONFIRMED}
LOW_CONFIDENCE = 0.7
HIGH_VARIABILITY_CV = 0.35
STALE_AFTER_DAYS = 7


class PlanNotFound(LookupError):
    pass


class InvalidTransition(ValueError):
    pass


class PlanConflict(ValueError):
    pass


def transition(plan: KitchenPlan, to: PlanStatus) -> None:
    if to not in ALLOWED_TRANSITIONS[plan.status]:
        raise InvalidTransition(
            f"This plan is {plan.status.value} and can no longer be {to.value}."
        )
    plan.status = to
    plan.reviewed_at = utc_now()
    if to == PlanStatus.APPROVED:
        plan.approved_at = plan.reviewed_at


def ingredient_needs(items: list[KitchenPlanItem], products: dict[str, Product]) -> list:
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for item in items:
        product = products.get(item.product_id)
        if not product:
            continue
        for req in product.ingredient_requirements:
            totals[(req.ingredient, req.unit)] += req.quantity * item.final_quantity
    return [
        IngredientNeed(ingredient=ing, unit=unit, quantity=round(qty, 3))
        for (ing, unit), qty in sorted(totals.items())
        if qty > 0
    ]


def _fmt(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


class PlanningService:
    def __init__(self, repo: Repository, business: Business, demand: DemandService):
        self.repo = repo
        self.business = business
        self.demand = demand

    def get(self, plan_id: str) -> KitchenPlan:
        plan = self.repo.get_plan(plan_id)
        if plan is None or plan.business_id != self.business.id:
            raise PlanNotFound(plan_id)
        return plan

    def generate(self, target: date, today: date) -> KitchenPlan:
        with sentry_sdk.start_span(
            op="secondo.plan.generate", name="Generate kitchen plan"
        ) as span:
            plan = self._generate(target, today)
            span.set_data("secondo.plan.target_date", target.isoformat())
            span.set_data("secondo.plan.model", plan.model_name)
            span.set_data("secondo.plan.items", len(plan.items))
            span.set_data("secondo.plan.warnings", len(plan.warnings))
            return plan

    def _generate(self, target: date, today: date) -> KitchenPlan:
        existing = [p for p in self.repo.list_plans(self.business.id) if p.target_date == target]
        if any(p.status == PlanStatus.APPROVED for p in existing):
            raise PlanConflict(
                f"A plan for {target.isoformat()} is already approved. Approved plans are kept "
                "as a record and cannot be regenerated."
            )
        reusable = next((p for p in existing if p.status in OPEN_STATUSES), None)

        products = {p.id: p for p in self.repo.list_products(self.business.id) if p.active}
        history = self.demand.history(today)
        forecasts = {f.product_id: f for f in self.demand.forecast(target, today)}
        closed = is_usually_closed(history, target)
        weekday = target.strftime("%A")

        target_orders = [
            o
            for o in self.repo.list_orders(self.business.id, start=target, end=target)
            if o.status in PREORDER_STATUSES
        ]
        confirmed: dict[str, int] = defaultdict(int)
        for o in target_orders:
            confirmed[o.product_id] += o.quantity

        warnings: list[PlanWarning] = []
        items: list[KitchenPlanItem] = []
        for pid, product in products.items():
            f = forecasts.get(pid)
            predicted = f.predicted_quantity if f else 0.0
            baseline = f.baseline_quantity if f else 0.0
            mae = f.evaluation_metadata.get("backtest_mae") if f else None
            pre = confirmed[pid]
            has_history = pid in history and history[pid].notna().any()
            obs = same_weekday(history, pid, target) if has_history else None

            reasons: list[str] = []
            if closed:
                recommended = pre
                reasons.append(f"No sales were recorded on {weekday}s in the last 8 weeks.")
            elif not has_history:
                recommended = pre
                reasons.append("No sales history yet.")
                warnings.append(
                    PlanWarning(
                        severity="warning",
                        product_id=pid,
                        message=(
                            f"{product.name}: no sales history, so only pre-orders are planned."
                        ),
                    )
                )
            else:
                recommended = max(int(round(predicted)), pre)
                is_average = self.demand.provider.name == "weekday_average"
                if is_average and obs is not None and len(obs) >= 2:
                    sold = ", ".join(str(int(v)) for v in obs)
                    reasons.append(
                        f"Last {len(obs)} {weekday}s sold {sold}, an average of {_fmt(predicted)}."
                    )
                else:
                    interval = f.evaluation_metadata.get("interval_80") if f else None
                    detail = (
                        f" (80% range {_fmt(interval[0])} to {_fmt(interval[1])})"
                        if interval
                        else ""
                    )
                    reasons.append(
                        f"{self.demand.provider.label} forecast: {_fmt(predicted)}{detail}."
                    )
                    if obs is not None and len(obs) >= 2:
                        sold = ", ".join(str(int(v)) for v in obs)
                        reasons.append(
                            f"For reference, the last {len(obs)} {weekday}s sold {sold}."
                        )
                if obs is not None and len(obs) < 2:
                    warnings.append(
                        PlanWarning(
                            severity="info",
                            product_id=pid,
                            message=f"{product.name}: fewer than 2 past {weekday}s to learn from.",
                        )
                    )
                if obs is not None and len(obs) >= 3 and obs.mean() > 0:
                    cv = float(np.std(obs) / obs.mean())
                    if cv > HIGH_VARIABILITY_CV:
                        warnings.append(
                            PlanWarning(
                                severity="info",
                                product_id=pid,
                                message=f"{product.name}: {weekday} sales vary a lot "
                                f"({int(obs.min())} to {int(obs.max())}).",
                            )
                        )
            if pre:
                reasons.append(f"{pre} already pre-ordered.")
                if not closed and has_history and pre > round(predicted):
                    reasons.append(
                        "Pre-orders exceed usual demand, so the plan follows pre-orders."
                    )
            if mae is not None and has_history and not closed:
                reasons.append(f"In testing this forecast was off by about {_fmt(mae)} a day.")

            items.append(
                KitchenPlanItem(
                    product_id=pid,
                    product_name=product.name,
                    predicted_quantity=predicted,
                    baseline_quantity=baseline,
                    typical_error=mae,
                    confirmed_quantity=pre,
                    recommended_quantity=recommended,
                    final_quantity=recommended,
                    explanation=" ".join(reasons),
                )
            )

        if closed:
            warnings.insert(
                0,
                PlanWarning(
                    severity="warning",
                    message=f"You don't usually open on {weekday}s. Only pre-orders are planned.",
                ),
            )
        if history.empty:
            warnings.insert(
                0,
                PlanWarning(
                    severity="warning",
                    message="No sales history yet. Import past sales to get demand forecasts.",
                ),
            )
        elif history.index[-1] < today - timedelta(days=STALE_AFTER_DAYS):
            warnings.insert(
                0,
                PlanWarning(
                    severity="warning",
                    message=f"Latest sales data is from {history.index[-1].isoformat()}. "
                    "Forecasts may be out of date; import recent sales.",
                ),
            )
        for o in target_orders:
            if o.extraction_confidence is not None and o.extraction_confidence < LOW_CONFIDENCE:
                name = products[o.product_id].name if o.product_id in products else o.product_id
                warnings.append(
                    PlanWarning(
                        severity="warning",
                        product_id=o.product_id,
                        message=f"A pre-order for {name} was read from a message with low "
                        "confidence. Double-check it.",
                    )
                )

        plan = KitchenPlan(
            business_id=self.business.id,
            target_date=target,
            items=items,
            explanations=self._explanations(history, target),
            warnings=warnings,
            ingredient_needs=ingredient_needs(items, products),
            customer_requests=self._customer_requests(target_orders, products),
            model_name=self.demand.provider.name,
        )
        if reusable:
            plan.id = reusable.id
        self.repo.save_plan(plan)
        return plan

    def _explanations(self, history, target: date) -> list[str]:
        lines = [
            f"Forecast model: {self.demand.provider.label}. {self.demand.provider.description}",
            "Recommended quantity = forecast rounded to whole units, never less than what is "
            "already pre-ordered.",
        ]
        if not history.empty:
            lines.append(
                f"Based on {len(history)} open days of sales from {history.index[0].isoformat()} "
                f"to {history.index[-1].isoformat()}."
            )
        if self.demand.fallback_reason:
            lines.append(self.demand.fallback_reason)
        return lines

    def _customer_requests(self, orders, products) -> list[CustomerRequest]:
        customers = {c.id: c for c in self.repo.list_customers(self.business.id)}
        requests = []
        for o in orders:
            customer = customers.get(o.customer_id) if o.customer_id else None
            if not customer and not o.notes:
                continue
            requests.append(
                CustomerRequest(
                    order_id=o.id,
                    customer_name=customer.display_name if customer else None,
                    product_name=products[o.product_id].name
                    if o.product_id in products
                    else o.product_id,
                    quantity=o.quantity,
                    dietary_constraints=customer.dietary_constraints if customer else [],
                    notes=o.notes,
                )
            )
        return requests

    def approve(self, plan_id: str, note: str | None = None) -> KitchenPlan:
        plan = self.get(plan_id)
        transition(plan, PlanStatus.APPROVED)
        plan.review_note = note or plan.review_note
        self.repo.save_plan(plan)
        return plan

    def reject(self, plan_id: str, note: str | None = None) -> KitchenPlan:
        plan = self.get(plan_id)
        transition(plan, PlanStatus.REJECTED)
        plan.review_note = note or plan.review_note
        self.repo.save_plan(plan)
        return plan

    def modify(self, plan_id: str, quantities: dict[str, int], note: str | None) -> KitchenPlan:
        plan = self.get(plan_id)
        known = {i.product_id for i in plan.items}
        unknown = set(quantities) - known
        if unknown:
            raise ValueError(f"Products not in this plan: {', '.join(sorted(unknown))}")
        if any(q < 0 for q in quantities.values()):
            raise ValueError("Quantities cannot be negative.")
        transition(plan, PlanStatus.MODIFIED)
        for item in plan.items:
            if item.product_id in quantities:
                item.final_quantity = quantities[item.product_id]
        products = {p.id: p for p in self.repo.list_products(self.business.id)}
        plan.ingredient_needs = ingredient_needs(plan.items, products)
        plan.review_note = note or plan.review_note
        self.repo.save_plan(plan)
        return plan
