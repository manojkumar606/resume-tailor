"""Schemas for the signed-in-devices list."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionRead(BaseModel):
    """One signed-in device, as shown in settings.

    The raw user agent is deliberately not exposed — it is a wall of version
    numbers that means nothing to the person reading it. `device` is a short
    label derived from it instead.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device: str
    last_used_at: datetime
    created_at: datetime
    expires_at: datetime
    # Which row is the browser making this request, so the UI can label it
    # "This device" and not offer to sign it out from the list.
    is_current: bool


class RevokedSessions(BaseModel):
    revoked: int
