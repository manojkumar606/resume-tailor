"""Model package.

Every model must be imported here so Alembic's autogenerate sees the full
metadata — a model that is never imported is invisible to migrations.
"""

from app.models.application import Application, ApplicationSource, ApplicationStatus
from app.models.base import Base
from app.models.job import Job, JobSource
from app.models.resume import Resume
from app.models.session import Session
from app.models.tailoring import Tailoring, TailoringStatus
from app.models.user import User
from app.models.verification import CodePurpose, EmailCode

__all__ = [
    "Application",
    "ApplicationSource",
    "ApplicationStatus",
    "Base",
    "CodePurpose",
    "EmailCode",
    "Job",
    "JobSource",
    "Resume",
    "Session",
    "Tailoring",
    "TailoringStatus",
    "User",
]
