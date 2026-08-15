import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# JSONB on Postgres, plain JSON everywhere else so the SQLite test suite still
# works. JSONB stores parsed and can be indexed; there is no reason to prefer
# JSON on a Postgres deployment.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")

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
    # Requirements the candidate genuinely does not meet, and a summary of the
    # edits made. Both drive the results UI, so they are stored, not recomputed.
    missing_keywords: Mapped[list[str] | None] = mapped_column(JSONVariant)
    changes: Mapped[list[str] | None] = mapped_column(JSONVariant)
    model: Mapped[str | None] = mapped_column(String(100))

    # Lineage for the refine loop. Self-referential FK with no ORM relationship
    # attached: nothing server-side needs to walk the chain, and a self-join
    # mapping would be complexity for no gain.
    refine_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tailorings.id", ondelete="SET NULL"), index=True
    )
    # What the candidate said was wrong with the previous attempt. Stored so the
    # version history can explain *why* each version exists.
    feedback: Mapped[list[str] | None] = mapped_column(JSONVariant)
    feedback_notes: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="tailorings")
    job: Mapped["Job"] = relationship(back_populates="tailorings")
    resume: Mapped["Resume"] = relationship(back_populates="tailorings")
    applications: Mapped[list["Application"]] = relationship(back_populates="tailoring")
