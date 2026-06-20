"""AI Agent Harness — orchestrates the game generation pipeline.

Preprocess → Generate → Validate → Fix (if needed) → Package → Upload

This is the core differentiator of the platform:
- Pluggable LLM adapters (Claude / OpenAI / future models)
- Vision API for asset description injection
- Automatic validation with retry-on-failure
- Single-file HTML bundling for MinIO storage/playback
"""

import logging

from app.agent.adapters.base import LLMAdapter
from app.agent.generators.html5_game import HTML5GameGenerator, GameGenerationContext
from app.agent.processors.validator import GameValidator
from app.agent.processors.packager import GamePackager

logger = logging.getLogger(__name__)


class GameGenerationHarness:
    """
    Orchestrates the full pipeline: Preprocess → Generate → Postprocess → Upload.

    Usage:
        adapter = create_adapter()  # ClaudeAdapter or OpenAIAdapter
        harness = GameGenerationHarness(adapter)
        result_url = await harness.run(task_id, game_id, user_prompt, asset_ids)
    """

    def __init__(self, adapter: LLMAdapter):
        self.adapter = adapter
        self.generator = HTML5GameGenerator(adapter)
        self.validator = GameValidator()
        self.packager = GamePackager()

    async def run(
        self,
        task_id: str,
        game_id: str,
        user_prompt: str,
        asset_ids: list[str] | None = None,
    ) -> str:
        """
        Run the complete game generation pipeline.

        Args:
            task_id: UUID of the GenerationTask
            game_id: UUID of the Game
            user_prompt: Natural language game description
            asset_ids: List of GameAsset UUIDs to include

        Returns:
            Public MinIO URL of the playable game
        """
        logger.info(f"[{task_id}] Starting generation pipeline for game {game_id}")

        # ====== PHASE 1: PREPROCESS ======
        logger.info(f"[{task_id}] Phase 1: Preprocessing")
        await self._update_progress(task_id, 10, "processing")

        asset_descriptions = await self._preprocess_assets(asset_ids or [])

        context = GameGenerationContext(
            user_prompt=user_prompt,
            asset_descriptions=asset_descriptions,
            game_id=game_id,
        )

        # ====== PHASE 2: GENERATE ======
        logger.info(f"[{task_id}] Phase 2: Generating game via LLM")
        await self._update_progress(task_id, 30, "processing")

        html_code = await self.generator.generate(context)

        await self._update_progress(task_id, 70, "processing")

        # ====== PHASE 3: POSTPROCESS ======
        logger.info(f"[{task_id}] Phase 3: Validating and packaging")

        # Validate
        validation = self.validator.validate(html_code)

        if not validation.is_valid:
            logger.warning(
                f"[{task_id}] Validation failed: {validation.errors}. Attempting auto-fix."
            )
            # Auto-fix: send errors back to LLM
            try:
                html_code = await self.generator.fix_errors(
                    html_code, validation.errors
                )
                # Re-validate
                validation = self.validator.validate(html_code)
                if not validation.is_valid:
                    logger.error(
                        f"[{task_id}] Auto-fix also failed: {validation.errors}"
                    )
                    # Continue anyway — deliver best-effort game
            except Exception as e:
                logger.error(f"[{task_id}] Auto-fix exception: {e}")

        if validation.warnings:
            logger.warning(f"[{task_id}] Validation warnings: {validation.warnings}")

        await self._update_progress(task_id, 85, "processing")

        # Package and upload to MinIO (or fallback to DB storage)
        logger.info(f"[{task_id}] Phase 4: Packaging & uploading")
        try:
            oss_url = await self.packager.package_and_upload(game_id, html_code)
        except Exception as e:
            logger.warning(f"[{task_id}] MinIO upload failed ({e}), storing in DB instead")
            oss_url = f"/api/games/{game_id}/play-html"

        # ====== PHASE 4: FINALIZE ======
        await self._finalize(task_id, game_id, oss_url, html_code)

        logger.info(f"[{task_id}] Generation complete: {oss_url}")
        return oss_url

    async def _preprocess_assets(self, asset_ids: list[str]) -> list[str]:
        """Load assets and generate descriptions via Vision API."""
        if not asset_ids:
            return []

        from app.database import async_session
        from app.services import game_service

        descriptions = []

        async with async_session() as db:
            for asset_id in asset_ids:
                # Query asset by ID directly
                from sqlalchemy import select
                from app.models.game import GameAsset

                result = await db.execute(
                    select(GameAsset).where(GameAsset.id == asset_id)
                )
                asset = result.scalar_one_or_none()

                if not asset:
                    continue

                if asset.asset_type == "image":
                    try:
                        desc = await self.adapter.describe_image(asset.oss_url)
                        descriptions.append(
                            f"Image '{asset.original_filename}': {desc}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to describe image {asset.id}: {e}")
                        descriptions.append(
                            f"Image '{asset.original_filename}' (description unavailable)"
                        )
                else:
                    descriptions.append(
                        f"Asset '{asset.original_filename}' (type: {asset.asset_type}, url: {asset.oss_url})"
                    )

        return descriptions

    async def _update_progress(self, task_id: str, progress: int, status: str):
        """Update the task progress in the database."""
        try:
            from app.database import async_session
            from app.services import task_service

            async with async_session() as db:
                await task_service.update_task_progress(
                    db, task_id, progress=progress, status=status
                )
        except Exception as e:
            logger.error(f"Failed to update task progress: {e}")

    async def _finalize(
        self, task_id: str, game_id: str, oss_url: str, html_code: str
    ):
        """Mark task as completed and update the game record."""
        try:
            from app.database import async_session
            from app.services import task_service, game_service

            async with async_session() as db:
                # Update task (store full HTML in llm_response_raw for no-MinIO fallback)
                await task_service.update_task_progress(
                    db,
                    task_id,
                    progress=100,
                    status="completed",
                    result_oss_url=oss_url,
                    llm_response_raw=html_code[:50000],  # Store for direct serving
                )

                # Update game — set to "preview", use API endpoint for reliable iframe loading
                game = await game_service.get_game(db, game_id)
                if game:
                    # Store API endpoint as primary URL (avoids OSS Content-Disposition issues)
                    game.game_url = f"/api/games/{game_id}/play-html"
                    game.status = "preview"
                    await db.commit()

        except Exception as e:
            logger.error(f"Failed to finalize task/game: {e}")
