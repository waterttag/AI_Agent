"""API router aggregation."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.games import router as games_router
from app.api.tasks import router as tasks_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(games_router)
api_router.include_router(tasks_router)
