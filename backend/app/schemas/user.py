import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES
from app.services.email_codes import CODE_DIGITS


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def _bcrypt_length_limit(cls, v: str) -> str:
        # bcrypt truncates at 72 bytes. Reject rather than silently ignore the tail.
        if len(v.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
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


class CodeSent(BaseModel):
    """Returned by signup and login instead of a token.

    Neither step yields a session on its own: the emailed code is required
    first, so a password alone can never produce access.
    """

    status: str = "code_sent"
    email: EmailStr
    expires_in_minutes: int
    detail: str


class CodeSubmission(BaseModel):
    email: EmailStr
    code: str = Field(min_length=CODE_DIGITS, max_length=CODE_DIGITS + 2)

    @field_validator("code")
    @classmethod
    def _digits_only(cls, v: str) -> str:
        # People paste codes with stray spaces from the email body.
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not cleaned.isdigit() or len(cleaned) != CODE_DIGITS:
            raise ValueError(f"code must be {CODE_DIGITS} digits")
        return cleaned


class CodeResendRequest(BaseModel):
    email: EmailStr
