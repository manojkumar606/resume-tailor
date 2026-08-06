import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    original_filename: str | None
    is_default: bool
    created_at: datetime


class ResumeDetail(ResumeRead):
    """Includes the extracted text — omitted from list responses, which would
    otherwise ship every resume's full body on every page load."""

    parsed_text: str | None


class ResumeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None
