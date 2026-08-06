import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobSource


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=50, max_length=50_000)
    location: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1024)
    source: JobSource = JobSource.MANUAL


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    company: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=50, max_length=50_000)
    location: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1024)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str
    location: str | None
    source_url: str | None
    source: JobSource
    created_at: datetime


class JobDetail(JobRead):
    description: str
