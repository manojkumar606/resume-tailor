from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.job import Job
    from app.models.resume import Resume
    from app.models.tailoring import Tailoring
    from app.models.verification import EmailCode


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Gates every route except /auth/*. See api/deps.get_verified_user.
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Opt-out, not opt-in: a retention feature nobody discovers does nothing.
    # Scoped to the daily digest only — login codes are transactional and are
    # never suppressed by this.
    reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tailorings: Mapped[list["Tailoring"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    email_codes: Mapped[list["EmailCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
