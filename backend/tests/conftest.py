import os
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import SAMPLE_SALES_CSV, load_settings
from app.main import create_app
from app.repository import SQLiteRepository
from app.seed import ensure_seeded

# 2026-10-04 is a Sunday; the synthetic history ends the day before.
TODAY = date(2026, 10, 4)


@pytest.fixture
def settings():
    return replace(
        load_settings(),
        database_path=Path(":memory:"),
        extraction_provider="rules",
        forecast_provider="weekday_average",
        sentry_dsn=None,  # a developer's backend/.env must not make tests report to Sentry
        mongodb_uri=None,  # the repo fixture decides the backend explicitly
    )


@pytest.fixture
def repo():
    # SECONDO_TEST_BACKEND=mongodb runs the whole suite against MONGODB_URI, one throwaway
    # database per test.
    if os.getenv("SECONDO_TEST_BACKEND") == "mongodb":
        from app.repository_mongo import MongoRepository

        database = f"secondo_test_{uuid4().hex[:12]}"
        mongo = MongoRepository(os.environ["MONGODB_URI"], database=database)
        yield mongo
        # Atlas "read and write" roles may not drop databases; dropping every collection is
        # allowed and Atlas removes the empty database itself.
        for name in mongo._db.list_collection_names():
            mongo._db.drop_collection(name)
        mongo.close()
    else:
        yield SQLiteRepository(":memory:")


@pytest.fixture
def business(repo, settings):
    return ensure_seeded(repo, settings)


@pytest.fixture
def client(settings, repo):
    app = create_app(settings=settings, repo=repo, clock=lambda: TODAY)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_csv() -> bytes:
    return SAMPLE_SALES_CSV.read_bytes()
