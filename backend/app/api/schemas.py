from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import (
    Forecast,
    IngredientRequirement,
    OrderSource,
    OrderStatus,
)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = "general"
    selling_price: float = Field(ge=0)
    ingredient_requirements: list[IngredientRequirement] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class OrderView(BaseModel):
    id: str
    order_date: date
    product_id: str
    product_name: str
    quantity: int
    customer_id: str | None
    customer_name: str | None
    status: OrderStatus
    source: OrderSource
    notes: str | None
    original_input: str | None
    extraction_confidence: float | None
    created_at: datetime


class OrderList(BaseModel):
    total: int
    orders: list[OrderView]


class OrderLine(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=10_000)


class OrderCreate(BaseModel):
    order_date: date
    items: list[OrderLine] = Field(min_length=1, max_length=50)
    customer_name: str | None = Field(default=None, max_length=120)
    dietary_constraints: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=1000)
    source: OrderSource = OrderSource.MANUAL
    status: OrderStatus | None = None
    original_input: str | None = Field(default=None, max_length=5000)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    allow_duplicate: bool = False


class OrderCreateResult(BaseModel):
    created: list[OrderView]
    duplicates: int


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ForecastRunRequest(BaseModel):
    target_date: date | None = None


class HistoryPoint(BaseModel):
    date: date
    product_id: str
    quantity: float


class ForecastResponse(BaseModel):
    target_date: date | None
    model_name: str
    model_label: str
    baseline_name: str
    forecasts: list[Forecast]
    history: list[HistoryPoint]


class PlanGenerateRequest(BaseModel):
    target_date: date | None = None


class PlanReview(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class PlanModify(BaseModel):
    quantities: dict[str, int]
    note: str | None = Field(default=None, max_length=1000)
