import json
from datetime import timedelta

import httpx
import pytest

from app.models import PlanStatus
from app.services.demand import DemandService
from app.services.ingestion import IngestionService
from app.services.narration import (
    NarrationError,
    NarrationService,
    NarrationUnavailable,
    PlanNotApproved,
    briefing_text,
)
from app.services.planning import PlanningService
from tests.conftest import TODAY

AUDIO = b"ID3fake-mp3-bytes"


@pytest.fixture
def plan(repo, business, sample_csv, client):
    IngestionService(repo, business).import_csv(sample_csv, TODAY)
    target = TODAY + timedelta(days=2)
    client.post(
        "/api/orders",
        json={
            "order_date": target.isoformat(),
            "items": [{"product_id": "cinnamon-roll", "quantity": 6}],
            "customer_name": "Priya Sharma",
            "dietary_constraints": ["eggless"],
            "notes": "Call Priya on 98450 00000 before pickup",
        },
    )
    demand = DemandService(repo, business, "weekday_average")
    return PlanningService(repo, business, demand).generate(target, TODAY)


def elevenlabs(status_code=200) -> tuple[NarrationService, list]:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status_code, content=AUDIO if status_code == 200 else b"{}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NarrationService("sk_test", "voice123", "eleven_multilingual_v2", client=client), calls


def test_briefing_never_contains_customer_names_or_notes(plan):
    text = briefing_text(plan)
    assert "Priya" not in text and "98450" not in text
    assert "Keep 6 Cinnamon Roll eggless." in text
    assert text.startswith(f"Kitchen plan for {plan.target_date:%A}")


def test_approved_plan_is_narrated_once_and_cached(plan):
    plan.status = PlanStatus.APPROVED
    svc, calls = elevenlabs()

    assert svc.narrate(plan) == AUDIO
    assert svc.narrate(plan) == AUDIO
    assert len(calls) == 1
    req = calls[0]
    assert req.url.path == "/v1/text-to-speech/voice123"
    assert req.headers["xi-api-key"] == "sk_test"
    body = json.loads(req.content)
    assert body["model_id"] == "eleven_multilingual_v2"
    assert "Priya" not in body["text"]


def test_draft_plans_are_not_narrated(plan):
    svc, calls = elevenlabs()
    with pytest.raises(PlanNotApproved):
        svc.narrate(plan)
    assert calls == []


def test_without_a_key_narration_is_unavailable(plan):
    plan.status = PlanStatus.APPROVED
    svc = NarrationService(None, "voice123", "eleven_multilingual_v2")
    assert svc.status()["available"] is False
    with pytest.raises(NarrationUnavailable):
        svc.narrate(plan)


@pytest.mark.parametrize(
    ("code", "fragment"), [(401, "API key"), (429, "quota"), (404, "voice"), (500, "500")]
)
def test_elevenlabs_errors_are_explained(plan, code, fragment):
    plan.status = PlanStatus.APPROVED
    svc, _ = elevenlabs(code)
    with pytest.raises(NarrationError, match=fragment):
        svc.narrate(plan)


def test_briefing_routes(client, sample_csv):
    client.post("/api/orders/import", files={"file": ("s.csv", sample_csv, "text/csv")})
    plan = client.post("/api/kitchen-plans/generate", json={}).json()

    transcript = client.get(f"/api/kitchen-plans/{plan['id']}/briefing").json()
    assert transcript["voice_available"] is False
    assert transcript["text"].startswith("Kitchen plan for")
    # Tests run without an ElevenLabs key, so audio is reported as unavailable, not faked.
    res = client.post(f"/api/kitchen-plans/{plan['id']}/briefing/audio")
    assert res.status_code == 503
    providers = client.get("/api/settings/providers").json()
    assert providers["narration"]["available"] is False


def test_elevenlabs_explanation_is_passed_through(plan):
    plan.status = PlanStatus.APPROVED

    def handler(request):
        detail = {"code": "paid_plan_required", "message": "Free users cannot use library voices."}
        return httpx.Response(402, json={"detail": detail})

    svc = NarrationService(
        "sk_test", "lib", "eleven_multilingual_v2",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )  # fmt: skip
    with pytest.raises(NarrationError, match="Free users cannot use library voices"):
        svc.narrate(plan)
