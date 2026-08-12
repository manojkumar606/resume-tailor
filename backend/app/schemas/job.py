import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.job import JobSource

# Enough text to tailor against. Shorter than this and the model has nothing to
# work with, so it is worth rejecting rather than producing a useless rewrite.
MIN_USEFUL_DESCRIPTION = 50


def clean_description(value: str | None) -> str | None:
    """Treat blank input as absent, and reject anything too short to tailor.

    The field is optional because most applications are logged for tracking
    only — but if someone has pasted something, a two-word description is a
    mistake rather than a deliberate choice.
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) < MIN_USEFUL_DESCRIPTION:
        raise ValueError(
            f"a description needs at least {MIN_USEFUL_DESCRIPTION} characters to "
            "be useful — leave it empty to just track the application"
        )
    return cleaned


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=50_000)
    location: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1024)
    apply_by: date | None = None
    source: JobSource = JobSource.MANUAL

    _check_description = field_validator("description")(clean_description)


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    company: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=50_000)
    location: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1024)
    apply_by: date | None = None

    _check_description = field_validator("description")(clean_description)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str
    location: str | None
    source_url: str | None
    apply_by: date | None
    source: JobSource
    created_at: datetime
    # Lets the UI offer "tailor" only where there is something to tailor,
    # without shipping the whole posting in every list response. Backed by a
    # property on the Job model, so from_attributes populates it.
    has_description: bool


class JobDetail(JobRead):
    description: str | None
