from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import get_container
from app.api.schemas import (
    ExtractRequest,
    OrderCreate,
    OrderCreateResult,
    OrderList,
    OrderView,
)
from app.config import SAMPLE_SALES_CSV
from app.container import Container
from app.models import Order, OrderSource, OrderStatus
from app.services.extraction import ExtractionResult
from app.services.ingestion import (
    MAX_CSV_BYTES,
    CsvFormatError,
    ImportResult,
    OrderDraft,
    default_status,
)

router = APIRouter(prefix="/orders")


def to_views(c: Container, orders: list[Order]) -> list[OrderView]:
    products = {p.id: p.name for p in c.repo.list_products(c.business.id)}
    customers = {cu.id: cu.display_name for cu in c.repo.list_customers(c.business.id)}
    return [
        OrderView(
            **o.model_dump(include=set(OrderView.model_fields) & set(Order.model_fields)),
            product_name=products.get(o.product_id, o.product_id),
            customer_name=customers.get(o.customer_id) if o.customer_id else None,
        )
        for o in orders
    ]


@router.get("")
def list_orders(
    start: date | None = None,
    end: date | None = None,
    product_id: str | None = None,
    source: OrderSource | None = None,
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    c: Container = Depends(get_container),
) -> OrderList:
    if start and end and start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start must be before end")
    orders = c.repo.list_orders(c.business.id, start=start, end=end)
    orders = [
        o
        for o in orders
        if (product_id is None or o.product_id == product_id)
        and (source is None or o.source == source)
        and (order_status is None or o.status == order_status)
    ]
    return OrderList(total=len(orders), orders=to_views(c, orders[offset : offset + limit]))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(body: OrderCreate, c: Container = Depends(get_container)) -> OrderCreateResult:
    ingestion = c.ingestion()
    catalog = ingestion.catalog()
    unknown = [line.product_id for line in body.items if line.product_id not in catalog.by_id]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown product id(s): {', '.join(unknown)}"
        )
    order_status = body.status or default_status(body.order_date, c.today())
    drafts = [
        OrderDraft(
            product_id=line.product_id,
            quantity=line.quantity,
            order_date=body.order_date,
            source=body.source,
            status=order_status,
            customer_name=body.customer_name,
            dietary_constraints=body.dietary_constraints,
            notes=body.notes,
            original_input=body.original_input,
            extraction_confidence=body.extraction_confidence,
        )
        for line in body.items
    ]
    created, duplicates = ingestion.create_orders(drafts, allow_duplicates=body.allow_duplicate)
    if not created:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This looks like a duplicate of an order already saved. "
            "Resubmit with allow_duplicate to save it anyway.",
        )
    return OrderCreateResult(created=to_views(c, created), duplicates=duplicates)


@router.post("/import")
async def import_orders(
    file: UploadFile = File(...), c: Container = Depends(get_container)
) -> ImportResult:
    content = await file.read(MAX_CSV_BYTES + 1)
    try:
        return c.ingestion().import_csv(content, c.today())
    except CsvFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/sample-csv")
def sample_csv() -> FileResponse:
    if not SAMPLE_SALES_CSV.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample data has not been generated.")
    return FileResponse(SAMPLE_SALES_CSV, media_type="text/csv", filename=SAMPLE_SALES_CSV.name)


@router.post("/extract")
def extract(body: ExtractRequest, c: Container = Depends(get_container)) -> ExtractionResult:
    return c.extraction.extract(body.text, c.ingestion().catalog(), c.today())
