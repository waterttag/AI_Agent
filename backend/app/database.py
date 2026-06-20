"""Async SQLAlchemy engine and session management."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

_db_url = settings.get_database_url()

# SQLite needs check_same_thread=False; PostgreSQL needs nothing special
_connect_args = {"check_same_thread": False} if "sqlite" in _db_url else {}
_poolclass = NullPool if "sqlite" in _db_url else None

engine = create_async_engine(
    _db_url,
    echo=False,
    connect_args=_connect_args,
    poolclass=_poolclass,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
