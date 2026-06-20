"""Celery task: generate a game via the AI Agent Harness."""

import asyncio
import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def generate_game_task(self, task_id: str, game_id: str, user_prompt: str, asset_ids: list[str]):
    """
    Celery task that orchestrates the full AI game generation pipeline.

    This task:
    1. Loads the game & assets from the database
    2. Runs the GameGenerationHarness pipeline
    3. Updates the task/game records with results
    """
    logger.info(f"Starting game generation: task={task_id}, game={game_id}")

    try:
        # Run the async pipeline in a sync context
        result = asyncio.run(_run_pipeline(task_id, game_id, user_prompt, asset_ids))
        return {"status": "completed", "url": result}
    except Exception as exc:
        logger.error(f"Game generation failed: task={task_id}, error={exc}", exc_info=True)

        # Update task to failed
        asyncio.run(_mark_failed(task_id, str(exc)))

        # Retry once if it's a transient error
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return {"status": "failed", "error": str(exc)}


async def _run_pipeline(
    task_id: str, game_id: str, user_prompt: str, asset_ids: list[str]
) -> str:
    """Run the AI Agent Harness pipeline."""
    from app.database import async_session
    from app.agent.harness import GameGenerationHarness
    from app.agent.adapters import create_adapter
    from app.services import task_service, game_service, storage_service

    # Create the LLM adapter
    adapter = create_adapter()

    # Create the harness
    harness = GameGenerationHarness(adapter)

    # Run the pipeline
    result_url = await harness.run(
        task_id=task_id,
        game_id=game_id,
        user_prompt=user_prompt,
        asset_ids=asset_ids,
    )

    return result_url


async def _mark_failed(task_id: str, error_message: str):
    """Mark a task as failed in the database."""
    from app.database import async_session
    from app.services import task_service, game_service

    async with async_session() as db:
        task = await task_service.get_task(db, task_id)
        if task:
            await task_service.update_task_progress(
                db,
                task_id,
                progress=0,
                status="failed",
                error_message=error_message,
            )
            # Also update the game status
            game = await game_service.get_game(db, task.game_id)
            if game:
                game.status = "failed"
                await db.commit()
