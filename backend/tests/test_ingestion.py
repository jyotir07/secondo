import pytest

from app.models import OrderStatus
from app.services.catalog import ProductCatalog
from app.services.ingestion import CsvFormatError, IngestionService, parse_sales_csv
from tests.conftest import TODAY


@pytest.fixture
def catalog(repo, business):
    return ProductCatalog(repo.list_products(business.id))


def test_parses_valid_rows_and_resolves_products(catalog):
    csv = (
        b"date,product_name,quantity_sold\n2026-09-01,Sourdough Loaf,12\n02/09/2026,croissants,30\n"
    )
    drafts, errors, skipped, total = parse_sales_csv(csv, catalog, TODAY)
    assert errors == []
    assert total == 2 and skipped == 0
    assert [d.product_id for d in drafts] == ["sourdough-loaf", "butter-croissant"]
    assert drafts[1].order_date.isoformat() == "2026-09-02"  # day-first
    assert all(d.status == OrderStatus.COMPLETED for d in drafts)


def test_future_rows_are_confirmed_preorders(catalog):
    csv = b"date,product_id,quantity\n2026-10-10,banana-bread,2\n"
    drafts, *_ = parse_sales_csv(csv, catalog, TODAY)
    assert drafts[0].status == OrderStatus.CONFIRMED


def test_missing_required_column_is_rejected(catalog):
    with pytest.raises(CsvFormatError, match="quantity"):
        parse_sales_csv(b"date,product_name\n2026-09-01,Sourdough Loaf\n", catalog, TODAY)


def test_invalid_rows_are_reported_with_line_numbers(catalog):
    csv = (
        b"date,product_name,quantity_sold\n"
        b"not-a-date,Sourdough Loaf,1\n"
        b"2026-09-01,Sourdough Loaf,-3\n"
        b"2026-09-01,Sourdough Loaf,2.5\n"
        b"2026-09-01,Sourdouhg Loaf,2\n"
        b"2026-09-01,Sourdough Loaf,0\n"
        b"2026-09-01,Sourdough Loaf,4\n"
    )
    drafts, errors, skipped, total = parse_sales_csv(csv, catalog, TODAY)
    assert total == 6
    assert len(drafts) == 1 and skipped == 1
    assert [e.line for e in errors] == [2, 3, 4, 5]
    assert "did you mean 'Sourdough Loaf'" in errors[3].message


def test_non_utf8_is_rejected(catalog):
    with pytest.raises(CsvFormatError, match="UTF-8"):
        parse_sales_csv("date,product,qty\n2026-09-01,Café,1\n".encode("utf-16"), catalog, TODAY)


def test_reimporting_same_file_detects_duplicates(repo, business, sample_csv):
    service = IngestionService(repo, business)
    first = service.import_csv(sample_csv, TODAY)
    assert first.imported == first.total_rows > 500
    assert first.errors == []

    second = service.import_csv(sample_csv, TODAY)
    assert second.imported == 0
    assert second.duplicates == first.total_rows
    assert len(repo.list_orders(business.id)) == first.imported


def test_duplicate_rows_within_one_file_are_detected(repo, business):
    row = b"2026-09-01,Sourdough Loaf,4\n"
    csv = b"date,product_name,quantity_sold\n" + row + row
    result = IngestionService(repo, business).import_csv(csv, TODAY)
    assert result.imported == 1 and result.duplicates == 1
