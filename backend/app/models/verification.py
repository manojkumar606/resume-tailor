import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class EmailVerificationToken(UUIDMixin, TimestampMixin, Base):
    """A single-use email verification token.

    Only a hash of the token is stored, for the same reason passwords are
    hashed: a database leak should not hand out account access. The plaintext
    exists only in the email that was sent.

    Kept in its own table rather than as a column on users so a resend issues a
    new row, leaving an audit trail of how many were sent and when — which is
    also what the resend cooldown is checked against.
    """

    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="verification_tokens")
