import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import Business
from app.repository import Repository
from app.seed import ensure_seeded
from app.services.demand import DemandService
from app.services.extraction_service import ExtractionService
from app.services.ingestion import IngestionService
from app.services.planning import PlanningService


class Container:
    """Wires services together once per process; routes pull from here via dependencies."""

    def __init__(self, settings: Settings, repo: Repository, clock=None):
        self.settings = settings
        self.repo = repo
        self.business: Business = ensure_seeded(repo, settings)
        self._clock = clock or (lambda: datetime.now(ZoneInfo(self.business.timezone)).date())
        self.extraction = ExtractionService(settings)
        self.forecast_cache: dict = {}
        self.forecast_lock = threading.Lock()

    def today(self) -> date:
        """Operational 'today' in the business's own timezone, not the server's."""
        return self._clock()

    def ingestion(self) -> IngestionService:
        return IngestionService(self.repo, self.business)

    def demand(self) -> DemandService:
        return DemandService(
            self.repo,
            self.business,
            self.settings.forecast_provider,
            cache=self.forecast_cache,
            lock=self.forecast_lock,
        )

    def planning(self) -> PlanningService:
        return PlanningService(self.repo, self.business, self.demand())
