"""Games API routes."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, get_optional_user
from app.models.user import User
from app.schemas.game import (
    GameCreate,
    GameUpdate,
    GameResponse,
    GameListResponse,
    GameAssetResponse,
    GenerateRequest,
)
from app.schemas.task import TaskResponse
from app.services import game_service, storage_service, task_service
from app.config import settings

router = APIRouter(prefix="/games", tags=["Games"])


@router.post("", response_model=GameResponse, status_code=status.HTTP_201_CREATED)
async def create_game(
    data: GameCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new game draft."""
    game = await game_service.create_game(db, current_user.id, data)
    # Re-fetch with eager-loaded assets to avoid lazy-loading greenlet error
    game = await game_service.get_game(db, game.id)
    resp = GameResponse.model_validate(game)
    resp.author_name = current_user.username
    return resp


@router.get("", response_model=GameListResponse)
async def list_games(
    status: str = Query(default="published"),
    tag: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List published games with optional tag filter."""
    return await game_service.list_games(db, status=status, tag=tag, page=page, size=size)


@router.get("/{game_id}", response_model=GameResponse)
async def get_game(game_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single game by ID."""
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    resp = GameResponse.model_validate(game)
    if game.author:
        resp.author_name = game.author.username
    # Increment play count
    game.play_count = (game.play_count or 0) + 1
    await db.commit()
    return resp


@router.put("/{game_id}", response_model=GameResponse)
async def update_game(
    game_id: str,
    data: GameUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update game metadata. Only the author may update."""
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your game")

    updated = await game_service.update_game(db, game_id, data)
    return GameResponse.model_validate(updated)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a game. Only the author may delete."""
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your game")

    await game_service.delete_game(db, game_id)


# --- Assets ---

@router.post("/{game_id}/assets", response_model=GameAssetResponse)
async def upload_asset(
    game_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload an asset (image/audio) for a game."""
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your game")

    # Determine asset type
    mime = file.content_type or ""
    if mime.startswith("image/"):
        asset_type = "image"
    elif mime.startswith("audio/"):
        asset_type = "audio"
    else:
        asset_type = "reference"

    oss_key, oss_url = await storage_service.upload_file(file, game_id)
    file_size = file.size

    asset = await game_service.add_asset(
        db, game_id, asset_type, file.filename or "unknown", oss_key, oss_url, file_size
    )
    return GameAssetResponse.model_validate(asset)


@router.get("/{game_id}/assets", response_model=list[GameAssetResponse])
async def list_assets(game_id: str, db: AsyncSession = Depends(get_db)):
    """List all assets for a game."""
    assets = await game_service.get_assets(db, game_id)
    return [GameAssetResponse.model_validate(a) for a in assets]


@router.delete("/{game_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    game_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an asset."""
    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your game")

    deleted = await game_service.delete_asset(db, asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Asset not found")


# --- Generation ---

@router.post("/{game_id}/generate", response_model=TaskResponse)
async def generate_game(
    game_id: str,
    data: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start AI game generation. Uses Celery if available, falls back to in-process."""
    if settings.llm_provider == "none" or not settings.llm_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI generation is not configured. Set LLM_PROVIDER and LLM_API_KEY in .env to enable.",
        )

    game = await game_service.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your game")

    # Update game status and prompt
    game.status = "generating"
    game.prompt_text = data.prompt_text

    # Collect asset IDs
    asset_ids = [a.id for a in game.assets]

    # Create task record
    task = await task_service.create_task(
        db,
        game_id=game_id,
        user_id=current_user.id,
        prompt_text=data.prompt_text,
        config={"model_preference": data.model_preference},
    )

    await db.commit()

    # Try Celery first, fall back to in-process background task
    try:
        from app.tasks.game_gen import generate_game_task
        generate_game_task.delay(
            task_id=str(task.id),
            game_id=str(game_id),
            user_prompt=data.prompt_text,
            asset_ids=asset_ids,
        )
    except Exception:
        # Celery/Redis not available — run in-process via background thread
        import asyncio
        import threading
        from app.agent.harness import GameGenerationHarness
        from app.agent.adapters import create_adapter

        def _run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                GameGenerationHarness(create_adapter()).run(
                    task_id=str(task.id),
                    game_id=str(game_id),
                    user_prompt=data.prompt_text,
                    asset_ids=asset_ids,
                )
            )
        threading.Thread(target=_run_in_thread, daemon=True).start()

    return TaskResponse.model_validate(task)


# --- Play HTML (direct serve, no MinIO fallback) ---
from fastapi.responses import HTMLResponse

@router.get("/{game_id}/play-html", response_class=HTMLResponse)
async def play_game_html(game_id: str, db: AsyncSession = Depends(get_db)):
    """Serve the generated game HTML directly (no MinIO required)."""
    from sqlalchemy import select
    from app.models.task import GenerationTask

    # Find the most recent completed task for this game
    result = await db.execute(
        select(GenerationTask)
        .where(GenerationTask.game_id == game_id, GenerationTask.status == "completed")
        .order_by(GenerationTask.completed_at.desc())
        .limit(1)
    )
    task = result.scalar_one_or_none()

    if not task or not task.llm_response_raw:
        raise HTTPException(status_code=404, detail="No generated HTML found for this game")

    return HTMLResponse(content=task.llm_response_raw)
