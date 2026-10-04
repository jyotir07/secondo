import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from pydantic import BaseModel

from app.models import Business, Customer, Order, OrderSource, OrderStatus
from app.repository import Repository
from app.services.catalog import ProductCatalog, normalize

MAX_CSV_BYTES = 5 * 1024 * 1024
# Day-first formats only: an Indian bakery's spreadsheet will not be month-first,
# and accepting both would make 03/04 silently ambiguous.
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")

_COLUMN_ALIASES = {
    "date": ("date", "order_date", "sale_date"),
    "quantity": ("quantity_sold", "quantity", "qty"),
    "product_id": ("product_id",),
    "product_name": ("product_name", "product", "item"),
    "customer": ("customer", "customer_name"),
    "notes": ("notes", "note"),
    "status": ("status",),
}


class CsvFormatError(ValueError):
    pass


class DuplicateOrderError(ValueError):
    pass


class RowError(BaseModel):
    line: int
    message: str


class ImportResult(BaseModel):
    total_rows: int
    imported: int
    duplicates: int
    skipped_zero_quantity: int
    errors: list[RowError]
    first_date: date | None = None
    last_date: date | None = None


@dataclass
class OrderDraft:
    product_id: str
    quantity: int
    order_date: date
    source: OrderSource
    status: OrderStatus
    customer_name: str | None = None
    dietary_constraints: list[str] = field(default_factory=list)
    notes: str | None = None
    original_input: str | None = None
    extraction_confidence: float | None = None


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{value}' (use YYYY-MM-DD or DD/MM/YYYY)")


def default_status(order_date: date, today: date) -> OrderStatus:
    return OrderStatus.COMPLETED if order_date <= today else OrderStatus.CONFIRMED


def dedupe_key(business_id: str, draft: OrderDraft) -> str:
    parts = [
        business_id,
        draft.order_date.isoformat(),
        draft.product_id,
        normalize(draft.customer_name or ""),
        str(draft.quantity),
        normalize(draft.original_input or ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _resolve_columns(header: list[str]) -> dict[str, str]:
    present = {h.strip().lower(): h for h in header if h}
    resolved = {}
    for canonical, options in _COLUMN_ALIASES.items():
        for option in options:
            if option in present:
                resolved[canonical] = present[option]
                break
    missing = [c for c in ("date", "quantity") if c not in resolved]
    if "product_id" not in resolved and "product_name" not in resolved:
        missing.append("product_name or product_id")
    if missing:
        raise CsvFormatError(f"CSV is missing required column(s): {', '.join(missing)}")
    return resolved


def _parse_quantity(value: str) -> int:
    number = float(value.strip())
    if number != int(number):
        raise ValueError(f"quantity must be a whole number, got '{value}'")
    if number < 0:
        raise ValueError(f"quantity cannot be negative, got '{value}'")
    return int(number)


def parse_sales_csv(
    content: bytes, catalog: ProductCatalog, today: date
) -> tuple[list[OrderDraft], list[RowError], int, int]:
    """Returns (drafts, row errors, zero-quantity rows skipped, total data rows)."""
    if len(content) > MAX_CSV_BYTES:
        raise CsvFormatError("CSV is larger than 5 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvFormatError("CSV is empty")
    cols = _resolve_columns(list(reader.fieldnames))

    drafts: list[OrderDraft] = []
    errors: list[RowError] = []
    skipped = 0
    total = 0
    for row in reader:
        line = reader.line_num
        if not any((v or "").strip() for v in row.values()):
            continue
        total += 1

        def cell(name: str, row=row) -> str:
            return (row.get(cols[name]) or "").strip() if name in cols else ""

        try:
            order_date = parse_date(cell("date"))
            quantity = _parse_quantity(cell("quantity"))
        except ValueError as exc:
            errors.append(RowError(line=line, message=str(exc)))
            continue

        product = catalog.match(cell("product_id")) if cell("product_id") else None
        if product is None and cell("product_name"):
            product = catalog.match(cell("product_name"))
        if product is None:
            label = cell("product_name") or cell("product_id")
            hint = catalog.suggest(label)
            message = f"unknown product '{label}'"
            if hint:
                message += f" (did you mean '{hint}'?)"
            errors.append(RowError(line=line, message=message))
            continue

        if quantity == 0:
            skipped += 1
            continue

        status = default_status(order_date, today)
        if cell("status"):
            try:
                status = OrderStatus(cell("status").lower())
            except ValueError:
                errors.append(RowError(line=line, message=f"invalid status '{cell('status')}'"))
                continue

        drafts.append(
            OrderDraft(
                product_id=product.id,
                quantity=quantity,
                order_date=order_date,
                source=OrderSource.CSV_IMPORT,
                status=status,
                customer_name=cell("customer") or None,
                notes=cell("notes") or None,
                original_input=",".join((v or "").strip() for v in row.values()),
            )
        )
    return drafts, errors, skipped, total


class IngestionService:
    def __init__(self, repo: Repository, business: Business):
        self.repo = repo
        self.business = business
        self._customers: dict[str, Customer] | None = None

    def catalog(self) -> ProductCatalog:
        return ProductCatalog(self.repo.list_products(self.business.id))

    def _resolve_customer(self, name: str | None, dietary: list[str]) -> str | None:
        if not name:
            return None
        if self._customers is None:
            self._customers = {
                normalize(c.display_name): c for c in self.repo.list_customers(self.business.id)
            }
        key = normalize(name)
        customer = self._customers.get(key)
        is_new = customer is None
        if customer is None:
            customer = Customer(business_id=self.business.id, display_name=name.strip())
            self._customers[key] = customer
        new_constraints = [d for d in dietary if d not in customer.dietary_constraints]
        if is_new or new_constraints:
            customer.dietary_constraints.extend(new_constraints)
            self.repo.save_customer(customer)
        return customer.id

    def create_orders(
        self, drafts: list[OrderDraft], allow_duplicates: bool = False
    ) -> tuple[list[Order], int]:
        """Persist drafts, skipping duplicates. Returns (created orders, duplicate count)."""
        keyed = []
        seen: set[str] = set()
        for d in drafts:
            key = dedupe_key(self.business.id, d)
            if allow_duplicates:
                # Salt the key so a deliberate repeat order is stored alongside the original.
                key = hashlib.sha256(f"{key}|{datetime.now().isoformat()}|{len(keyed)}".encode())
                key = key.hexdigest()
            keyed.append((key, d))
        existing = self.repo.existing_dedupe_keys(self.business.id, [k for k, _ in keyed])

        orders: list[Order] = []
        duplicates = 0
        for key, d in keyed:
            if key in existing or key in seen:
                duplicates += 1
                continue
            seen.add(key)
            orders.append(
                Order(
                    business_id=self.business.id,
                    customer_id=self._resolve_customer(d.customer_name, d.dietary_constraints),
                    product_id=d.product_id,
                    quantity=d.quantity,
                    order_date=d.order_date,
                    status=d.status,
                    source=d.source,
                    original_input=d.original_input,
                    extraction_confidence=d.extraction_confidence,
                    notes=d.notes,
                    dedupe_key=key,
                )
            )
        if orders:
            self.repo.insert_orders(orders)
        return orders, duplicates

    def import_csv(self, content: bytes, today: date) -> ImportResult:
        drafts, errors, skipped, total = parse_sales_csv(content, self.catalog(), today)
        orders, duplicates = self.create_orders(drafts)
        dates = [d.order_date for d in drafts]
        return ImportResult(
            total_rows=total,
            imported=len(orders),
            duplicates=duplicates,
            skipped_zero_quantity=skipped,
            errors=errors,
            first_date=min(dates) if dates else None,
            last_date=max(dates) if dates else None,
        )
