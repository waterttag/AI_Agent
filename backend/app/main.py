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

# Locate frontend build directory — handles local dev and Docker paths
_BASE = Path(__file__).resolve().parent.parent.parent  # project root
_FRONTEND_DIST = _BASE / "frontend" / "dist"
_SEED_DIR = _BASE / "seed" / "games"
# In Docker, the backend lives at /app/ (one level up is project root)
if not (_FRONTEND_DIST / "index.html").exists():
    _DOCKER_BASE = Path(__file__).resolve().parent.parent  # /app (Docker WORKDIR)
    _FRONTEND_DIST = _DOCKER_BASE / "frontend" / "dist"
    _SEED_DIR = _DOCKER_BASE / "seed" / "games"

_SEED_GAMES = [
    {"title": "Classic Snake", "description": "Control a growing snake, eat red apples, and avoid crashing into yourself. A timeless arcade classic reimagined for the browser.", "tags": ["arcade","classic","snake"], "file": "snake.html"},
    {"title": "Memory Match", "description": "Flip cards and find matching pairs of cute emojis. Test your memory with 8 pairs to discover. Track your moves and beat your best time!", "tags": ["puzzle","memory","casual"], "file": "memory.html"},
    {"title": "Breakout Blitz", "description": "Destroy all the colorful bricks with your ball and paddle. Classic brick-breaker action with vibrant visuals and satisfying gameplay.", "tags": ["arcade","classic","breakout"], "file": "breakout.html"},
]


async def _auto_seed():
    """Ensure demo user and seed games exist after deploy."""
    from app.database import async_session
    from sqlalchemy import select, func
    from app.models.user import User
    from app.models.game import Game
    from app.models.task import GenerationTask
    from app.utils.security import hash_password

    async with async_session() as db:
        result = await db.execute(select(func.count()).select_from(Game).where(Game.status == "published"))
        count = result.scalar() or 0
        if count > 0:
            return  # Already seeded

        # Create demo user if missing
        result = await db.execute(select(User).where(User.email == "demo@aigame.dev"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(username="democreator", email="demo@aigame.dev", password_hash=hash_password("demo123"), role="creator")
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # Inject seed games
        for seed in _SEED_GAMES:
            html_path = _SEED_DIR / seed["file"]
            if not html_path.exists():
                continue
            html_content = html_path.read_text(encoding="utf-8")

            game = Game(title=seed["title"], description=seed["description"], tags=seed["tags"],
                        author_id=user.id, status="published", prompt_text="Pre-built seed game")
            db.add(game)
            await db.commit()
            await db.refresh(game)

            game.game_url = f"/api/games/{game.id}/play-html"
            task = GenerationTask(game_id=game.id, user_id=user.id, status="completed", progress=100,
                                  user_prompt_used="Seed game injection", llm_response_raw=html_content,
                                  result_oss_url=f"/api/games/{game.id}/play-html")
            db.add(task)
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Auto-seed on fresh deploy
    try:
        await _auto_seed()
    except Exception:
        pass
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
