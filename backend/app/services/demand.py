from datetime import date, timedelta

import pandas as pd

from app.models import Business, Forecast
from app.repository import Repository
from app.services.forecasting import (
    EvaluationReport,
    ForecastProvider,
    HistoricalAverage,
    WeekdayAverage,
    backtest,
    build_history,
    is_usually_closed,
)

BASELINE = HistoricalAverage()


def available_providers() -> dict[str, ForecastProvider]:
    return {p.name: p for p in (HistoricalAverage(), WeekdayAverage())}


class DemandService:
    def __init__(self, repo: Repository, business: Business, provider_name: str):
        self.repo = repo
        self.business = business
        providers = available_providers()
        self.requested_provider = provider_name
        self.provider = providers.get(provider_name, providers["weekday_average"])
        self.baseline = BASELINE

    @property
    def fallback_reason(self) -> str | None:
        if self.provider.name != self.requested_provider:
            return (
                f"Forecast provider '{self.requested_provider}' unavailable; using weekday average."
            )
        return None

    def product_ids(self) -> list[str]:
        return [p.id for p in self.repo.list_products(self.business.id) if p.active]

    def history(self, today: date) -> pd.DataFrame:
        # Today's sales are excluded: the day is not over, so its totals would bias forecasts low.
        orders = self.repo.list_orders(self.business.id, end=today)
        return build_history(orders, self.product_ids(), before=today)

    def next_open_day(self, today: date) -> date:
        """Tomorrow, or the first day after it that the business normally trades."""
        history = self.history(today)
        for offset in range(1, 8):
            candidate = today + timedelta(days=offset)
            if not is_usually_closed(history, candidate):
                return candidate
        return today + timedelta(days=1)

    def evaluate(self, today: date) -> EvaluationReport:
        history = self.history(today)
        providers = [self.baseline]
        if self.provider.name != self.baseline.name:
            providers.append(self.provider)
        return backtest(history, providers)

    def forecast(self, target: date, today: date) -> list[Forecast]:
        history = self.history(today)
        pids = list(history.columns) or self.product_ids()
        if history.empty:
            history = pd.DataFrame(columns=pids, dtype=float)
        predicted = self.provider.predict(history, target, pids)
        baseline = self.baseline.predict(history, target, pids)
        report = self.evaluate(today)
        featured = next((m for m in report.metrics if m.provider == self.provider.name), None)
        forecasts = []
        for pid in pids:
            metrics = featured.by_product.get(pid) if featured else None
            forecasts.append(
                Forecast(
                    business_id=self.business.id,
                    product_id=pid,
                    target_date=target,
                    predicted_quantity=round(predicted[pid], 2),
                    model_name=self.provider.name,
                    baseline_quantity=round(baseline[pid], 2),
                    evaluation_metadata={
                        "backtest_mae": metrics.mae if metrics else None,
                        "backtest_days": report.holdout_days,
                        "history_end": report.history_end.isoformat()
                        if report.history_end
                        else None,
                        "fallback_reason": self.fallback_reason,
                    },
                )
            )
        self.repo.save_forecasts(forecasts)
        return forecasts
