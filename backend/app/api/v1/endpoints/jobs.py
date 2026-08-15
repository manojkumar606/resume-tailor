import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select

from app.api.deps import DbSession, VerifiedUser
from app.core.config import settings
from app.models.job import Job
from app.schemas.job import JobCreate, JobDetail, JobImportResult, JobRead, JobUpdate
from app.services.job_import import (
    SUPPORTED_IMAGE_TYPES,
    ImportError_,
    parse_screenshots,
)
from app.services.llm import LLMProvider, get_llm_provider

router = APIRouter(prefix="/jobs", tags=["jobs"])

Provider = Annotated[LLMProvider, Depends(get_llm_provider)]


# Declared before /{job_id}: FastAPI matches in order, and a UUID path param
# would otherwise swallow this literal and reject it as a malformed UUID.
@router.post("/parse-screenshots", response_model=JobImportResult)
def parse_job_screenshots(
    current_user: VerifiedUser,
    provider: Provider,
    files: list[UploadFile] = File(...),
) -> JobImportResult:
    """Read a posting out of screenshots, without saving anything.

    Screenshots rather than a URL because the major boards block server-side
    fetching — this image has already been rendered by the user's own
    logged-in browser, so none of that applies.
    """
    if len(files) > settings.MAX_SCREENSHOTS:
        raise HTTPException(
            status_code=413,
            detail=f"Upload at most {settings.MAX_SCREENSHOTS} screenshots at once.",
        )

    images: list[tuple[bytes, str]] = []
    for upload in files:
        mime = (upload.content_type or "").split(";")[0].strip().lower()
        if mime not in SUPPORTED_IMAGE_TYPES:
            raise HTTPException(
                status_code=415,
                detail=(
                    f"{upload.filename or 'That file'} is not a supported image. "
                    f"Use {', '.join(sorted(SUPPORTED_IMAGE_TYPES))}."
                ),
            )

        data = upload.file.read()
        if not data:
            raise HTTPException(status_code=400, detail="One of the images was empty.")
        if len(data) > settings.MAX_SCREENSHOT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{upload.filename or 'That image'} is larger than "
                    f"{settings.MAX_SCREENSHOT_BYTES // (1024 * 1024)} MB."
                ),
            )
        images.append((data, mime))

    try:
        return JobImportResult(**parse_screenshots(provider, images))
    except ImportError_ as exc:
        # 422: the request was well-formed, the images just were not readable.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
