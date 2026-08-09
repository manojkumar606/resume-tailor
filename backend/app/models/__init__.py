"""Model package.

Every model must be imported here so Alembic's autogenerate sees the full
metadata — a model that is never imported is invisible to migrations.
"""

from app.models.application import Application, ApplicationStatus
from app.models.base import Base
from app.models.job import Job, JobSource
from app.models.resume import Resume
from app.models.tailoring import Tailoring, TailoringStatus
from app.models.user import User
from app.models.verification import EmailVerificationToken

__all__ = [
    "Application",
    "ApplicationStatus",
    "Base",
    "EmailVerificationToken",
    "Job",
    "JobSource",
    "Resume",
    "Tailoring",
    "TailoringStatus",
    "User",
]
