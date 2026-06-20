"""Seed the database with example games and a test user.

Usage:
    python seed/seed.py          # Using SQLite (default)
    python seed/seed.py --pg     # Using PostgreSQL from docker-compose

Ensure MinIO is running before executing.
"""

import asyncio
import sys
import os

# Add backend to path — handles both local and Docker paths
if os.path.exists("/app/app"):
    # Docker: backend code is at /app/
    sys.path.insert(0, "/app")
    SEED_DIR = "/"
else:
    # Local dev
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    SEED_DIR = os.path.dirname(__file__)

from app.database import async_session, engine, Base
from app.models import User, Game
from app.utils.security import hash_password
from app.utils.s3_client import get_s3_client, ensure_bucket
from app.config import settings

# SEED_DIR defined above (handles Docker vs local)

SEED_GAMES = [
    {
        "title": "Classic Snake",
        "description": "Control a growing snake, eat apples, and avoid crashing into yourself. A timeless arcade classic reimagined.",
        "tags": ["arcade", "classic", "snake"],
        "html_file": "snake.html",
    },
    {
        "title": "Memory Match",
        "description": "Flip cards and find matching pairs of cute emojis. Test your memory with 8 pairs to discover.",
        "tags": ["puzzle", "memory", "casual"],
        "html_file": "memory.html",
    },
    {
        "title": "Breakout Blitz",
        "description": "Destroy all the colorful bricks with your ball and paddle. Classic brick-breaker action!",
        "tags": ["arcade", "classic", "breakout"],
        "html_file": "breakout.html",
    },
]


async def clear_existing():
    """Clear existing seed data for idempotent re-runs."""
    async with async_session() as db:
        from sqlalchemy import delete
        await db.execute(delete(Game))
        await db.execute(delete(User))
        await db.commit()
    print("Cleared existing data.")


async def create_test_user() -> User:
    """Create a test creator account."""
    async with async_session() as db:
        user = User(
            username="democreator",
            email="demo@aigame.dev",
            password_hash=hash_password("demo123"),
            role="creator",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Created test user: {user.username} (demo@aigame.dev / demo123)")
        return user


async def upload_and_create_games(user: User):
    """Upload HTML games to S3-compatible storage and create DB records."""
    client = get_s3_client()
    bucket = settings.minio_bucket
    ensure_bucket()

    async with async_session() as db:
        for seed in SEED_GAMES:
            html_path = os.path.join(SEED_DIR, "games", seed["html_file"])
            if not os.path.exists(html_path):
                print(f"WARNING: Game HTML not found: {html_path}")
                continue

            # Create game record first (we need the UUID)
            game = Game(
                title=seed["title"],
                description=seed["description"],
                tags=seed["tags"],
                author_id=user.id,
                status="published",
                prompt_text=f"A fun {seed['tags'][0]} game.",
            )
            db.add(game)
            await db.commit()
            await db.refresh(game)

            # Upload HTML to S3-compatible storage
            from io import BytesIO
            oss_key = f"games/{game.id}/index.html"
            with open(html_path, "rb") as f:
                html_data = f.read()

            client.put_object(
                Bucket=bucket,
                Key=oss_key,
                Body=BytesIO(html_data),
                ContentType="text/html",
                ACL="public-read",
            )

            # Update game URL
            scheme = "https" if settings.minio_secure else "http"
            game.game_url = f"{scheme}://{settings.minio_endpoint}/{bucket}/{oss_key}"
            await db.commit()

            print(f"Seeded: {game.title} → {game.game_url}")

    print(f"\nSeeded {len(SEED_GAMES)} games successfully!")
    print(f"\nLogin: demo@aigame.dev / demo123")


async def main():
    print("=== AI Game Platform — Seed Script ===\n")

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await clear_existing()
    user = await create_test_user()
    await upload_and_create_games(user)

    print("\nDone! Start the backend and frontend to see the games.")
    print("  Backend: cd backend && uvicorn app.main:app --reload")
    print("  Frontend: cd frontend && npm run dev")


if __name__ == "__main__":
    asyncio.run(main())
