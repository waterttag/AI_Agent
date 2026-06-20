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
    system_prompt_used: Optional[str] = None
    user_prompt_used: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskLogResponse(BaseModel):
    """Agent log summary for the latest generation."""
    task_id: str
    status: str
    progress: int
    prompt_summary: Optional[str] = None  # First 200 chars of user prompt
    agent_steps: list[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
