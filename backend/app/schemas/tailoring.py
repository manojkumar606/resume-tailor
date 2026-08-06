import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.tailoring import TailoringStatus


class TailoringCreate(BaseModel):
    job_id: uuid.UUID
    # Omit to use the user's default resume.
    resume_id: uuid.UUID | None = None


class TailoringRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID
    status: TailoringStatus
    match_score: float | None
    model: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class TailoringDetail(TailoringRead):
    tailored_text: str | None
    missing_keywords: list[str] | None
    changes: list[str] | None
