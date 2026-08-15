import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.tailoring import TailoringStatus

MAX_FEEDBACK_ITEMS = 8
MAX_FEEDBACK_ITEM_CHARS = 120


class TailoringCreate(BaseModel):
    job_id: uuid.UUID
    # Omit to use the user's default resume.
    resume_id: uuid.UUID | None = None

    # ── Refining a previous attempt ────────────────────────────────────────
    # The tailoring being revised. Must belong to the caller, be for the same
    # job, and have succeeded — there is nothing to revise otherwise.
    refine_of: uuid.UUID | None = None
    # Short, predefined complaints. Bounded because they go straight into the
    # prompt, and an unbounded list is a cheap way to blow up a request.
    feedback: list[str] = Field(default_factory=list, max_length=MAX_FEEDBACK_ITEMS)
    feedback_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("feedback")
    @classmethod
    def _tidy_feedback(cls, items: list[str]) -> list[str]:
        cleaned = [item.strip()[:MAX_FEEDBACK_ITEM_CHARS] for item in items]
        return [item for item in cleaned if item]


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

    # Lineage, so the history can show which version came from which complaint.
    refine_of_id: uuid.UUID | None
    feedback: list[str] | None
    feedback_notes: str | None


class TailoringDetail(TailoringRead):
    tailored_text: str | None
    missing_keywords: list[str] | None
    changes: list[str] | None
