import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.lab import LabSessionStatus


class LabRead(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str | None
    instructions_md: str | None
    image: str
    cpu_limit: str
    memory_limit: str
    timeout_seconds: int

    model_config = {"from_attributes": True}


class LabTaskRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    order: int
    points: int

    model_config = {"from_attributes": True}


class LabSessionCreate(BaseModel):
    lab_id: uuid.UUID


class LabSessionRead(BaseModel):
    id: uuid.UUID
    lab_id: uuid.UUID
    status: LabSessionStatus
    container_id: str | None
    expires_at: datetime | None
    started_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCheckRequest(BaseModel):
    task_id: uuid.UUID


class TaskCheckResult(BaseModel):
    task_id: uuid.UUID
    passed: bool
    points_earned: int
    output: str


class LabScoreRead(BaseModel):
    total_points: int
    max_points: int
    final_score: int
    time_bonus: int
    attempts_penalty: int
    tasks_passed: int
    tasks_total: int
