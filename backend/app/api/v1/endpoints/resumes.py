import uuid

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select, update

from app.api.deps import CurrentUser, DbSession
from app.models.resume import Resume
from app.models.tailoring import Tailoring
from app.schemas.resume import ResumeDetail, ResumeRead, ResumeUpdate
from app.services.parsing import ParseError, UnsupportedFileType, extract_text
from app.services.storage import StorageError, build_key, get_storage

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _get_owned_resume(db: DbSession, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    """Fetch a resume, scoped to its owner.

    Returns 404 rather than 403 for someone else's resume — a 403 would confirm
    the id exists.
    """
    resume = db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


def _clear_other_defaults(db: DbSession, user_id: uuid.UUID, keep_id: uuid.UUID) -> None:
    db.execute(
        update(Resume)
        .where(Resume.user_id == user_id, Resume.id != keep_id, Resume.is_default)
        .values(is_default=False)
    )


@router.post("", response_model=ResumeDetail, status_code=status.HTTP_201_CREATED)
def upload_resume(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> Resume:
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        text = extract_text(file.filename or "", raw)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    key = build_key(current_user.id, "resumes", file.filename or "resume")
    try:
        get_storage().save(key, raw)
    except StorageError as exc:
        raise HTTPException(status_code=500, detail="Could not store the file") from exc

    # The first resume a user uploads becomes their default automatically.
    has_existing = db.scalar(
        select(Resume.id).where(Resume.user_id == current_user.id).limit(1)
    )

    resume = Resume(
        user_id=current_user.id,
        name=(name or "").strip() or (file.filename or "Resume"),
        original_filename=file.filename,
        file_key=key,
        parsed_text=text,
        is_default=has_existing is None,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("", response_model=list[ResumeRead])
def list_resumes(current_user: CurrentUser, db: DbSession) -> list[Resume]:
    return list(
        db.scalars(
            select(Resume)
            .where(Resume.user_id == current_user.id)
            .order_by(Resume.is_default.desc(), Resume.created_at.desc())
        )
    )


@router.get("/{resume_id}", response_model=ResumeDetail)
def get_resume(
    resume_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> Resume:
    return _get_owned_resume(db, current_user.id, resume_id)


@router.patch("/{resume_id}", response_model=ResumeDetail)
def update_resume(
    resume_id: uuid.UUID,
    payload: ResumeUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> Resume:
    resume = _get_owned_resume(db, current_user.id, resume_id)

    if payload.name is not None:
        resume.name = payload.name.strip()

    if payload.is_default is not None:
        if payload.is_default:
            resume.is_default = True
            _clear_other_defaults(db, current_user.id, resume.id)
        else:
            resume.is_default = False

    db.commit()
    db.refresh(resume)
    return resume


@router.get("/{resume_id}/download")
def download_resume(
    resume_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> Response:
    resume = _get_owned_resume(db, current_user.id, resume_id)
    try:
        data = get_storage().load(resume.file_key)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Stored file is missing") from exc

    filename = resume.original_filename or "resume"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> Response:
    resume = _get_owned_resume(db, current_user.id, resume_id)

    # tailorings.resume_id is ON DELETE RESTRICT: past tailorings must stay
    # attributable to the resume they came from. Refuse with an explanation
    # rather than letting the database raise an opaque IntegrityError.
    in_use = db.scalar(
        select(Tailoring.id).where(Tailoring.resume_id == resume.id).limit(1)
    )
    if in_use is not None:
        raise HTTPException(
            status_code=409,
            detail="This resume has tailored versions and cannot be deleted.",
        )

    was_default = resume.is_default
    file_key = resume.file_key

    db.delete(resume)
    db.flush()

    # Never leave a user with resumes but no default.
    if was_default:
        replacement = db.scalar(
            select(Resume)
            .where(Resume.user_id == current_user.id)
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        if replacement is not None:
            replacement.is_default = True

    db.commit()

    # Storage cleanup is best-effort: the row is already gone, and an orphaned
    # blob is far less harmful than a failed delete the user cannot retry.
    try:
        get_storage().delete(file_key)
    except StorageError:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
