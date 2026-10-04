import json
from dataclasses import replace
from datetime import date

import httpx
import pytest

from app.services.catalog import ProductCatalog
from app.services.extraction_service import ExtractionService
from app.services.gemma import OllamaExtractor
from tests.conftest import TODAY

MESSAGE = "Hi, 2 sourdough loaves and 6 cinnamon rolls for Saturday please. Eggless! - Priya"
TAGS = {"models": [{"name": "gemma3:4b"}]}


@pytest.fixture
def catalog(repo, business):
    return ProductCatalog(repo.list_products(business.id))


def ollama_with(chat_responses: list, tags=TAGS) -> tuple[OllamaExtractor, list]:
    """An extractor whose HTTP calls are answered from a script instead of a real server."""
    calls = []
    replies = iter(chat_responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags)
        calls.append(json.loads(request.content))
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaExtractor("http://ollama.test", "gemma3:4b", 5, client=client), calls


def service(settings, ollama, provider="auto"):
    return ExtractionService(replace(settings, extraction_provider=provider), ollama=ollama)


def test_falls_back_to_rules_when_ollama_is_not_running(settings, catalog):
    # Nothing listens on port 9; the connection is refused immediately.
    ollama = OllamaExtractor("http://127.0.0.1:9", "gemma3:4b", 2)
    svc = service(settings, ollama, provider="ollama")

    result = svc.extract(MESSAGE, catalog, TODAY)

    assert result.provider == "rules"
    assert result.fallback_used is True
    assert "not reachable" in result.fallback_reason
    assert {i.product_id: i.quantity for i in result.items} == {
        "sourdough-loaf": 2,
        "cinnamon-roll": 6,
    }
    assert result.order_date == date(2026, 10, 10)
    assert svc.status()["active"] == "rules"


def test_rules_mode_never_calls_the_model(settings, catalog):
    ollama, calls = ollama_with([])
    result = service(settings, ollama, provider="rules").extract(MESSAGE, catalog, TODAY)
    assert result.provider == "rules" and result.fallback_used is False
    assert calls == []


def test_gemma_output_is_validated_and_matched_to_catalogue(settings, catalog):
    ollama, calls = ollama_with(
        [
            {
                "items": [
                    {"product": "Sourdough Loaf", "quantity": 2},
                    {"product": "cinnamon rolls", "quantity": 6},
                    {"product": "Baguette", "quantity": 1},
                ],
                "date_phrase": "Saturday",
                "date": "2026-10-11",  # wrong weekday maths; the phrase wins
                "customer_name": "Priya",
                "dietary_constraints": ["Eggless"],
                "notes": None,
            }
        ]
    )
    result = service(settings, ollama).extract(MESSAGE, catalog, TODAY)

    assert result.provider == "ollama" and result.model == "gemma3:4b"
    assert result.fallback_used is False
    matched = {i.product_id: i.quantity for i in result.items if i.matched}
    assert matched == {"sourdough-loaf": 2, "cinnamon-roll": 6}
    assert any(not i.matched and i.mention == "Baguette" for i in result.items)
    assert any("Baguette" in w for w in result.warnings)
    assert result.order_date == date(2026, 10, 10)
    assert result.dietary_constraints == ["eggless"]
    assert calls[0]["format"]["type"] == "object"  # structured output requested
    assert calls[0]["options"]["temperature"] == 0


def test_invalid_json_is_retried_once_then_succeeds(settings, catalog):
    ollama, calls = ollama_with(
        ["not json at all", {"items": [{"product": "Sourdough Loaf", "quantity": 3}]}]
    )
    result = service(settings, ollama).extract(MESSAGE, catalog, TODAY)
    assert len(calls) == 2
    assert result.provider == "ollama"
    assert result.items[0].quantity == 3


def test_schema_violations_fall_back_to_rules(settings, catalog):
    bad = {"items": [{"product": "Sourdough Loaf", "quantity": -4}]}
    ollama, calls = ollama_with([bad, bad])
    result = service(settings, ollama).extract(MESSAGE, catalog, TODAY)
    assert len(calls) == 2
    assert result.provider == "rules" and result.fallback_used is True
    assert "invalid model output" in result.fallback_reason


def test_timeout_falls_back_without_retrying(settings, catalog):
    ollama, calls = ollama_with([httpx.ReadTimeout("slow")])
    result = service(settings, ollama).extract(MESSAGE, catalog, TODAY)
    assert len(calls) == 1
    assert result.fallback_used is True and "timed out" in result.fallback_reason


def test_missing_model_is_reported(settings, catalog):
    ollama, _ = ollama_with([], tags={"models": [{"name": "llama3:latest"}]})
    svc = service(settings, ollama)
    status = svc.status()
    assert status["available"] is False and "ollama pull gemma3:4b" in status["detail"]
    assert svc.extract(MESSAGE, catalog, TODAY).fallback_used is True
