"""Persistence behind a small interface so a MongoDB adapter can be swapped in later.

Each entity is stored as a validated JSON document plus the few columns we filter on.
That keeps the SQLite schema trivially portable to a document store.
"""

import sqlite3
import threading
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.models import Business, Customer, Forecast, KitchenPlan, Order, Product

M = TypeVar("M", bound=BaseModel)


class Repository(Protocol):
    def describe(self) -> dict[str, str]: ...

    def get_business(self) -> Business | None: ...
    def save_business(self, business: Business) -> None: ...

    def list_products(self, business_id: str) -> list[Product]: ...
    def get_product(self, product_id: str) -> Product | None: ...
    def save_product(self, product: Product) -> None: ...

    def list_customers(self, business_id: str) -> list[Customer]: ...
    def get_customer(self, customer_id: str) -> Customer | None: ...
    def save_customer(self, customer: Customer) -> None: ...

    def list_orders(
        self, business_id: str, start: date | None = None, end: date | None = None
    ) -> list[Order]: ...
    def existing_dedupe_keys(self, business_id: str, keys: Iterable[str]) -> set[str]: ...
    def insert_orders(self, orders: list[Order]) -> None: ...

    def save_forecasts(self, forecasts: list[Forecast]) -> None: ...
    def list_forecasts(
        self, business_id: str, target_date: date | None = None
    ) -> list[Forecast]: ...

    def save_plan(self, plan: KitchenPlan) -> None: ...
    def get_plan(self, plan_id: str) -> KitchenPlan | None: ...
    def list_plans(self, business_id: str) -> list[KitchenPlan]: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, order_date TEXT NOT NULL,
    dedupe_key TEXT NOT NULL, data TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS orders_dedupe ON orders (business_id, dedupe_key);
CREATE INDEX IF NOT EXISTS orders_date ON orders (business_id, order_date);
CREATE TABLE IF NOT EXISTS forecasts (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, target_date TEXT NOT NULL,
    created_at TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kitchen_plans (
    id TEXT PRIMARY KEY, business_id TEXT NOT NULL, target_date TEXT NOT NULL,
    created_at TEXT NOT NULL, data TEXT NOT NULL);
"""


class SQLiteRepository:
    def __init__(self, path: Path | str):
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    def describe(self) -> dict[str, str]:
        return {"backend": "sqlite", "location": self._path}

    def _fetch(self, model: type[M], sql: str, params: tuple = ()) -> list[M]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [model.model_validate_json(row[0]) for row in rows]

    def _fetch_one(self, model: type[M], sql: str, params: tuple) -> M | None:
        found = self._fetch(model, sql, params)
        return found[0] if found else None

    def _write(self, sql: str, params: list[tuple]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(sql, params)

    def get_business(self) -> Business | None:
        return self._fetch_one(Business, "SELECT data FROM businesses LIMIT 1", ())

    def save_business(self, business: Business) -> None:
        self._write(
            "INSERT OR REPLACE INTO businesses (id, data) VALUES (?, ?)",
            [(business.id, business.model_dump_json())],
        )

    def list_products(self, business_id: str) -> list[Product]:
        products = self._fetch(
            Product, "SELECT data FROM products WHERE business_id = ?", (business_id,)
        )
        return sorted(products, key=lambda p: p.name)

    def get_product(self, product_id: str) -> Product | None:
        return self._fetch_one(Product, "SELECT data FROM products WHERE id = ?", (product_id,))

    def save_product(self, product: Product) -> None:
        self._write(
            "INSERT OR REPLACE INTO products (id, business_id, data) VALUES (?, ?, ?)",
            [(product.id, product.business_id, product.model_dump_json())],
        )

    def list_customers(self, business_id: str) -> list[Customer]:
        return self._fetch(
            Customer, "SELECT data FROM customers WHERE business_id = ?", (business_id,)
        )

    def get_customer(self, customer_id: str) -> Customer | None:
        return self._fetch_one(Customer, "SELECT data FROM customers WHERE id = ?", (customer_id,))

    def save_customer(self, customer: Customer) -> None:
        self._write(
            "INSERT OR REPLACE INTO customers (id, business_id, data) VALUES (?, ?, ?)",
            [(customer.id, customer.business_id, customer.model_dump_json())],
        )

    def list_orders(
        self, business_id: str, start: date | None = None, end: date | None = None
    ) -> list[Order]:
        sql = "SELECT data FROM orders WHERE business_id = ?"
        params: list = [business_id]
        if start:
            sql += " AND order_date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND order_date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY order_date DESC, rowid DESC"
        return self._fetch(Order, sql, tuple(params))

    def existing_dedupe_keys(self, business_id: str, keys: Iterable[str]) -> set[str]:
        keys = list(keys)
        found: set[str] = set()
        # Chunked to stay under SQLite's bound-parameter limit on large imports.
        for i in range(0, len(keys), 500):
            chunk = keys[i : i + 500]
            placeholders = ",".join("?" * len(chunk))
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT dedupe_key FROM orders WHERE business_id = ? "
                    f"AND dedupe_key IN ({placeholders})",
                    (business_id, *chunk),
                ).fetchall()
            found.update(r[0] for r in rows)
        return found

    def insert_orders(self, orders: list[Order]) -> None:
        self._write(
            "INSERT INTO orders (id, business_id, order_date, dedupe_key, data) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (o.id, o.business_id, o.order_date.isoformat(), o.dedupe_key, o.model_dump_json())
                for o in orders
            ],
        )

    def save_forecasts(self, forecasts: list[Forecast]) -> None:
        self._write(
            "INSERT OR REPLACE INTO forecasts (id, business_id, target_date, created_at, data) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    f.id,
                    f.business_id,
                    f.target_date.isoformat(),
                    f.created_at.isoformat(),
                    f.model_dump_json(),
                )
                for f in forecasts
            ],
        )

    def list_forecasts(self, business_id: str, target_date: date | None = None) -> list[Forecast]:
        sql = "SELECT data FROM forecasts WHERE business_id = ?"
        params: list = [business_id]
        if target_date:
            sql += " AND target_date = ?"
            params.append(target_date.isoformat())
        sql += " ORDER BY created_at DESC"
        return self._fetch(Forecast, sql, tuple(params))

    def save_plan(self, plan: KitchenPlan) -> None:
        self._write(
            "INSERT OR REPLACE INTO kitchen_plans (id, business_id, target_date, created_at, data) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    plan.id,
                    plan.business_id,
                    plan.target_date.isoformat(),
                    plan.created_at.isoformat(),
                    plan.model_dump_json(),
                )
            ],
        )

    def get_plan(self, plan_id: str) -> KitchenPlan | None:
        return self._fetch_one(
            KitchenPlan, "SELECT data FROM kitchen_plans WHERE id = ?", (plan_id,)
        )

    def list_plans(self, business_id: str) -> list[KitchenPlan]:
        return self._fetch(
            KitchenPlan,
            "SELECT data FROM kitchen_plans WHERE business_id = ? "
            "ORDER BY target_date DESC, created_at DESC",
            (business_id,),
        )
