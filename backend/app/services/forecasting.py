"""Demand forecasting.

History is a wide frame: one row per *open* business day, one column per product, values are
units sold. Days with no sales of anything are treated as closed and dropped, so a weekly
closing day does not drag averages down. Before a product's first sale the value is NaN.

Every provider sees only rows strictly before the date it predicts; the backtest enforces this
by slicing history per evaluated day (rolling origin).
"""

from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.models import Order, OrderStatus

REALIZED = {OrderStatus.COMPLETED, OrderStatus.CONFIRMED, OrderStatus.PENDING}


def build_history(orders: list[Order], product_ids: list[str], before: date) -> pd.DataFrame:
    rows = [
        (o.order_date, o.product_id, o.quantity)
        for o in orders
        if o.status in REALIZED and o.order_date < before and o.product_id in product_ids
    ]
    if not rows:
        return pd.DataFrame(columns=product_ids, dtype=float)
    df = pd.DataFrame(rows, columns=["date", "product_id", "quantity"])
    wide = df.pivot_table(index="date", columns="product_id", values="quantity", aggfunc="sum")
    wide = wide.reindex(columns=product_ids).sort_index().fillna(0.0)
    for pid in product_ids:
        sold = wide.index[wide[pid] > 0]
        if len(sold):
            wide.loc[wide.index < sold[0], pid] = np.nan
        else:
            wide[pid] = np.nan
    wide.index = pd.Index([pd.Timestamp(d).date() for d in wide.index], name="date")
    return wide.astype(float)


def same_weekday(history: pd.DataFrame, pid: str, target: date, n: int = 4) -> pd.Series:
    series = history[pid].dropna()
    mask = [d.weekday() == target.weekday() for d in series.index]
    return series[mask].tail(n)


def is_usually_closed(history: pd.DataFrame, target: date, weeks: int = 8) -> bool:
    if history.empty:
        return False
    first, last = history.index[0], history.index[-1]
    if (last - first).days < weeks * 7:
        return False
    window_start = last - timedelta(weeks=weeks)
    recent = [d for d in history.index if d > window_start]
    return not any(d.weekday() == target.weekday() for d in recent)


class ForecastProvider(Protocol):
    name: str
    label: str
    description: str

    def predict(
        self, history: pd.DataFrame, target: date, product_ids: list[str]
    ) -> dict[str, float]: ...


class HistoricalAverage:
    name = "historical_average"
    label = "Historical average"
    description = "Mean daily units over the last 28 open days, ignoring the day of the week."

    def __init__(self, window: int = 28):
        self.window = window

    def predict(self, history, target, product_ids):
        out = {}
        for pid in product_ids:
            series = history[pid].dropna().tail(self.window) if pid in history else pd.Series()
            out[pid] = float(series.mean()) if len(series) else 0.0
        return out


class WeekdayAverage:
    name = "weekday_average"
    label = "Weekday average"
    description = (
        "Mean units on the same weekday over the last 4 weeks. Falls back to the historical "
        "average when fewer than 2 same-weekday observations exist."
    )

    def __init__(self, weeks: int = 4):
        self.weeks = weeks
        self.fallback = HistoricalAverage()

    def predict(self, history, target, product_ids):
        fallback = self.fallback.predict(history, target, product_ids)
        out = {}
        for pid in product_ids:
            obs = same_weekday(history, pid, target, self.weeks) if pid in history else []
            out[pid] = float(obs.mean()) if len(obs) >= 2 else fallback[pid]
        return out


class ProductMetrics(BaseModel):
    product_id: str
    mae: float
    wape: float | None
    bias: float
    n: int


class ProviderMetrics(BaseModel):
    provider: str
    label: str
    mae: float
    wape: float | None
    bias: float
    by_product: dict[str, ProductMetrics]


class BacktestPoint(BaseModel):
    date: date
    product_id: str
    actual: float
    predictions: dict[str, float]


class EvaluationReport(BaseModel):
    method: str
    history_start: date | None
    history_end: date | None
    open_days: int
    observations: int
    holdout_start: date | None
    holdout_end: date | None
    holdout_days: int
    metrics: list[ProviderMetrics]
    points: list[BacktestPoint]
    sufficient_data: bool
    notes: list[str]


def _metrics(errors: np.ndarray, actuals: np.ndarray) -> tuple[float, float | None, float]:
    mae = float(np.mean(np.abs(errors)))
    total = float(np.sum(actuals))
    wape = float(np.sum(np.abs(errors)) / total) if total > 0 else None
    bias = float(np.mean(errors))
    return round(mae, 3), (round(wape, 4) if wape is not None else None), round(bias, 3)


MIN_TRAIN_DAYS = 21


def backtest(
    history: pd.DataFrame, providers: list[ForecastProvider], holdout_days: int = 14
) -> EvaluationReport:
    product_ids = list(history.columns)
    open_days = list(history.index)
    method = (
        f"Rolling-origin backtest over the last {holdout_days} open days: for each day, every "
        "model predicts using only sales strictly before that day, then is compared to what "
        "actually sold."
    )
    base = dict(
        method=method,
        history_start=open_days[0] if open_days else None,
        history_end=open_days[-1] if open_days else None,
        open_days=len(open_days),
        observations=int(history.notna().sum().sum()) if len(history) else 0,
    )
    if len(open_days) < MIN_TRAIN_DAYS + holdout_days:
        return EvaluationReport(
            **base,
            holdout_start=None,
            holdout_end=None,
            holdout_days=0,
            metrics=[],
            points=[],
            sufficient_data=False,
            notes=[
                f"Need at least {MIN_TRAIN_DAYS + holdout_days} open days of sales to evaluate; "
                f"have {len(open_days)}."
            ],
        )

    holdout = open_days[-holdout_days:]
    points: list[BacktestPoint] = []
    for day in holdout:
        train = history[history.index < day]
        preds = {p.name: p.predict(train, day, product_ids) for p in providers}
        for pid in product_ids:
            actual = history.at[day, pid]
            if pd.isna(actual):
                continue
            points.append(
                BacktestPoint(
                    date=day,
                    product_id=pid,
                    actual=float(actual),
                    predictions={name: round(v[pid], 3) for name, v in preds.items()},
                )
            )

    metrics = []
    for p in providers:
        errs = np.array([pt.predictions[p.name] - pt.actual for pt in points])
        acts = np.array([pt.actual for pt in points])
        mae, wape, bias = _metrics(errs, acts)
        by_product = {}
        for pid in product_ids:
            sel = [i for i, pt in enumerate(points) if pt.product_id == pid]
            if not sel:
                continue
            pmae, pwape, pbias = _metrics(errs[sel], acts[sel])
            by_product[pid] = ProductMetrics(
                product_id=pid, mae=pmae, wape=pwape, bias=pbias, n=len(sel)
            )
        metrics.append(
            ProviderMetrics(
                provider=p.name, label=p.label, mae=mae, wape=wape, bias=bias,
                by_product=by_product,
            )
        )  # fmt: skip

    return EvaluationReport(
        **base,
        holdout_start=holdout[0],
        holdout_end=holdout[-1],
        holdout_days=len(holdout),
        metrics=metrics,
        points=points,
        sufficient_data=True,
        notes=[
            "Bias > 0 means the model over-predicts on average (risk of waste); "
            "bias < 0 means it under-predicts (risk of selling out).",
        ],
    )
