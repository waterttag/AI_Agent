"""FastAPI application entry point — serves API + frontend SPA."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import engine, Base
from app.utils.minio_client import ensure_bucket
from app.api import api_router

# Locate frontend build directory
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # MinIO bucket creation is optional (may not be available in prod)
    try:
        ensure_bucket()
    except Exception:
        pass
    yield
    await engine.dispose()


app = FastAPI(
    title="AI Native Game Platform",
    description="AI-powered interactive game generation and distribution platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Serve Frontend SPA (production) ---
if _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve frontend SPA — all non-API routes go to index.html."""
        file_path = _FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def root():
        return {
            "name": "AI Native Game Platform",
            "version": "0.1.0",
            "docs": "/docs",
            "tip": "Frontend not built. Run: cd frontend && npm run build",
        }
