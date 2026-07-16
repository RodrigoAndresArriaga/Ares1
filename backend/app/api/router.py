# aggregate Phase 1/3 API routes under /api
from fastapi import APIRouter

from app.api.routes import health, missions, simulation

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(simulation.router)
api_router.include_router(missions.router)
