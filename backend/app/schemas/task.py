"""Task-related Pydantic schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TaskResponse(BaseModel):
    id: str
    game_id: str
    user_id: str
    status: str
    progress: int
    result_oss_url: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
