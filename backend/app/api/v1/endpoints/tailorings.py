import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import DbSession, VerifiedUser
from app.core.db import get_session_factory
from app.models.job import Job
from app.models.resume import Resume
from app.models.tailoring import Tailoring, TailoringStatus
from app.schemas.tailoring import TailoringCreate, TailoringDetail, TailoringRead
from app.services.llm import LLMProvider, get_llm_provider
from app.services.storage import StorageError, get_storage
from app.services.tailoring import build_critique
from app.services.tailoring_runner import reap_if_stalled, run_tailoring

router = APIRouter(prefix="/tailorings", tags=["tailorings"])

Provider = Annotated[LLMProvider, Depends(get_llm_provider)]
SessionFactory = Annotated[Callable[[], OrmSession], Depends(get_session_factory)]


def _get_owned_tailoring(
    db: DbSession, user_id: uuid.UUID, tailoring_id: uuid.UUID
) -> Tailoring:
    row = db.scalar(
        select(Tailoring).where(
            Tailoring.id == tailoring_id, Tailoring.user_id == user_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Tailoring not found")
    return reap_if_stalled(db, row)


@router.post("", response_model=TailoringDetail, status_code=status.HTTP_202_ACCEPTED)
def create_tailoring(
    payload: TailoringCreate,
    current_user: VerifiedUser,
    db: DbSession,
    provider: Provider,
    session_factory: SessionFactory,
    background: BackgroundTasks,
) -> Tailoring:
    """Start tailoring a resume for a job.

    Returns immediately with a `pending` row; the client polls it. Every
    validation below still happens synchronously, so a bad request is still a
    4xx the user sees straight away rather than a failed row they have to go
    and look up.
    """
    job = db.scalar(
        select(Job).where(Job.id == payload.job_id, Job.user_id == current_user.id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if payload.resume_id is not None:
        resume = db.scalar(
            select(Resume).where(
                Resume.id == payload.resume_id, Resume.user_id == current_user.id
            )
        )
        if resume is None:
            raise HTTPException(status_code=404, detail="Resume not found")
    else:
        resume = db.scalar(
            select(Resume)
            .where(Resume.user_id == current_user.id, Resume.is_default)
            .limit(1)
        )
        if resume is None:
            raise HTTPException(
                status_code=400,
                detail="No default resume. Upload a resume or pass resume_id.",
            )

    # description is optional now: applications can be tracked without one.
    # Tailoring is the one thing that genuinely cannot proceed without it.
    if not job.has_description:
        raise HTTPException(
            status_code=422,
            detail=(
                "This job has no description saved. Add the posting text to tailor "
                "a resume for it."
            ),
        )

    if not resume.parsed_text:
        raise HTTPException(
            status_code=422, detail="That resume has no extracted text to tailor"
        )

    previous_attempt: str | None = None
    critique: str | None = None

    if payload.refine_of is not None:
        previous = db.scalar(
            select(Tailoring).where(
                Tailoring.id == payload.refine_of,
                Tailoring.user_id == current_user.id,
            )
        )
        if previous is None:
            raise HTTPException(status_code=404, detail="Tailoring not found")
        # Revising against a different job's output would silently produce
        # nonsense, so it is refused rather than quietly ignored.
        if previous.job_id != job.id:
            raise HTTPException(
                status_code=400,
                detail="That version belongs to a different job.",
            )
        if previous.status is not TailoringStatus.SUCCEEDED or not previous.tailored_text:
            raise HTTPException(
                status_code=409,
                detail="That version did not succeed, so there is nothing to refine.",
            )

        critique = build_critique(payload.feedback, payload.feedback_notes)
        if critique is None:
            raise HTTPException(
                status_code=422,
                detail="Say what was wrong with it — pick at least one problem.",
            )
        previous_attempt = previous.tailored_text

    row = Tailoring(
        user_id=current_user.id,
        job_id=job.id,
        resume_id=resume.id,
        status=TailoringStatus.PENDING,
        model=getattr(provider, "model_name", None),
        refine_of_id=payload.refine_of,
        feedback=payload.feedback or None,
        feedback_notes=payload.feedback_notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Queued rather than awaited. Starlette runs this after the response is
    # sent, so the row id is already with the client by the time work begins.
    background.add_task(
        run_tailoring,
        row.id,
        provider,
        session_factory,
        previous_attempt=previous_attempt,
        critique=critique,
    )
    return row


@router.get("", response_model=list[TailoringRead])
def list_tailorings(
    current_user: VerifiedUser,
    db: DbSession,
    job_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Tailoring]:
    stmt = select(Tailoring).where(Tailoring.user_id == current_user.id)
    if job_id is not None:
        stmt = stmt.where(Tailoring.job_id == job_id)
    stmt = stmt.order_by(Tailoring.created_at.desc()).limit(limit).offset(offset)
    return [reap_if_stalled(db, row) for row in db.scalars(stmt)]


@router.get("/{tailoring_id}", response_model=TailoringDetail)
def get_tailoring(
    tailoring_id: uuid.UUID, current_user: VerifiedUser, db: DbSession
) -> Tailoring:
    return _get_owned_tailoring(db, current_user.id, tailoring_id)


@router.get("/{tailoring_id}/download")
def download_tailored_resume(
    tailoring_id: uuid.UUID, current_user: VerifiedUser, db: DbSession
) -> Response:
    row = _get_owned_tailoring(db, current_user.id, tailoring_id)
    if row.status is not TailoringStatus.SUCCEEDED or not row.output_file_key:
        raise HTTPException(
            status_code=409, detail=f"Tailoring is {row.status.value}, not ready"
        )

    try:
        data = get_storage().load(row.output_file_key)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Stored file is missing") from exc

    job = db.get(Job, row.job_id)
    safe = "".join(
        c for c in f"{job.company}-{job.title}" if c.isalnum() or c in " -_"
    ).strip() or "resume"

    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{safe}.docx"'},
    )


@router.delete("/{tailoring_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tailoring(
    tailoring_id: uuid.UUID, current_user: VerifiedUser, db: DbSession
) -> Response:
    row = _get_owned_tailoring(db, current_user.id, tailoring_id)
    file_key = row.output_file_key
    db.delete(row)
    db.commit()
    if file_key:
        try:
            get_storage().delete(file_key)
        except StorageError:
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)
