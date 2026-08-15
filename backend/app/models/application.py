import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.tailoring import Tailoring
    from app.models.user import User


class ApplicationStatus(str, enum.Enum):
    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"


class Application(UUIDMixin, TimestampMixin, Base):
    """A tracked application — one card on the user's pipeline board."""

    __tablename__ = "applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Nullable: a job can be tracked before any resume has been tailored for it.
    tailoring_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tailorings.id", ondelete="SET NULL"), index=True
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.SAVED,
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    # When this card last triggered a reminder email. Without it the daily job
    # would nag about the same stale application every single morning.
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # One card per job. Without this the board can show the same role twice,
    # which is confusing and makes the funnel numbers wrong.
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
    )

    user: Mapped["User"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship(back_populates="applications")
    tailoring: Mapped["Tailoring | None"] = relationship(back_populates="applications")
