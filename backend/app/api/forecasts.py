from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_container
from app.api.schemas import ForecastResponse, ForecastRunRequest, HistoryPoint
from app.container import Container
from app.services.forecasting import EvaluationReport

router = APIRouter(prefix="/forecasts")


def _history_points(c: Container, days: int) -> list[HistoryPoint]:
    history = c.demand().history(c.today())
    if history.empty:
        return []
    recent = history[history.index >= history.index[-1] - timedelta(days=days)]
    return [
        HistoryPoint(date=d, product_id=pid, quantity=float(q))
        for d, row in recent.iterrows()
        for pid, q in row.items()
        if q == q  # skip NaN (before the product's first sale)
    ]


@router.get("")
def get_forecasts(
    target_date: date | None = None,
    history_days: int = Query(default=56, ge=7, le=365),
    c: Container = Depends(get_container),
) -> ForecastResponse:
    demand = c.demand()
    forecasts = c.repo.list_forecasts(c.business.id, target_date)
    if forecasts and target_date is None:
        target_date = forecasts[0].target_date
        forecasts = [f for f in forecasts if f.target_date == target_date]
    # Keep only the most recent run for each product.
    latest = {}
    for f in forecasts:
        latest.setdefault(f.product_id, f)
    return ForecastResponse(
        target_date=target_date,
        model_name=demand.provider.name,
        model_label=demand.provider.label,
        baseline_name=demand.baseline.name,
        forecasts=list(latest.values()),
        history=_history_points(c, history_days),
    )


@router.post("/run")
def run_forecasts(
    body: ForecastRunRequest, c: Container = Depends(get_container)
) -> ForecastResponse:
    today = c.today()
    demand = c.demand()
    target = body.target_date or demand.next_open_day(today)
    forecasts = demand.forecast(target, today)
    return ForecastResponse(
        target_date=target,
        model_name=demand.provider.name,
        model_label=demand.provider.label,
        baseline_name=demand.baseline.name,
        forecasts=forecasts,
        history=_history_points(c, 56),
    )


@router.get("/evaluation")
def evaluation(c: Container = Depends(get_container)) -> EvaluationReport:
    return c.demand().evaluate(c.today())
