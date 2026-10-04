from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(UTC)


class Business(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    business_type: str
    timezone: str
    currency: str
    created_at: datetime = Field(default_factory=utc_now)


class IngredientRequirement(BaseModel):
    ingredient: str = Field(min_length=1)
    quantity: float = Field(gt=0, description="Amount needed per unit of product")
    unit: str = Field(min_length=1)


class Product(BaseModel):
    id: str = Field(default_factory=new_id)
    business_id: str
    name: str = Field(min_length=1, max_length=120)
    category: str = "general"
    selling_price: float = Field(ge=0)
    ingredient_requirements: list[IngredientRequirement] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    active: bool = True


class Customer(BaseModel):
    id: str = Field(default_factory=new_id)
    business_id: str
    display_name: str = Field(min_length=1, max_length=120)
    preferences: list[str] = Field(default_factory=list)
    dietary_constraints: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderSource(StrEnum):
    CSV_IMPORT = "csv_import"
    MANUAL = "manual"
    MESSAGE = "message"


class Order(BaseModel):
    id: str = Field(default_factory=new_id)
    business_id: str
    customer_id: str | None = None
    product_id: str
    quantity: int = Field(gt=0, le=10_000)
    order_date: date
    status: OrderStatus
    source: OrderSource
    original_input: str | None = None
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None
    dedupe_key: str
    created_at: datetime = Field(default_factory=utc_now)


class Forecast(BaseModel):
    id: str = Field(default_factory=new_id)
    business_id: str
    product_id: str
    target_date: date
    predicted_quantity: float
    model_name: str
    baseline_quantity: float
    evaluation_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class PlanStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class KitchenPlanItem(BaseModel):
    product_id: str
    product_name: str
    predicted_quantity: float
    baseline_quantity: float
    typical_error: float | None = None
    confirmed_quantity: int
    recommended_quantity: int
    final_quantity: int = Field(ge=0)
    explanation: str


class PlanWarning(BaseModel):
    severity: str  # info | warning
    message: str
    product_id: str | None = None


class IngredientNeed(BaseModel):
    ingredient: str
    unit: str
    quantity: float


class CustomerRequest(BaseModel):
    order_id: str
    customer_name: str | None
    product_name: str
    quantity: int
    dietary_constraints: list[str] = Field(default_factory=list)
    notes: str | None = None


class KitchenPlan(BaseModel):
    id: str = Field(default_factory=new_id)
    business_id: str
    target_date: date
    items: list[KitchenPlanItem]
    explanations: list[str] = Field(default_factory=list)
    warnings: list[PlanWarning] = Field(default_factory=list)
    ingredient_needs: list[IngredientNeed] = Field(default_factory=list)
    customer_requests: list[CustomerRequest] = Field(default_factory=list)
    model_name: str
    status: PlanStatus = PlanStatus.DRAFT
    review_note: str | None = None
    approved_at: datetime | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
