from datetime import date

import pytest
from pydantic import ValidationError

from app.services.catalog import ProductCatalog
from app.services.extraction import ExtractedItem, RuleBasedExtractor, resolve_date
from tests.conftest import TODAY


@pytest.fixture
def catalog(repo, business):
    return ProductCatalog(repo.list_products(business.id))


def extract(text, catalog):
    return RuleBasedExtractor().extract(text, catalog, TODAY)


def test_extracts_products_quantities_date_and_name(catalog):
    result = extract(
        "Hi! Can I get 2 sourdough loaves and a dozen croissants for Saturday? "
        "Eggless if possible. Pickup by 10am.\n- Priya",
        catalog,
    )
    quantities = {i.product_id: i.quantity for i in result.items}
    assert quantities == {"sourdough-loaf": 2, "butter-croissant": 12}
    assert result.order_date == date(2026, 10, 10)
    assert result.customer_name == "Priya"
    assert result.dietary_constraints == ["eggless"]
    assert "Pickup by 10am" in result.notes
    assert result.provider == "rules"
    assert result.confidence == 1.0


def test_longest_product_phrase_wins(catalog):
    result = extract("3 chocolate chip cookies and one chocolate cake tomorrow", catalog)
    quantities = {i.product_id: i.quantity for i in result.items}
    assert quantities == {"chocolate-chip-cookie": 3, "chocolate-cake-1kg": 1}


def test_missing_quantity_and_date_lower_confidence(catalog):
    result = extract("Do you have banana bread?", catalog)
    assert result.items[0].quantity == 1
    assert result.order_date is None
    assert result.confidence < 0.7
    assert any("assumed 1" in w for w in result.warnings)
    assert any("No date" in w for w in result.warnings)


def test_unrecognised_message_yields_no_items(catalog):
    result = extract("Are you open on Diwali?", catalog)
    assert result.items == [] and result.confidence == 0.0


@pytest.mark.parametrize(
    "text,expected",
    [
        ("tomorrow", date(2026, 10, 5)),
        ("day after tomorrow", date(2026, 10, 6)),
        ("this Sunday", date(2026, 10, 11)),  # today is Sunday: means next week
        ("on 12th oct", date(2026, 10, 12)),
        ("on 2 jan", date(2027, 1, 2)),
        ("for 15/10", date(2026, 10, 15)),
        ("2026-11-01", date(2026, 11, 1)),
        ("whenever", None),
    ],
)
def test_resolve_date(text, expected):
    assert resolve_date(text, TODAY) == expected


def test_extracted_item_schema_rejects_bad_quantity():
    with pytest.raises(ValidationError):
        ExtractedItem(product_id="x", product_name="X", mention="x", quantity=0, matched=True)
