"""MongoDB (Atlas) implementation of the Repository interface.

Documents are the same validated JSON shape the SQLite adapter stores, with `_id` set to the
entity id. Dates are ISO strings (YYYY-MM-DD), so range filters and sorting compare correctly
as strings.
"""

import time
from collections.abc import Iterable
from datetime import date
from typing import TypeVar

from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, MongoClient, ReplaceOne
from pymongo.uri_parser import parse_uri

from app.models import Business, Customer, Forecast, KitchenPlan, Order, Product

M = TypeVar("M", bound=BaseModel)
DEFAULT_DATABASE = "secondo"


class MongoRepository:
    def __init__(self, uri: str, database: str | None = None, timeout_ms: int = 8000):
        parsed = parse_uri(uri)
        self._client: MongoClient = MongoClient(
            uri, serverSelectionTimeoutMS=timeout_ms, appname="secondo"
        )
        self._db = self._client[database or parsed.get("database") or DEFAULT_DATABASE]
        # Never expose credentials: Settings shows only the cluster address and database.
        cluster = uri.rsplit("@", 1)[-1].split("/", 1)[0].split("?", 1)[0]
        self._location = f"{cluster}/{self._db.name}"
        # Fail at startup with a clear error rather than on the first request.
        self._client.admin.command("ping")
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self._db.products.create_index([("business_id", ASCENDING)])
        self._db.customers.create_index([("business_id", ASCENDING)])
        self._db.orders.create_index(
            [("business_id", ASCENDING), ("dedupe_key", ASCENDING)], unique=True
        )
        self._db.orders.create_index([("business_id", ASCENDING), ("order_date", DESCENDING)])
        self._db.forecasts.create_index(
            [("business_id", ASCENDING), ("target_date", ASCENDING), ("created_at", DESCENDING)]
        )
        self._db.kitchen_plans.create_index(
            [("business_id", ASCENDING), ("target_date", DESCENDING)]
        )

    def describe(self) -> dict[str, str]:
        return {"backend": "mongodb", "location": self._location}

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _doc(model: BaseModel, **extra) -> dict:
        return {"_id": model.id, **model.model_dump(mode="json"), **extra}

    @staticmethod
    def _load(model: type[M], docs) -> list[M]:
        # Pydantic ignores the storage-only fields (_id, _seq).
        return [model.model_validate(d) for d in docs]

    def _upsert(self, collection: str, model: BaseModel) -> None:
        self._db[collection].replace_one({"_id": model.id}, self._doc(model), upsert=True)

    def get_business(self) -> Business | None:
        doc = self._db.businesses.find_one()
        return Business.model_validate(doc) if doc else None

    def save_business(self, business: Business) -> None:
        self._upsert("businesses", business)

    def list_products(self, business_id: str) -> list[Product]:
        products = self._load(Product, self._db.products.find({"business_id": business_id}))
        return sorted(products, key=lambda p: p.name)

    def get_product(self, product_id: str) -> Product | None:
        doc = self._db.products.find_one({"_id": product_id})
        return Product.model_validate(doc) if doc else None

    def save_product(self, product: Product) -> None:
        self._upsert("products", product)

    def list_customers(self, business_id: str) -> list[Customer]:
        return self._load(Customer, self._db.customers.find({"business_id": business_id}))

    def get_customer(self, customer_id: str) -> Customer | None:
        doc = self._db.customers.find_one({"_id": customer_id})
        return Customer.model_validate(doc) if doc else None

    def save_customer(self, customer: Customer) -> None:
        self._upsert("customers", customer)

    def list_orders(
        self, business_id: str, start: date | None = None, end: date | None = None
    ) -> list[Order]:
        query: dict = {"business_id": business_id}
        if start or end:
            query["order_date"] = {}
            if start:
                query["order_date"]["$gte"] = start.isoformat()
            if end:
                query["order_date"]["$lte"] = end.isoformat()
        cursor = self._db.orders.find(query).sort(
            [("order_date", DESCENDING), ("_seq", DESCENDING)]
        )
        return self._load(Order, cursor)

    def existing_dedupe_keys(self, business_id: str, keys: Iterable[str]) -> set[str]:
        keys = list(keys)
        found: set[str] = set()
        for i in range(0, len(keys), 1000):
            cursor = self._db.orders.find(
                {"business_id": business_id, "dedupe_key": {"$in": keys[i : i + 1000]}},
                {"dedupe_key": 1},
            )
            found.update(d["dedupe_key"] for d in cursor)
        return found

    def insert_orders(self, orders: list[Order]) -> None:
        if not orders:
            return
        # _seq preserves insertion order, the tie-breaker SQLite gets from rowid.
        base = time.time_ns()
        self._db.orders.insert_many(
            [self._doc(o, _seq=base + i) for i, o in enumerate(orders)], ordered=True
        )

    def save_forecasts(self, forecasts: list[Forecast]) -> None:
        if forecasts:
            self._db.forecasts.bulk_write(
                [ReplaceOne({"_id": f.id}, self._doc(f), upsert=True) for f in forecasts]
            )

    def list_forecasts(self, business_id: str, target_date: date | None = None) -> list[Forecast]:
        query: dict = {"business_id": business_id}
        if target_date:
            query["target_date"] = target_date.isoformat()
        return self._load(Forecast, self._db.forecasts.find(query).sort("created_at", DESCENDING))

    def save_plan(self, plan: KitchenPlan) -> None:
        self._upsert("kitchen_plans", plan)

    def get_plan(self, plan_id: str) -> KitchenPlan | None:
        doc = self._db.kitchen_plans.find_one({"_id": plan_id})
        return KitchenPlan.model_validate(doc) if doc else None

    def list_plans(self, business_id: str) -> list[KitchenPlan]:
        cursor = self._db.kitchen_plans.find({"business_id": business_id}).sort(
            [("target_date", DESCENDING), ("created_at", DESCENDING)]
        )
        return self._load(KitchenPlan, cursor)
