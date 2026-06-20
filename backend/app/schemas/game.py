"""Game-related Pydantic schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class GameCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    prompt_text: Optional[str] = Field(default=None, max_length=10000)


class GameUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    tags: Optional[list[str]] = None
    cover_image_url: Optional[str] = None
    status: Optional[str] = None


class GameAssetResponse(BaseModel):
    id: str
    game_id: str
    asset_type: str
    original_filename: str
    oss_url: str
    file_size: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GameResponse(BaseModel):
    id: str
    title: str
    description: str
    cover_image_url: Optional[str] = None
    game_url: Optional[str] = None
    author_id: str
    author_name: Optional[str] = None
    tags: list = Field(default_factory=list)
    status: str
    prompt_text: Optional[str] = None
    play_count: int = 0
    created_at: datetime
    updated_at: datetime
    assets: list[GameAssetResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class GameListResponse(BaseModel):
    items: list[GameResponse]
    total: int
    page: int
    size: int


class GenerateRequest(BaseModel):
    prompt_text: str = Field(..., min_length=10, max_length=10000)
    model_preference: Optional[str] = None
