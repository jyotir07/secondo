import logging
import time
from datetime import date

from app.config import Settings
from app.services.catalog import ProductCatalog
from app.services.extraction import ExtractionError, ExtractionResult, RuleBasedExtractor
from app.services.gemma import OllamaExtractor

log = logging.getLogger(__name__)

PING_TTL_S = 30


class ExtractionService:
    """Chooses between Gemma (via Ollama) and the deterministic parser.

    EXTRACTION_PROVIDER: "rules" never calls a model; "ollama" and "auto" use Gemma when it is
    reachable and fall back to rules otherwise. Every fallback is labelled in the result.
    """

    def __init__(self, settings: Settings, ollama: OllamaExtractor | None = None):
        self.settings = settings
        self.rules = RuleBasedExtractor()
        self.ollama = ollama or OllamaExtractor(
            settings.ollama_url, settings.ollama_model, settings.ollama_timeout_s
        )
        self._ping: tuple[float, bool, str] | None = None

    @property
    def uses_model(self) -> bool:
        return self.settings.extraction_provider in ("ollama", "auto")

    def model_status(self) -> tuple[bool, str]:
        now = time.monotonic()
        if self._ping is None or now - self._ping[0] > PING_TTL_S:
            ok, detail = self.ollama.ping()
            self._ping = (now, ok, detail)
        return self._ping[1], self._ping[2]

    def extract(self, text: str, catalog: ProductCatalog, today: date) -> ExtractionResult:
        if not self.uses_model:
            return self.rules.extract(text, catalog, today)

        available, detail = self.model_status()
        if available:
            try:
                return self.ollama.extract(text, catalog, today)
            except ExtractionError as exc:
                log.warning("Gemma extraction failed, using rules: %s", exc)
                reason = str(exc)
                self._ping = None  # re-check reachability next time
        else:
            reason = detail

        result = self.rules.extract(text, catalog, today)
        result.fallback_used = True
        result.fallback_reason = reason
        return result

    def status(self) -> dict:
        if not self.uses_model:
            return {
                "configured": self.settings.extraction_provider,
                "active": "rules",
                "model": None,
                "available": True,
                "detail": "Deterministic rule-based parser. Runs locally, no model needed.",
            }
        available, detail = self.model_status()
        return {
            "configured": self.settings.extraction_provider,
            "active": "ollama" if available else "rules",
            "model": self.settings.ollama_model,
            "available": available,
            "detail": detail
            if available
            else f"{detail} Using the rule-based parser until the model is available.",
        }
