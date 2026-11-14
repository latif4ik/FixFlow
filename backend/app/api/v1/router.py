from fastapi import APIRouter

from app.api.v1 import (
    assignments,
    audit,
    auth,
    catalog,
    estimates,
    health,
    inventory,
    notifications,
    org,
    properties,
    requests,
    technicians,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(org.router)
api_router.include_router(catalog.router)
api_router.include_router(technicians.router)
api_router.include_router(properties.router)
api_router.include_router(properties.assets_router)
api_router.include_router(audit.router)
api_router.include_router(requests.router)
api_router.include_router(requests.files_router)
api_router.include_router(assignments.router)
api_router.include_router(estimates.router)
api_router.include_router(notifications.router)
api_router.include_router(inventory.router)
