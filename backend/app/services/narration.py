"""Spoken briefing of an approved kitchen plan via ElevenLabs text-to-speech.

ElevenLabs is a cloud service, so the briefing text is built to carry only what the kitchen
needs to hear: product quantities, dietary labels and warnings. Customer names and free-text
notes never leave the server.
"""

from collections import OrderedDict

import httpx
import sentry_sdk

from app.models import KitchenPlan, PlanStatus

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
CACHE_SIZE = 32


class NarrationError(RuntimeError):
    pass


class NarrationUnavailable(NarrationError):
    pass


class PlanNotApproved(NarrationError):
    pass


def _qty(n: int, name: str) -> str:
    return f"{n} {name}"


def briefing_text(plan: KitchenPlan) -> str:
    day = f"{plan.target_date.strftime('%A')}, {plan.target_date.day} {plan.target_date:%B}"
    items = [i for i in plan.items if i.final_quantity > 0]
    total = sum(i.final_quantity for i in items)
    parts = [f"Kitchen plan for {day}. {total} items to prepare."]
    if items:
        parts.append(
            " ".join(
                f"{_qty(i.final_quantity, i.product_name)}."
                for i in sorted(items, key=lambda i: -i.final_quantity)
            )
        )
    else:
        parts.append("Nothing to bake.")

    requests = plan.customer_requests
    if requests:
        noun = "order" if len(requests) == 1 else "orders"
        parts.append(f"{len(requests)} customer {noun} included.")
        dietary = [r for r in requests if r.dietary_constraints]
        for r in dietary:
            parts.append(
                f"Keep {_qty(r.quantity, r.product_name)} {', '.join(r.dietary_constraints)}."
            )

    warnings = [w.message for w in plan.warnings if w.severity == "warning"]
    if warnings:
        parts.append("Watch out: " + " ".join(warnings))
    return " ".join(parts)


def _explain(res: httpx.Response, voice_id: str) -> str:
    # ElevenLabs' own message is the most actionable (e.g. "Free users cannot use library
    # voices via the API"); it never contains the key.
    try:
        detail = res.json().get("detail")
        message = detail.get("message") if isinstance(detail, dict) else detail
    except ValueError:
        message = None
    generic = {
        401: "ElevenLabs rejected the API key or it lacks Text to Speech access.",
        402: "ElevenLabs requires a paid plan or more credits for this request.",
        404: f"ElevenLabs voice '{voice_id}' was not found.",
        429: "ElevenLabs rate limit or quota reached. Try again later.",
    }.get(res.status_code, f"ElevenLabs returned an error ({res.status_code}).")
    return f"{generic} ElevenLabs says: {message}" if message else generic


class NarrationService:
    def __init__(
        self,
        api_key: str | None,
        voice_id: str,
        model_id: str,
        timeout_s: float = 30,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.timeout_s = timeout_s
        self.client = client or httpx.Client()
        # Approved plans never change, so one synthesis per plan is enough.
        self._cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def status(self) -> dict:
        return {
            "available": self.available,
            "provider": "elevenlabs",
            "voice_id": self.voice_id if self.available else None,
            "model": self.model_id if self.available else None,
        }

    def narrate(self, plan: KitchenPlan) -> bytes:
        if not self.available:
            raise NarrationUnavailable("Voice briefings need ELEVENLABS_API_KEY on the server.")
        if plan.status != PlanStatus.APPROVED:
            raise PlanNotApproved("Only approved plans can be narrated.")
        text = briefing_text(plan)
        key = (plan.id, text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        with sentry_sdk.start_span(op="secondo.narrate", name="ElevenLabs briefing") as span:
            span.set_data("secondo.narration.characters", len(text))
            span.set_data("secondo.narration.model", self.model_id)
            try:
                res = self.client.post(
                    API_URL.format(voice_id=self.voice_id),
                    headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
                    params={"output_format": "mp3_44100_128"},
                    json={"text": text, "model_id": self.model_id},
                    timeout=self.timeout_s,
                )
            except httpx.TimeoutException as exc:
                raise NarrationError("ElevenLabs took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise NarrationError(f"Could not reach ElevenLabs ({type(exc).__name__}).") from exc

        if res.status_code >= 400:
            raise NarrationError(_explain(res, self.voice_id))

        audio = res.content
        self._cache[key] = audio
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return audio
