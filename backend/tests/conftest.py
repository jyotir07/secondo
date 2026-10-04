from dataclasses import replace
from datetime import date
from pathlib import Path

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
    )


@pytest.fixture
def repo():
    return SQLiteRepository(":memory:")


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
