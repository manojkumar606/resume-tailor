import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class Session(UUIDMixin, TimestampMixin, Base):
    """One signed-in device.

    The point of this table is that a stateless JWT cannot be taken back. Before
    it existed, "Sign out" only deleted the browser's copy of the token — anyone
    holding that string kept full access until it expired a week later, and
    nothing could stop them. The token now names a row, so revoking the row
    revokes the access.

    It also moves idle expiry to the server. A client-side timer is a courtesy;
    this is enforcement.

    Deliberately no IP address: it identifies little on mobile networks and is
    personal data this app has no use for. The user agent is enough to answer
    "is this me?".
    """

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Absolute ceiling, set at sign-in and never extended. Activity keeps a
    # session alive up to this point, not beyond it.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Touched on use, throttled — see api/deps. Idle expiry is measured from here.
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set on sign-out or revocation. Never deleted, so the row remains an
    # auditable record of a session that existed.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user_agent: Mapped[str | None] = mapped_column(String(400))

    user: Mapped["User"] = relationship(back_populates="sessions")
