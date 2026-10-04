from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.deps import get_container
from app.api.schemas import ProductCreate
from app.container import Container
from app.models import Business, Product, utc_now
from app.services.catalog import normalize
from app.services.demand import available_providers

router = APIRouter()


@router.get("/health")
def health(c: Container = Depends(get_container)) -> dict:
    return {"status": "ok", "database": c.repo.describe()["backend"], "today": c.today()}


@router.get("/business")
def business(c: Container = Depends(get_container)) -> Business:
    return c.business


@router.get("/products")
def list_products(c: Container = Depends(get_container)) -> list[Product]:
    return c.repo.list_products(c.business.id)


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, c: Container = Depends(get_container)) -> Product:
    existing = {normalize(p.name) for p in c.repo.list_products(c.business.id)}
    if normalize(body.name) in existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A product named '{body.name}' exists.")
    product = Product(business_id=c.business.id, **body.model_dump())
    c.repo.save_product(product)
    return product


@router.get("/export")
def export(c: Container = Depends(get_container)) -> JSONResponse:
    """Everything SECONDO stores for this business, as one JSON file the owner keeps."""
    bid = c.business.id
    data = {
        "exported_at": utc_now(),
        "business": c.business,
        "products": c.repo.list_products(bid),
        "customers": c.repo.list_customers(bid),
        "orders": c.repo.list_orders(bid),
        "forecasts": c.repo.list_forecasts(bid),
        "kitchen_plans": c.repo.list_plans(bid),
    }
    filename = f"secondo-export-{c.today().isoformat()}.json"
    return JSONResponse(
        jsonable_encoder(data),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/settings/providers")
def providers(c: Container = Depends(get_container)) -> dict:
    demand = c.demand()
    return {
        "mode": "local",
        "extraction": c.extraction.status(),
        "forecasting": {
            "configured": c.settings.forecast_provider,
            "active": demand.provider.name,
            "active_label": demand.provider.label,
            "baseline": demand.baseline.name,
            "fallback_reason": demand.fallback_reason,
            "available": [
                {"name": p.name, "label": p.label, "description": p.description}
                for p in available_providers().values()
            ],
        },
        "database": c.repo.describe(),
        "narration": c.narration.status(),
        "business": {"timezone": c.business.timezone, "today": c.today()},
    }
