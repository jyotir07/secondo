from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import forecasts, orders, plans, system
from app.config import Settings, load_settings
from app.container import Container
from app.observability import init_sentry
from app.repository import Repository, SQLiteRepository


def open_repository(settings: Settings) -> Repository:
    """MongoDB Atlas when MONGODB_URI is set (hosted), otherwise a local SQLite file."""
    if settings.mongodb_uri:
        from app.repository_mongo import MongoRepository  # noqa: PLC0415

        return MongoRepository(settings.mongodb_uri)
    return SQLiteRepository(settings.database_path)


def create_app(
    settings: Settings | None = None, repo: Repository | None = None, clock=None
) -> FastAPI:
    settings = settings or load_settings()
    init_sentry(settings)
    repo = repo or open_repository(settings)

    app = FastAPI(title="SECONDO API", version="0.1.0")
    app.state.container = Container(settings, repo, clock=clock)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (system, orders, forecasts, plans):
        app.include_router(module.router, prefix="/api")
    return app
