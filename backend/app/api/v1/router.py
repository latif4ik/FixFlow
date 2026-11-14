from fastapi import APIRouter

from app.api.v1 import audit, auth, catalog, health, org, properties, technicians

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(org.router)
api_router.include_router(catalog.router)
api_router.include_router(technicians.router)
api_router.include_router(properties.router)
api_router.include_router(properties.assets_router)
api_router.include_router(audit.router)
