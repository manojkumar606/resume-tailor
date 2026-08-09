import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def _bcrypt_length_limit(cls, v: str) -> str:
        # bcrypt truncates at 72 bytes. Reject rather than silently ignore the tail.
        if len(v.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"password must be at most {MAX_PASSWORD_BYTES} bytes"
            )
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime


class VerifyRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
