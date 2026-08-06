import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text, Uuid
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
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[JobSource] = mapped_column(
        Enum(JobSource, name="job_source"), default=JobSource.MANUAL, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="jobs")
    tailorings: Mapped[list["Tailoring"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
