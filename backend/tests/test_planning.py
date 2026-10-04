from datetime import date

import pytest

from app.models import OrderSource, OrderStatus, PlanStatus
from app.services.demand import DemandService
from app.services.ingestion import IngestionService, OrderDraft
from app.services.planning import InvalidTransition, PlanConflict, PlanningService
from tests.conftest import TODAY

SATURDAY = date(2026, 10, 10)
MONDAY = date(2026, 10, 5)


@pytest.fixture
def planning(repo, business, sample_csv):
    IngestionService(repo, business).import_csv(sample_csv, TODAY)
    return PlanningService(repo, business, DemandService(repo, business, "weekday_average"))


def preorder(repo, business, pid, qty, day=SATURDAY, confidence=None):
    IngestionService(repo, business).create_orders(
        [
            OrderDraft(
                product_id=pid, quantity=qty, order_date=day, source=OrderSource.MESSAGE,
                status=OrderStatus.CONFIRMED, customer_name="Priya",
                dietary_constraints=["eggless"], notes="Pickup 10am",
                original_input=f"{qty} {pid}", extraction_confidence=confidence,
            )
        ]
    )  # fmt: skip


def item(plan, pid):
    return next(i for i in plan.items if i.product_id == pid)


def test_plan_recommends_rounded_forecast_with_explanations(planning):
    plan = planning.generate(SATURDAY, TODAY)
    assert plan.status == PlanStatus.DRAFT
    croissant = item(plan, "butter-croissant")
    assert croissant.recommended_quantity == round(croissant.predicted_quantity)
    assert croissant.final_quantity == croissant.recommended_quantity
    assert "Saturdays sold" in croissant.explanation
    assert croissant.typical_error is not None
    assert any(n.ingredient == "Butter" for n in plan.ingredient_needs)


def test_preorders_set_a_floor_and_appear_as_customer_requests(planning, repo, business):
    preorder(repo, business, "chocolate-cake-1kg", 9, confidence=0.5)
    plan = planning.generate(SATURDAY, TODAY)
    cake = item(plan, "chocolate-cake-1kg")
    assert cake.confirmed_quantity == 9 and cake.recommended_quantity == 9
    assert "Pre-orders exceed usual demand" in cake.explanation
    assert plan.customer_requests[0].customer_name == "Priya"
    assert plan.customer_requests[0].dietary_constraints == ["eggless"]
    assert any("low confidence" in w.message for w in plan.warnings)


def test_closed_day_plans_only_preorders(planning, repo, business):
    preorder(repo, business, "banana-bread", 2, day=MONDAY)
    plan = planning.generate(MONDAY, TODAY)
    assert item(plan, "banana-bread").recommended_quantity == 2
    assert item(plan, "butter-croissant").recommended_quantity == 0
    assert "don't usually open on Mondays" in plan.warnings[0].message


def test_next_open_day_skips_closed_monday(planning):
    assert planning.demand.next_open_day(TODAY) == date(2026, 10, 6)


def test_empty_history_still_produces_a_plan(repo, business):
    service = PlanningService(repo, business, DemandService(repo, business, "weekday_average"))
    plan = service.generate(SATURDAY, TODAY)
    assert all(i.recommended_quantity == 0 for i in plan.items)
    assert "No sales history" in plan.warnings[0].message


def test_modify_then_approve(planning):
    plan = planning.generate(SATURDAY, TODAY)
    butter_before = next(n for n in plan.ingredient_needs if n.ingredient == "Butter").quantity
    plan = planning.modify(plan.id, {"butter-croissant": 0}, "Out of butter")
    assert plan.status == PlanStatus.MODIFIED
    assert item(plan, "butter-croissant").final_quantity == 0
    assert item(plan, "butter-croissant").recommended_quantity > 0  # original kept for the record
    butter_after = next(n for n in plan.ingredient_needs if n.ingredient == "Butter").quantity
    assert butter_after < butter_before

    plan = planning.approve(plan.id)
    assert plan.status == PlanStatus.APPROVED and plan.approved_at is not None
    assert plan.review_note == "Out of butter"


@pytest.mark.parametrize("final", ["approve", "reject"])
def test_final_states_are_locked(planning, final):
    plan = planning.generate(SATURDAY, TODAY)
    getattr(planning, final)(plan.id)
    with pytest.raises(InvalidTransition):
        planning.modify(plan.id, {"butter-croissant": 1}, None)
    with pytest.raises(InvalidTransition):
        planning.approve(plan.id)


def test_regenerating_replaces_draft_but_not_approved(planning, repo, business):
    first = planning.generate(SATURDAY, TODAY)
    second = planning.generate(SATURDAY, TODAY)
    assert first.id == second.id
    assert len(repo.list_plans(business.id)) == 1

    planning.approve(second.id)
    with pytest.raises(PlanConflict):
        planning.generate(SATURDAY, TODAY)


def test_modify_rejects_unknown_products_and_negatives(planning):
    plan = planning.generate(SATURDAY, TODAY)
    with pytest.raises(ValueError, match="not in this plan"):
        planning.modify(plan.id, {"nope": 1}, None)
    with pytest.raises(ValueError, match="negative"):
        planning.modify(plan.id, {"butter-croissant": -1}, None)
