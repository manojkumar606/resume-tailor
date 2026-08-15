from fastapi import APIRouter

from app.api.v1.endpoints import (
    applications,
    auth,
    health,
    jobs,
    reminders,
    resumes,
    tailorings,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(resumes.router)
api_router.include_router(jobs.router)
api_router.include_router(tailorings.router)
api_router.include_router(applications.router)
api_router.include_router(reminders.router)
