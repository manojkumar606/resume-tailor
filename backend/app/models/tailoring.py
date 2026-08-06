import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.job import Job
    from app.models.resume import Resume
    from app.models.user import User


class TailoringStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Tailoring(UUIDMixin, TimestampMixin, Base):
    """One run of "tailor this resume for this job".

    Modelled as a row rather than a synchronous call so the work can move to a
    background worker in P2 without an API change: the client polls status.
    """

    __tablename__ = "tailorings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("resumes.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    status: Mapped[TailoringStatus] = mapped_column(
        Enum(TailoringStatus, name="tailoring_status"),
        default=TailoringStatus.PENDING,
        nullable=False,
    )
    tailored_text: Mapped[str | None] = mapped_column(Text)
    output_file_key: Mapped[str | None] = mapped_column(String(512))
    match_score: Mapped[float | None] = mapped_column(Float)
    model: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="tailorings")
    job: Mapped["Job"] = relationship(back_populates="tailorings")
    resume: Mapped["Resume"] = relationship(back_populates="tailorings")
    applications: Mapped[list["Application"]] = relationship(back_populates="tailoring")
