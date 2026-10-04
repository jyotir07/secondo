import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
SAMPLE_SALES_CSV = REPO_DIR / "sample_data" / "synthetic_bakery_sales.csv"

load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_path: Path
    business_name: str
    business_timezone: str
    business_currency: str
    extraction_provider: str  # auto | ollama | rules
    ollama_url: str
    ollama_model: str
    ollama_timeout_s: float
    forecast_provider: str
    cors_origins: list[str]
    mongodb_uri: str | None = None
    sentry_dsn: str | None = None
    sentry_environment: str = "local"
    sentry_traces_sample_rate: float = 1.0


def load_settings() -> Settings:
    db_path = Path(os.getenv("SECONDO_DB_PATH", str(BACKEND_DIR / "data" / "secondo.db")))
    return Settings(
        database_path=db_path,
        business_name=os.getenv("SECONDO_BUSINESS_NAME", "Neighbourhood Bakery"),
        business_timezone=os.getenv("SECONDO_BUSINESS_TIMEZONE", "Asia/Kolkata"),
        business_currency=os.getenv("SECONDO_BUSINESS_CURRENCY", "INR"),
        extraction_provider=os.getenv("EXTRACTION_PROVIDER", "auto").lower(),
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "gemma3:4b"),
        ollama_timeout_s=float(os.getenv("OLLAMA_TIMEOUT_S", "60")),
        forecast_provider=os.getenv("FORECAST_PROVIDER", "tabpfn"),
        mongodb_uri=os.getenv("MONGODB_URI") or None,
        sentry_dsn=os.getenv("SENTRY_DSN") or None,
        sentry_environment=os.getenv("SENTRY_ENVIRONMENT", "local"),
        sentry_traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
        cors_origins=[
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ],
    )
