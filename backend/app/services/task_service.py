"""Generation task business logic."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import GenerationTask


async def create_task(
    db: AsyncSession,
    game_id: str,
    user_id: str,
    prompt_text: str,
    config: dict | None = None,
) -> GenerationTask:
    """Create a new generation task."""
    task = GenerationTask(
        game_id=game_id,
        user_id=user_id,
        status="pending",
        progress=0,
        user_prompt_used=prompt_text,
        config=config or {},
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str) -> GenerationTask | None:
    """Get a task by ID."""
    result = await db.execute(
        select(GenerationTask).where(GenerationTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def list_tasks_for_game(db: AsyncSession, game_id: str) -> list[GenerationTask]:
    """List all tasks for a game, newest first."""
    result = await db.execute(
        select(GenerationTask)
        .where(GenerationTask.game_id == game_id)
        .order_by(GenerationTask.created_at.desc())
    )
    return list(result.scalars().all())


async def update_task_progress(
    db: AsyncSession,
    task_id: str,
    progress: int,
    status: str = "processing",
    result_oss_url: str | None = None,
    error_message: str | None = None,
    llm_response_raw: str | None = None,
    system_prompt_used: str | None = None,
) -> GenerationTask | None:
    """Update task progress and optionally mark as completed/failed."""
    task = await get_task(db, task_id)
    if not task:
        return None

    task.progress = progress
    task.status = status

    if status == "processing" and task.started_at is None:
        task.started_at = datetime.now(timezone.utc)

    if status in ("completed", "failed"):
        task.completed_at = datetime.now(timezone.utc)

    if result_oss_url is not None:
        task.result_oss_url = result_oss_url
    if error_message is not None:
        task.error_message = error_message
    if llm_response_raw is not None:
        task.llm_response_raw = llm_response_raw
    if system_prompt_used is not None:
        task.system_prompt_used = system_prompt_used

    await db.commit()
    await db.refresh(task)
    return task
