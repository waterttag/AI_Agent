"""Admin API routes — for seeding and internal operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.game import Game
from app.models.task import GenerationTask
from app.schemas.game import GameResponse
from app.schemas.task import TaskResponse
from app.services import game_service, task_service

router = APIRouter(prefix="/admin", tags=["Admin"])


class InjectGameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    html_content: str = Field(..., min_length=100)
    author_username: str = Field(default="democreator")


@router.post("/inject-game", response_model=GameResponse)
async def inject_game(data: InjectGameRequest, db: AsyncSession = Depends(get_db)):
    """Inject a pre-built HTML game directly into the platform.

    Creates a published game + completed generation task with the given HTML.
    Intended for seeding seed games without running the AI pipeline.
    """
    # Find or create author
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.username == data.author_username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{data.author_username}' not found. Register first.")

    # Create game as published
    game = Game(
        title=data.title,
        description=data.description,
        tags=data.tags,
        author_id=user.id,
        status="published",
        prompt_text="Pre-built seed game",
        game_url=f"/api/games/GAME_ID_PLACEHOLDER/play-html",
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)

    # Update game_url with real ID
    game.game_url = f"/api/games/{game.id}/play-html"

    # Create a completed generation task with the HTML
    task = GenerationTask(
        game_id=game.id,
        user_id=user.id,
        status="completed",
        progress=100,
        user_prompt_used="Seed game injection",
        llm_response_raw=data.html_content,
        result_oss_url=f"/api/games/{game.id}/play-html",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Re-fetch with relations
    game = await game_service.get_game(db, game.id)
    resp = GameResponse.model_validate(game)
    if game.author:
        resp.author_name = game.author.username
    return resp
