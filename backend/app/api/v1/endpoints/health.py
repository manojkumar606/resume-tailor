from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness — does the process respond at all."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@router.get("/health/ready")
def readiness(db: DbSession) -> dict:
    """Readiness — can the process actually reach its dependencies."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
