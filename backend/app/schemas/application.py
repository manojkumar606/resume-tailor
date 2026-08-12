import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.application import ApplicationStatus
from app.models.job import JobSource
from app.schemas.job import clean_description


class ApplicationJob(BaseModel):
    """The job fields a board card needs. Deliberately excludes the full
    description, which would bloat every card in the list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str
    location: str | None
    source_url: str | None
    apply_by: date | None
    has_description: bool


class ApplicationTailoring(BaseModel):
    """Summary of the tailoring attached to this application, if any.

    missing_keywords is included because the gaps for a role are what an
    interviewer probes — it is the most useful thing to see on a card.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_score: float | None
    missing_keywords: list[str] | None


class ApplicationCreate(BaseModel):
    """Track an existing job. Use /applications/quick to create both at once."""

    job_id: uuid.UUID
    status: ApplicationStatus = ApplicationStatus.SAVED
    tailoring_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    applied_at: datetime | None = None


class ApplicationQuickCreate(BaseModel):
    """Log an application in one call, without tailoring anything.

    This is the path for the bulk of a real job hunt: roles applied to via a
    referral or a company site, where there is no reason to involve the model.
    """

    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1024)
    apply_by: date | None = None
    description: str | None = Field(default=None, max_length=50_000)
    status: ApplicationStatus = ApplicationStatus.SAVED
    notes: str | None = Field(default=None, max_length=10_000)
    source: JobSource = JobSource.MANUAL

    _check_description = field_validator("description")(clean_description)


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    # Settable so a user can correct the date the server stamped for them.
    applied_at: datetime | None = None
    tailoring_id: uuid.UUID | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    job: ApplicationJob
    tailoring: ApplicationTailoring | None

    # Computed server-side so the threshold lives in one place — the reminder
    # job will reuse the same rule.
    is_stale: bool
    days_since_update: int
    days_until_deadline: int | None
