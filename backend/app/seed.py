"""Starter bakery catalogue, created on first run so the app is usable immediately.

Prices and recipes are illustrative defaults for a small home bakery, not real figures.
"""

from app.config import Settings
from app.models import Business, IngredientRequirement, Product
from app.repository import Repository

Ing = IngredientRequirement

STARTER_PRODUCTS: list[dict] = [
    {
        "id": "sourdough-loaf",
        "name": "Sourdough Loaf",
        "category": "bread",
        "selling_price": 220,
        "aliases": ["sourdough", "sour dough", "sourdough bread"],
        "ingredient_requirements": [
            Ing(ingredient="Bread flour", quantity=0.45, unit="kg"),
            Ing(ingredient="Salt", quantity=0.009, unit="kg"),
        ],
    },
    {
        "id": "butter-croissant",
        "name": "Butter Croissant",
        "category": "pastry",
        "selling_price": 90,
        "aliases": ["croissant", "croissants", "butter croissants"],
        "ingredient_requirements": [
            Ing(ingredient="All-purpose flour", quantity=0.06, unit="kg"),
            Ing(ingredient="Butter", quantity=0.035, unit="kg"),
        ],
    },
    {
        "id": "chocolate-chip-cookie",
        "name": "Chocolate Chip Cookie",
        "category": "cookie",
        "selling_price": 60,
        "aliases": ["cookie", "cookies", "choc chip cookie", "choco chip cookie"],
        "ingredient_requirements": [
            Ing(ingredient="All-purpose flour", quantity=0.03, unit="kg"),
            Ing(ingredient="Butter", quantity=0.015, unit="kg"),
            Ing(ingredient="Sugar", quantity=0.02, unit="kg"),
            Ing(ingredient="Chocolate chips", quantity=0.015, unit="kg"),
        ],
    },
    {
        "id": "cinnamon-roll",
        "name": "Cinnamon Roll",
        "category": "pastry",
        "selling_price": 120,
        "aliases": ["cinnamon rolls", "cinnamon bun", "cinnamon buns"],
        "ingredient_requirements": [
            Ing(ingredient="All-purpose flour", quantity=0.08, unit="kg"),
            Ing(ingredient="Butter", quantity=0.02, unit="kg"),
            Ing(ingredient="Sugar", quantity=0.025, unit="kg"),
        ],
    },
    {
        "id": "banana-bread",
        "name": "Banana Bread Loaf",
        "category": "bread",
        "selling_price": 350,
        "aliases": ["banana bread", "banana loaf"],
        "ingredient_requirements": [
            Ing(ingredient="All-purpose flour", quantity=0.25, unit="kg"),
            Ing(ingredient="Sugar", quantity=0.15, unit="kg"),
            Ing(ingredient="Butter", quantity=0.1, unit="kg"),
            Ing(ingredient="Bananas", quantity=3, unit="pcs"),
        ],
    },
    {
        "id": "chocolate-cake-1kg",
        "name": "Chocolate Cake (1 kg)",
        "category": "cake",
        "selling_price": 900,
        "aliases": ["chocolate cake", "choco cake", "cake", "birthday cake"],
        "ingredient_requirements": [
            Ing(ingredient="All-purpose flour", quantity=0.35, unit="kg"),
            Ing(ingredient="Sugar", quantity=0.3, unit="kg"),
            Ing(ingredient="Butter", quantity=0.2, unit="kg"),
            Ing(ingredient="Cocoa powder", quantity=0.08, unit="kg"),
        ],
    },
]


def ensure_seeded(repo: Repository, settings: Settings) -> Business:
    business = repo.get_business()
    if business:
        return business
    business = Business(
        name=settings.business_name,
        business_type="home_bakery",
        timezone=settings.business_timezone,
        currency=settings.business_currency,
    )
    repo.save_business(business)
    for spec in STARTER_PRODUCTS:
        repo.save_product(Product(business_id=business.id, **spec))
    return business
