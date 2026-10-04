from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services import demand as demand_module
from app.services.demand import DemandService
from app.services.forecasting import HistoricalAverage, backtest
from app.services.ingestion import IngestionService
from app.services.tabpfn_provider import (
    FEATURES,
    TabPFNForecaster,
    build_features,
    tabpfn_installed,
)
from tests.conftest import TODAY


def wide_history(days: int = 60, products=("a", "b")) -> pd.DataFrame:
    start = date(2026, 6, 1)
    idx = [start + timedelta(days=i) for i in range(days)]
    rng = np.random.default_rng(0)
    data = {p: rng.integers(5, 15, size=days).astype(float) for p in products}
    return pd.DataFrame(data, index=pd.Index(idx, name="date"))


def test_features_never_include_the_rows_own_sales():
    history = wide_history()
    before = build_features(history, ["a", "b"])
    changed = history.copy()
    day = history.index[40]
    changed.loc[day, "a"] = 999.0
    after = build_features(changed, ["a", "b"])

    on_or_before = before["date"] <= day
    pd.testing.assert_frame_equal(
        before.loc[on_or_before, FEATURES], after.loc[on_or_before, FEATURES]
    )
    next_row = after[(after["date"] == history.index[41]) & (after["product_id"] == "a")]
    assert next_row["lag_1"].item() == 999.0  # the next day may use it


class BlockSpy:
    name = "spy"
    label = "Spy"
    refit_every = 7

    def __init__(self):
        self.calls = []

    def predict_days(self, history, days, product_ids):
        self.calls.append((history.index.max(), list(days)))
        return {d: {pid: {"mean": 1.0} for pid in product_ids} for d in days}


def test_block_refit_providers_only_see_data_before_each_predicted_day():
    history = wide_history()
    spy = BlockSpy()
    report = backtest(history, [HistoricalAverage(), spy], holdout_days=14)

    assert len(spy.calls) == 2
    for latest_seen, days in spy.calls:
        assert latest_seen < days[-1]
        assert len(days) == 7
    assert {m.provider for m in report.metrics} == {"historical_average", "spy"}
    assert "retrained every 7 open days" in report.method


def seeded_service(repo, business, sample_csv, **kwargs) -> DemandService:
    IngestionService(repo, business).import_csv(sample_csv, TODAY)
    return DemandService(repo, business, "tabpfn", **kwargs)


def test_missing_tabpfn_is_reported_and_baseline_still_works(
    repo, business, sample_csv, monkeypatch
):
    monkeypatch.setattr(
        demand_module, "tabpfn_installed", lambda: (False, "TabPFN is not installed.")
    )
    svc = seeded_service(repo, business, sample_csv)

    assert svc.provider.name == "weekday_average"
    assert "TabPFN is not installed" in svc.fallback_reason
    forecasts = svc.forecast(TODAY + timedelta(days=2), TODAY)
    assert all(f.model_name == "weekday_average" for f in forecasts)
    assert forecasts[0].evaluation_metadata["fallback_reason"] == svc.fallback_reason
    assert {m.provider for m in svc.evaluate(TODAY).metrics} == {
        "historical_average",
        "weekday_average",
    }


class Exploding(TabPFNForecaster):
    def predict_days(self, history, days, product_ids):
        raise RuntimeError("weights not downloaded")


def test_runtime_failure_falls_back_and_is_remembered(repo, business, sample_csv, monkeypatch):
    monkeypatch.setattr(demand_module, "tabpfn_installed", lambda: (True, None))
    monkeypatch.setattr(demand_module, "TABPFN", Exploding())
    cache: dict = {}
    svc = seeded_service(repo, business, sample_csv, cache=cache)

    forecasts = svc.forecast(TODAY + timedelta(days=2), TODAY)

    assert all(f.model_name == "weekday_average" for f in forecasts)
    assert "weights not downloaded" in svc.fallback_reason
    again = DemandService(repo, business, "tabpfn", cache=cache)
    assert again.provider.name == "weekday_average"
    assert "weights not downloaded" in again.fallback_reason


def test_results_are_cached_per_history(repo, business, sample_csv):
    cache: dict = {}
    svc = seeded_service(repo, business, sample_csv, cache=cache)
    svc.provider = demand_module.FALLBACK  # keep the test fast; caching is provider-agnostic
    first = svc.evaluate(TODAY)
    assert svc.evaluate(TODAY) is first


@pytest.mark.skipif(not tabpfn_installed()[0], reason="TabPFN extra not installed")
def test_real_tabpfn_predicts_plausible_quantities():
    history = wide_history(days=50)
    target = history.index[-1] + timedelta(days=1)
    preds = TabPFNForecaster(n_estimators=1).predict_days(history, [target], ["a", "b"])[target]
    for p in preds.values():
        assert 3 <= p["mean"] <= 17
        assert p["p10"] <= p["mean"] <= p["p90"]
