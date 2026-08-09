import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import DbSession, VerifiedUser
from app.models.job import Job
from app.schemas.job import JobCreate, JobDetail, JobRead, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_owned_job(db: DbSession, user_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.user_id == user_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("", response_model=JobDetail, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, current_user: VerifiedUser, db: DbSession) -> Job:
    job = Job(user_id=current_user.id, **payload.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[JobRead])
def list_jobs(
    current_user: VerifiedUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Job]:
    return list(
        db.scalars(
            select(Job)
            .where(Job.user_id == current_user.id)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: uuid.UUID, current_user: VerifiedUser, db: DbSession) -> Job:
    return _get_owned_job(db, current_user.id, job_id)


@router.patch("/{job_id}", response_model=JobDetail)
def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    current_user: VerifiedUser,
    db: DbSession,
) -> Job:
    job = _get_owned_job(db, current_user.id, job_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: uuid.UUID, current_user: VerifiedUser, db: DbSession
) -> Response:
    job = _get_owned_job(db, current_user.id, job_id)
    # Tailorings and applications for this job cascade at the DB level.
    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
