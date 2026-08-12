import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import DbSession, VerifiedUser
from app.models.job import Job
from app.models.resume import Resume
from app.models.tailoring import Tailoring, TailoringStatus
from app.schemas.tailoring import TailoringCreate, TailoringDetail, TailoringRead
from app.services.docx_writer import build_resume_docx
from app.services.llm import LLMError, LLMProvider, get_llm_provider
from app.services.storage import StorageError, build_key, get_storage
from app.services.tailoring import tailor

router = APIRouter(prefix="/tailorings", tags=["tailorings"])

Provider = Annotated[LLMProvider, Depends(get_llm_provider)]


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
    return row


@router.post("", response_model=TailoringDetail, status_code=status.HTTP_201_CREATED)
def create_tailoring(
    payload: TailoringCreate,
    current_user: VerifiedUser,
    db: DbSession,
    provider: Provider,
) -> Tailoring:
    """Tailor a resume for a job.

    Runs inline today. The row carries a status so this can move behind a
    worker queue later and return 202 without the client contract changing.
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

    row = Tailoring(
        user_id=current_user.id,
        job_id=job.id,
        resume_id=resume.id,
        status=TailoringStatus.RUNNING,
        model=getattr(provider, "model_name", None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    try:
        result = tailor(
            provider,
            resume_text=resume.parsed_text,
            job_title=job.title,
            company=job.company,
            description=job.description,
        )
    except LLMError as exc:
        # Persist the failure rather than losing it: the user can see why, and
        # the row stays as a record of the attempt.
        row.status = TailoringStatus.FAILED
        row.error = str(exc)
        row.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        raise HTTPException(status_code=502, detail=f"Tailoring failed: {exc}") from exc

    key = build_key(current_user.id, "tailored", f"{job.company}.docx")
    try:
        get_storage().save(key, build_resume_docx(result.tailored_text))
    except Exception as exc:
        row.status = TailoringStatus.FAILED
        row.error = f"Could not generate the document: {exc}"
        row.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        raise HTTPException(
            status_code=500, detail="Could not generate the document"
        ) from exc

    row.status = TailoringStatus.SUCCEEDED
    row.tailored_text = result.tailored_text
    row.match_score = result.match_score
    row.missing_keywords = result.missing_keywords
    row.changes = result.changes
    row.output_file_key = key
    row.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
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
    return list(db.scalars(stmt))


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
