from datetime import date

from app.config import Settings
from app.services.catalog import ProductCatalog
from app.services.extraction import ExtractionResult, RuleBasedExtractor


class ExtractionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.rules = RuleBasedExtractor()

    def extract(self, text: str, catalog: ProductCatalog, today: date) -> ExtractionResult:
        return self.rules.extract(text, catalog, today)

    def status(self) -> dict:
        return {
            "configured": self.settings.extraction_provider,
            "active": "rules",
            "model": None,
            "available": True,
            "detail": "Deterministic rule-based extractor. Runs locally, no model needed.",
        }
