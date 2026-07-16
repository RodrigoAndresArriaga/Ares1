# aggregate Phase 1/3/4 API routes under /api
from fastapi import APIRouter

from app.api.routes import health, missions, retrieval, simulation

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(simulation.router)
api_router.include_router(missions.router)
api_router.include_router(retrieval.router)
