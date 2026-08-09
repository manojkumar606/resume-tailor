import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class CodePurpose(str, enum.Enum):
    SIGNUP = "signup"  # confirming the address when the account is created
    LOGIN = "login"    # second factor on every subsequent sign-in


class EmailCode(UUIDMixin, TimestampMixin, Base):
    """A short-lived numeric code emailed to the user.

    Used for both signup confirmation and as the second step of every login, so
    a password alone is never enough to obtain a session.

    Stored as an HMAC keyed with SECRET_KEY rather than a plain hash. A six-digit
    code is only a million possibilities, so a bare SHA-256 of it would fall to
    an offline sweep the instant the table leaked; without the key, the digest is
    useless.
    """

    __tablename__ = "email_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    purpose: Mapped[CodePurpose] = mapped_column(
        Enum(CodePurpose, name="code_purpose"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Guessing is cheap against six digits, so a code is retired after a few
    # wrong tries rather than staying open for its full lifetime.
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="email_codes")
