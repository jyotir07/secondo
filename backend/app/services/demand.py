import logging
import threading
from contextlib import AbstractContextManager
from datetime import date, timedelta

import pandas as pd
import sentry_sdk

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
from app.services.tabpfn_provider import TabPFNForecaster, tabpfn_installed

log = logging.getLogger(__name__)

BASELINE = HistoricalAverage()
FALLBACK = WeekdayAverage()
TABPFN = TabPFNForecaster()


def available_providers() -> dict[str, ForecastProvider]:
    providers: list[ForecastProvider] = [BASELINE, FALLBACK]
    if tabpfn_installed()[0]:
        providers.append(TABPFN)
    return {p.name: p for p in providers}


def _fingerprint(history: pd.DataFrame) -> tuple:
    if history.empty:
        return ("empty",)
    return (len(history), history.index[-1], float(history.sum().sum()), tuple(history.columns))


class DemandService:
    """Forecasts and evaluation for one business.

    `cache` is shared across requests (owned by the app container) so the expensive TabPFN
    backtest and prediction run once per change in sales history, not on every page load.
    """

    def __init__(
        self,
        repo: Repository,
        business: Business,
        provider_name: str,
        cache: dict | None = None,
        lock: AbstractContextManager | None = None,
    ):
        self.repo = repo
        self.business = business
        self.requested_provider = provider_name
        self.cache = cache if cache is not None else {}
        # Serialises model runs so two requests don't each spend 30s of CPU on the same work.
        self.lock = lock or threading.Lock()
        providers = available_providers()
        self.provider = providers.get(provider_name, FALLBACK)
        if ("runtime_error", provider_name) in self.cache:
            # It failed earlier in this process; don't pay for another failing run.
            self.provider = FALLBACK
        self.baseline = BASELINE
        self._setup_reason: str | None = None
        if self.provider.name != provider_name:
            if provider_name == TABPFN.name:
                self._setup_reason = tabpfn_installed()[1]
            else:
                self._setup_reason = f"Unknown forecast provider '{provider_name}'."

    @property
    def fallback_reason(self) -> str | None:
        reason = self._setup_reason or self.cache.get(("runtime_error", self.requested_provider))
        if reason:
            return f"{reason} Using {FALLBACK.label.lower()} instead."
        return None

    def _runtime_failure(self, exc: Exception) -> None:
        log.exception("Forecast provider %s failed; falling back", self.provider.name)
        self.cache[("runtime_error", self.requested_provider)] = (
            f"{self.provider.label} failed to run ({type(exc).__name__}: {exc})."
        )
        self.provider = FALLBACK

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

    def _providers_to_compare(self) -> list[ForecastProvider]:
        providers: list[ForecastProvider] = [self.baseline]
        for p in (FALLBACK, self.provider):
            if p not in providers:
                providers.append(p)
        return providers

    def evaluate(self, today: date) -> EvaluationReport:
        history = self.history(today)
        providers = self._providers_to_compare()
        key = ("eval", _fingerprint(history), tuple(p.name for p in providers))
        with self.lock:
            if key not in self.cache:
                try:
                    with sentry_sdk.start_span(
                        op="secondo.forecast.backtest", name="Backtest forecast models"
                    ) as span:
                        span.set_data("secondo.providers", [p.name for p in providers])
                        span.set_data("secondo.history.open_days", len(history))
                        self.cache[key] = backtest(history, providers)
                except Exception as exc:  # noqa: BLE001 - any model failure degrades to baselines
                    self._runtime_failure(exc)
        return self.cache[key] if key in self.cache else self.evaluate(today)

    def _predict(self, history: pd.DataFrame, target: date, pids: list[str]) -> dict:
        """{product: {"mean", "p10"?, "p90"?}} from the active provider."""
        key = ("predict", _fingerprint(history), target, self.provider.name)
        with self.lock:
            if key not in self.cache:
                try:
                    if hasattr(self.provider, "predict_days") and not history.empty:
                        preds = self.provider.predict_days(history, [target], pids)[target]
                    else:
                        raw = self.provider.predict(history, target, pids)
                        preds = {pid: {"mean": v} for pid, v in raw.items()}
                    self.cache[key] = preds
                except Exception as exc:  # noqa: BLE001
                    self._runtime_failure(exc)
        return self.cache[key] if key in self.cache else self._predict(history, target, pids)

    def forecast(self, target: date, today: date) -> list[Forecast]:
        history = self.history(today)
        pids = list(history.columns) or self.product_ids()
        if history.empty:
            history = pd.DataFrame(columns=pids, dtype=float)
        # Evaluate first: if the featured model fails there, the forecast falls back too.
        report = self.evaluate(today)
        predicted = self._predict(history, target, pids)
        baseline = self.baseline.predict(history, target, pids)
        featured = next((m for m in report.metrics if m.provider == self.provider.name), None)
        forecasts = []
        for pid in pids:
            metrics = featured.by_product.get(pid) if featured else None
            p = predicted[pid]
            forecasts.append(
                Forecast(
                    business_id=self.business.id,
                    product_id=pid,
                    target_date=target,
                    predicted_quantity=round(p["mean"], 2),
                    model_name=self.provider.name,
                    baseline_quantity=round(baseline[pid], 2),
                    evaluation_metadata={
                        "backtest_mae": metrics.mae if metrics else None,
                        "backtest_days": report.holdout_days,
                        "history_end": report.history_end.isoformat()
                        if report.history_end
                        else None,
                        "interval_80": [round(p["p10"], 2), round(p["p90"], 2)]
                        if "p10" in p
                        else None,
                        "fallback_reason": self.fallback_reason,
                    },
                )
            )
        self.repo.save_forecasts(forecasts)
        return forecasts
