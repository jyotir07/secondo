from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.models import Order, OrderSource, OrderStatus
from app.services.forecasting import (
    HistoricalAverage,
    WeekdayAverage,
    backtest,
    build_history,
    is_usually_closed,
)


def order(d: date, pid: str, qty: int, status=OrderStatus.COMPLETED) -> Order:
    return Order(
        business_id="b", product_id=pid, quantity=qty, order_date=d, status=status,
        source=OrderSource.CSV_IMPORT, dedupe_key=f"{d}{pid}{qty}{status}",
    )  # fmt: skip


def test_history_drops_closed_days_and_masks_before_first_sale():
    d0 = date(2026, 9, 1)
    orders = [
        order(d0, "a", 5),
        order(d0 + timedelta(days=2), "a", 7),
        order(d0 + timedelta(days=2), "b", 3),
        order(d0 + timedelta(days=3), "b", 2, OrderStatus.CANCELLED),
        order(d0 + timedelta(days=9), "a", 99),  # on/after cut-off: excluded
    ]
    h = build_history(orders, ["a", "b"], before=d0 + timedelta(days=9))
    assert list(h.index) == [d0, d0 + timedelta(days=2)]  # day 1 and cancelled-only day 3 gone
    assert np.isnan(h.at[d0, "b"])  # b not sold yet
    assert h.at[d0 + timedelta(days=2), "a"] == 7


def frame(values: dict[date, float]) -> pd.DataFrame:
    return pd.DataFrame({"p": list(values.values())}, index=list(values.keys()))


def test_weekday_average_uses_last_four_same_weekdays():
    start = date(2026, 8, 3)  # Monday
    history = frame({start + timedelta(days=i): float(10 if i % 7 == 5 else 2) for i in range(42)})
    target = start + timedelta(days=47)  # a Saturday
    assert WeekdayAverage().predict(history, target, ["p"])["p"] == 10
    assert HistoricalAverage().predict(history, target, ["p"])["p"] == pytest.approx(
        history["p"].tail(28).mean()
    )


def test_weekday_average_falls_back_with_little_history():
    history = frame({date(2026, 9, 1): 4.0, date(2026, 9, 2): 6.0})
    assert WeekdayAverage().predict(history, date(2026, 9, 8), ["p"])["p"] == 5.0


def test_closed_weekday_detection():
    start = date(2026, 6, 2)  # Tuesday
    days = [start + timedelta(days=i) for i in range(70) if (start + timedelta(days=i)).weekday()]
    history = frame({d: 1.0 for d in days})
    assert is_usually_closed(history, date(2026, 10, 5))  # Monday
    assert not is_usually_closed(history, date(2026, 10, 6))


class Spy:
    name = "spy"
    label = "Spy"
    description = ""

    def __init__(self):
        self.calls = []

    def predict(self, history, target, product_ids):
        assert history.empty or max(history.index) < target, "future data leaked into training"
        self.calls.append(target)
        return {pid: 1.0 for pid in product_ids}


def test_backtest_never_trains_on_future_and_computes_metrics():
    start = date(2026, 6, 1)
    history = frame({start + timedelta(days=i): float(i % 3) for i in range(40)})
    spy = Spy()
    report = backtest(history, [spy], holdout_days=14)
    assert report.sufficient_data
    assert len(spy.calls) == 14 and spy.calls[0] == start + timedelta(days=26)

    actual = history["p"].tail(14).to_numpy()
    errors = 1.0 - actual
    m = report.metrics[0]
    assert m.mae == pytest.approx(np.mean(np.abs(errors)), abs=1e-3)
    assert m.bias == pytest.approx(np.mean(errors), abs=1e-3)
    assert m.wape == pytest.approx(np.abs(errors).sum() / actual.sum(), abs=1e-3)


def test_backtest_reports_insufficient_data():
    history = frame({date(2026, 9, 1) + timedelta(days=i): 1.0 for i in range(10)})
    report = backtest(history, [HistoricalAverage()])
    assert not report.sufficient_data and report.metrics == []
