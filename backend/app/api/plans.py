from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_container
from app.api.schemas import PlanGenerateRequest, PlanModify, PlanReview
from app.container import Container
from app.models import KitchenPlan
from app.services.narration import (
    NarrationError,
    NarrationUnavailable,
    PlanNotApproved,
    briefing_text,
)
from app.services.planning import InvalidTransition, PlanConflict, PlanNotFound

router = APIRouter(prefix="/kitchen-plans")


def _handle(fn):
    try:
        return fn()
    except PlanNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kitchen plan not found.") from exc
    except (InvalidTransition, PlanConflict) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def generate(body: PlanGenerateRequest, c: Container = Depends(get_container)) -> KitchenPlan:
    today = c.today()
    target = body.target_date or c.demand().next_open_day(today)
    if target < today:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Plans can only be made for today or later."
        )
    return _handle(lambda: c.planning().generate(target, today))


@router.get("")
def list_plans(c: Container = Depends(get_container)) -> list[KitchenPlan]:
    return c.repo.list_plans(c.business.id)


@router.get("/{plan_id}")
def get_plan(plan_id: str, c: Container = Depends(get_container)) -> KitchenPlan:
    return _handle(lambda: c.planning().get(plan_id))


@router.post("/{plan_id}/approve")
def approve(plan_id: str, body: PlanReview, c: Container = Depends(get_container)) -> KitchenPlan:
    return _handle(lambda: c.planning().approve(plan_id, body.note))


@router.post("/{plan_id}/reject")
def reject(plan_id: str, body: PlanReview, c: Container = Depends(get_container)) -> KitchenPlan:
    return _handle(lambda: c.planning().reject(plan_id, body.note))


@router.post("/{plan_id}/modify")
def modify(plan_id: str, body: PlanModify, c: Container = Depends(get_container)) -> KitchenPlan:
    return _handle(lambda: c.planning().modify(plan_id, body.quantities, body.note))


@router.get("/{plan_id}/briefing")
def briefing(plan_id: str, c: Container = Depends(get_container)) -> dict:
    """The exact text a voice briefing would speak (also shown as a transcript)."""
    plan = _handle(lambda: c.planning().get(plan_id))
    return {"text": briefing_text(plan), "voice_available": c.narration.available}


@router.post("/{plan_id}/briefing/audio")
def briefing_audio(plan_id: str, c: Container = Depends(get_container)) -> Response:
    plan = _handle(lambda: c.planning().get(plan_id))
    try:
        audio = c.narration.narrate(plan)
    except NarrationUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except PlanNotApproved as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except NarrationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return Response(content=audio, media_type="audio/mpeg")
