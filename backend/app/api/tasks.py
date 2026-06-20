"""Task API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.task import TaskResponse, TaskLogResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get generation task status and progress."""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your task")
    return TaskResponse.model_validate(task)


@router.get("/games/{game_id}", response_model=list[TaskResponse])
async def list_tasks(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all generation tasks for a game."""
    tasks = await task_service.list_tasks_for_game(db, game_id)
    return [TaskResponse.model_validate(t) for t in tasks if t.user_id == current_user.id]


@router.get("/games/{game_id}/log", response_model=TaskLogResponse)
async def get_task_log(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the agent execution log for the latest generation task of a game."""
    tasks = await task_service.list_tasks_for_game(db, game_id)
    user_tasks = [t for t in tasks if t.user_id == current_user.id]
    if not user_tasks:
        raise HTTPException(status_code=404, detail="No generation tasks found")

    latest = user_tasks[0]  # Already sorted by created_at desc

    steps = []
    if latest.system_prompt_used:
        steps.append("Preprocess: Context assembled with system prompt")
    if latest.started_at:
        steps.append(f"Generate: LLM call started at {latest.started_at.isoformat()}")
    if latest.completed_at:
        steps.append(f"Package: Completed at {latest.completed_at.isoformat()}")
    if latest.result_oss_url:
        steps.append(f"Upload: Stored at {latest.result_oss_url}")

    return TaskLogResponse(
        task_id=latest.id,
        status=latest.status,
        progress=latest.progress,
        prompt_summary=latest.user_prompt_used[:200] if latest.user_prompt_used else None,
        agent_steps=steps,
        started_at=latest.started_at,
        completed_at=latest.completed_at,
    )
