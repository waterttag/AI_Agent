"""Game and GameAsset ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    game_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    assets: Mapped[list["GameAsset"]] = relationship(
        "GameAsset", back_populates="game", cascade="all, delete-orphan"
    )
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])

    def __repr__(self) -> str:
        return f"<Game(id={self.id}, title={self.title}, status={self.status})>"


class GameAsset(Base):
    __tablename__ = "game_assets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)  # image, audio
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    oss_key: Mapped[str] = mapped_column(String(500), nullable=False)
    oss_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship
    game: Mapped["Game"] = relationship("Game", back_populates="assets")

    def __repr__(self) -> str:
        return f"<GameAsset(id={self.id}, type={self.asset_type})>"
