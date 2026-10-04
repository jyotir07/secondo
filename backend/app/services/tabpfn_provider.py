"""TabPFN demand forecasting.

One global regressor over all products. Each (open day, product) becomes a row whose features
are computed only from earlier open days (every feature is a shifted series), so a row never
sees its own sales. TabPFN is an in-context learner: "fitting" stores the training rows and the
cost is paid at predict time, so the backtest refits once per block of days, not once per day.
"""

import logging
import time
from datetime import date

import numpy as np
import pandas as pd
import sentry_sdk

log = logging.getLogger(__name__)

FEATURES = [
    "product",
    "weekday",
    "lag_1",
    "same_weekday_1",
    "same_weekday_2",
    "same_weekday_mean_4",
    "mean_7",
    "day_index",
]
MIN_TRAIN_ROWS = 60


def tabpfn_installed() -> tuple[bool, str | None]:
    try:
        import tabpfn  # noqa: F401, PLC0415
    except ImportError:
        return False, "TabPFN is not installed. Run: uv sync --extra tabpfn"
    return True, None


def build_features(frame: pd.DataFrame, product_ids: list[str]) -> pd.DataFrame:
    """Long table of (date, product, features, target) from a wide open-day history."""
    rows = []
    day_index = pd.Series(np.arange(len(frame)), index=frame.index, dtype=float)
    weekdays = pd.Series([d.weekday() for d in frame.index], index=frame.index)
    for code, pid in enumerate(product_ids):
        s = frame[pid] if pid in frame else pd.Series(np.nan, index=frame.index)
        by_weekday = s.groupby(weekdays)
        rows.append(
            pd.DataFrame(
                {
                    "date": frame.index,
                    "product_id": pid,
                    "product": float(code),
                    "weekday": weekdays.astype(float).values,
                    "lag_1": s.shift(1).values,
                    "same_weekday_1": by_weekday.shift(1).values,
                    "same_weekday_2": by_weekday.shift(2).values,
                    "same_weekday_mean_4": by_weekday.transform(
                        lambda x: x.shift(1).rolling(4, min_periods=1).mean()
                    ).values,
                    "mean_7": s.shift(1).rolling(7, min_periods=1).mean().values,
                    "day_index": day_index.values,
                    "target": s.values,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


class TabPFNForecaster:
    name = "tabpfn"
    label = "TabPFN"
    description = (
        "TabPFN v2 regressor (open-weight tabular foundation model) over weekday and lagged-sales "
        "features, one model for all products. Runs locally on CPU."
    )
    refit_every = 7

    def __init__(self, n_estimators: int = 4, device: str = "cpu"):
        self.n_estimators = n_estimators
        self.device = device

    def _regressor(self):
        # Imported lazily: torch takes seconds to import and is optional.
        from tabpfn import TabPFNRegressor  # noqa: PLC0415
        from tabpfn.constants import ModelVersion  # noqa: PLC0415

        # v2 weights are downloadable without a Hugging Face account; later versions are gated.
        return TabPFNRegressor.create_default_for_version(
            ModelVersion.V2,
            device=self.device,
            n_estimators=self.n_estimators,
            random_state=0,
            show_progress_bar=False,
        )

    def predict_days(
        self, history: pd.DataFrame, days: list[date], product_ids: list[str]
    ) -> dict[date, dict[str, dict[str, float]]]:
        """Predict each day using a model trained on rows strictly before days[0].

        Returns {day: {product_id: {"mean", "p10", "p90"}}}.
        """
        index = sorted(set(history.index) | set(days))
        frame = history.reindex(index)
        long = build_features(frame, product_ids)
        train = long[(long["date"] < days[0]) & long["target"].notna()]
        if len(train) < MIN_TRAIN_ROWS:
            raise ValueError(f"TabPFN needs at least {MIN_TRAIN_ROWS} training rows.")
        test = long[long["date"].isin(days)]

        started = time.perf_counter()
        with sentry_sdk.start_span(op="secondo.model.tabpfn", name="TabPFN fit + predict") as span:
            span.set_data("secondo.tabpfn.train_rows", len(train))
            span.set_data("secondo.tabpfn.predict_rows", len(test))
            span.set_data("secondo.tabpfn.n_estimators", self.n_estimators)
            span.set_data("secondo.tabpfn.device", self.device)
            model = self._regressor()
            model.fit(train[FEATURES].to_numpy(), train["target"].to_numpy())
            # One forward pass yields both the mean and the quantiles.
            main = model.predict(
                test[FEATURES].to_numpy(), output_type="main", quantiles=[0.1, 0.9]
            )
            mean, (p10, p90) = main["mean"], main["quantiles"]
        log.info(
            "TabPFN: %d train rows, %d predictions in %.1fs",
            len(train),
            len(test),
            time.perf_counter() - started,
        )

        out: dict[date, dict[str, dict[str, float]]] = {}
        for i, (d, pid) in enumerate(zip(test["date"], test["product_id"], strict=True)):
            out.setdefault(d, {})[pid] = {
                "mean": max(0.0, float(mean[i])),
                "p10": max(0.0, float(p10[i])),
                "p90": max(0.0, float(p90[i])),
            }
        return out

    def predict(self, history: pd.DataFrame, target: date, product_ids: list[str]):
        preds = self.predict_days(history[history.index < target], [target], product_ids)
        return {pid: preds[target][pid]["mean"] for pid in product_ids}
