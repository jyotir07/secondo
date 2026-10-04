"""Gemma (or any Ollama-served model) as an order extractor.

The model only reads the message. Catalogue matching, date resolution and confidence scoring
reuse the deterministic code in extraction.py, so model output is never trusted blindly.
"""

import json
import time
from datetime import date

import httpx
import sentry_sdk
from pydantic import BaseModel, Field, ValidationError

from app.services.catalog import ProductCatalog
from app.services.extraction import (
    DIETARY_PATTERNS,
    ExtractedItem,
    ExtractionError,
    ExtractionResult,
    finalize,
    resolve_date,
)


class LLMItem(BaseModel):
    product: str = Field(min_length=1)
    quantity: int = Field(gt=0, le=10_000)


class LLMOrder(BaseModel):
    items: list[LLMItem]
    date_phrase: str | None = None
    date: str | None = None
    customer_name: str | None = None
    dietary_constraints: list[str] = Field(default_factory=list)
    notes: str | None = None


SYSTEM_PROMPT = """You read customer order messages for a small bakery and return JSON only.
Rules:
- items: every product the customer wants, using the closest name from the catalogue below,
  with an integer quantity ("a dozen" = 12, "half a dozen" = 6). If no quantity is given, use 1.
- date_phrase: the words in the message that say when the order is needed, copied exactly
  (e.g. "Saturday", "tomorrow", "12th Oct"). null if none.
- date: that date as YYYY-MM-DD, using today's date given below. null if none.
- customer_name: the sender's name if they sign or introduce themselves, else null.
- dietary_constraints: lowercase labels such as eggless, vegan, gluten-free, nut-free.
- notes: pickup/delivery time, messages to write on cakes, or other instructions. null if none.
Do not invent items, names or dates that are not in the message.

Catalogue:
{catalogue}"""


class OllamaExtractor:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        retries: int = 1,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s
        self.retries = retries
        self.client = client or httpx.Client()

    def ping(self, timeout_s: float = 2.0) -> tuple[bool, str]:
        """Is Ollama reachable and is the configured model pulled?"""
        try:
            res = self.client.get(f"{self.base_url}/api/tags", timeout=timeout_s)
            res.raise_for_status()
            names = {m.get("name", "") for m in res.json().get("models", [])}
        except (httpx.HTTPError, ValueError) as exc:
            return False, f"Ollama is not reachable at {self.base_url} ({type(exc).__name__})."
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names:
            return (
                False,
                f"Ollama is running but '{self.model}' is not pulled. "
                f"Run: ollama pull {self.model}",
            )
        return True, f"{self.model} via Ollama at {self.base_url}."

    def _chat(self, text: str, catalog: ProductCatalog, today: date) -> LLMOrder:
        catalogue = "\n".join(f"- {p.name}" for p in catalog.products)
        payload = {
            "model": self.model,
            "stream": False,
            "format": LLMOrder.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(catalogue=catalogue)},
                {
                    "role": "user",
                    "content": f"Today is {today:%A} {today.isoformat()}.\n\nMessage:\n{text}",
                },
            ],
        }
        last_error = "no attempt made"
        for attempt in range(1, self.retries + 2):
            try:
                with sentry_sdk.start_span(op="gen_ai.request", name=f"chat {self.model}") as span:
                    # Message text and customer names are deliberately not attached: in local
                    # mode they must not leave the machine, and that includes telemetry.
                    span.set_data("gen_ai.operation.name", "chat")
                    span.set_data("gen_ai.provider.name", "ollama")
                    span.set_data("gen_ai.request.model", self.model)
                    span.set_data("gen_ai.request.temperature", 0)
                    span.set_data("secondo.attempt", attempt)
                    res = self.client.post(
                        f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_s
                    )
                    res.raise_for_status()
                    body = res.json()
                    if "prompt_eval_count" in body:
                        span.set_data("gen_ai.usage.input_tokens", body["prompt_eval_count"])
                    if "eval_count" in body:
                        span.set_data("gen_ai.usage.output_tokens", body["eval_count"])
                    content = body["message"]["content"]
                    return LLMOrder.model_validate(json.loads(content))
            except httpx.TimeoutException as exc:
                # A timeout will very likely repeat; retrying only doubles the wait.
                raise ExtractionError(f"Model timed out after {self.timeout_s:.0f}s.") from exc
            except httpx.HTTPError as exc:
                raise ExtractionError(f"Ollama request failed: {exc}") from exc
            except (KeyError, ValueError, ValidationError) as exc:
                last_error = f"invalid model output ({type(exc).__name__})"
        raise ExtractionError(f"Model returned {last_error} after {self.retries + 1} attempts.")

    def extract(self, text: str, catalog: ProductCatalog, today: date) -> ExtractionResult:
        started = time.perf_counter()
        order = self._chat(text, catalog, today)

        items: dict[str, ExtractedItem] = {}
        unmatched: list[ExtractedItem] = []
        for it in order.items:
            product = catalog.match(it.product)
            if product is None:
                unmatched.append(
                    ExtractedItem(
                        product_id=None,
                        product_name=catalog.suggest(it.product) or it.product,
                        mention=it.product,
                        quantity=it.quantity,
                        matched=False,
                    )
                )
            elif product.id in items:
                items[product.id].quantity += it.quantity
            else:
                items[product.id] = ExtractedItem(
                    product_id=product.id,
                    product_name=product.name,
                    mention=it.product,
                    quantity=it.quantity,
                    matched=True,
                )

        order_date = resolve_date(order.date_phrase, today) if order.date_phrase else None
        if order_date is None and order.date:
            try:
                order_date = date.fromisoformat(order.date)
            except ValueError:
                order_date = None

        known = set(DIETARY_PATTERNS)
        dietary = sorted({d.strip().lower() for d in order.dietary_constraints if d.strip()})
        result = ExtractionResult(
            items=[*items.values(), *unmatched],
            order_date=order_date,
            customer_name=(order.customer_name or "").strip() or None,
            dietary_constraints=[d for d in dietary if d in known] or dietary,
            notes=(order.notes or "").strip() or None,
            confidence=0,
            provider=self.name,
            model=self.model,
            original_input=text,
        )
        result = finalize(result, today)
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result
