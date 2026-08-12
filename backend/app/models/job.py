import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.tailoring import Tailoring
    from app.models.user import User


class JobSource(str, enum.Enum):
    MANUAL = "manual"        # user pasted the description text
    URL = "url"              # user pasted a link, server fetched it
    EXTENSION = "extension"  # captured by the browser extension


class Job(UUIDMixin, TimestampMixin, Base):
    """A job posting the user wants to apply to."""

    __tablename__ = "jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    # Optional on purpose. Most applications are logged for tracking only —
    # forcing a full posting just to record "applied via referral" is friction
    # the tracker should not impose. Tailoring checks for it separately.
    description: Mapped[str | None] = mapped_column(Text)
    # When the posting closes. Drives deadline reminders.
    apply_by: Mapped[date | None] = mapped_column(Date)
    source: Mapped[JobSource] = mapped_column(
        Enum(JobSource, name="job_source"), default=JobSource.MANUAL, nullable=False
    )

    @property
    def has_description(self) -> bool:
        """Whether there is enough posting text to tailor against."""
        return bool(self.description and self.description.strip())

    user: Mapped["User"] = relationship(back_populates="jobs")
    tailorings: Mapped[list["Tailoring"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
