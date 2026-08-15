import csv
import io
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.models.tailoring import Tailoring
from app.models.user import User
from app.models.verification import EmailCode
from app.schemas.user import AccountDeleteRequest, UserRead, UserUpdate
from app.services.storage import StorageError, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["account"])

EXPORT_COLUMNS = [
    "status",
    "job_title",
    "company",
    "location",
    "source_url",
    "apply_by",
    "applied_at",
    "match_score",
    "missing_keywords",
    "notes",
    "created_at",
    "updated_at",
]


@router.patch("", response_model=UserRead)
def update_me(payload: UserUpdate, current_user: CurrentUser, db: DbSession) -> UserRead:
    """Change preferences. Uses CurrentUser, not VerifiedUser — a token can only
    exist post-verification anyway, and settings should never be the thing that
    locks someone out."""
    fields = payload.model_dump(exclude_unset=True)

    if "full_name" in fields:
        name = fields["full_name"]
        current_user.full_name = name.strip() if isinstance(name, str) else None
    if fields.get("reminders_enabled") is not None:
        current_user.reminders_enabled = fields["reminders_enabled"]

    db.commit()
    db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.get("/export")
def export_my_data(current_user: CurrentUser, db: DbSession) -> Response:
    """Every tracked application as CSV.

    People keep a parallel spreadsheet anyway, and being able to walk away with
    the data is part of what makes a job-hunting tool trustworthy.
    """
    rows = db.scalars(
        select(Application)
        .options(joinedload(Application.job), joinedload(Application.tailoring))
        .where(Application.user_id == current_user.id)
        .order_by(Application.created_at)
    ).unique()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                "status": row.status.value,
                "job_title": row.job.title,
                "company": row.job.company,
                "location": row.job.location or "",
                "source_url": row.job.source_url or "",
                "apply_by": row.job.apply_by.isoformat() if row.job.apply_by else "",
                "applied_at": row.applied_at.isoformat() if row.applied_at else "",
                "match_score": (
                    row.tailoring.match_score
                    if row.tailoring and row.tailoring.match_score is not None
                    else ""
                ),
                "missing_keywords": "; ".join(
                    (row.tailoring.missing_keywords or []) if row.tailoring else []
                ),
                "notes": row.notes or "",
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
        )

    stamp = datetime.now(UTC).date().isoformat()
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="resume-tailor-applications-{stamp}.csv"'
            )
        },
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_account(
    payload: AccountDeleteRequest, current_user: CurrentUser, db: DbSession
) -> Response:
    """Delete the account and everything belonging to it.

    Job hunting is usually done while employed, so "I can leave whenever I want"
    is a large part of why anyone trusts this with a resume.
    """
    if payload.confirm_email.strip().lower() != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That email does not match this account.",
        )

    user_id = current_user.id

    # Gather the storage keys before the rows go, or the blobs are orphaned with
    # nothing left pointing at them.
    file_keys = [
        key
        for key in (
            *db.scalars(select(Resume.file_key).where(Resume.user_id == user_id)),
            *db.scalars(
                select(Tailoring.output_file_key).where(Tailoring.user_id == user_id)
            ),
        )
        if key
    ]

    # Deleted explicitly and in dependency order rather than leaning on the
    # cascade: tailorings.resume_id is ON DELETE RESTRICT, so a cascade that
    # reached resumes first would abort the whole delete.
    db.execute(delete(Application).where(Application.user_id == user_id))
    db.execute(delete(Tailoring).where(Tailoring.user_id == user_id))
    db.execute(delete(Resume).where(Resume.user_id == user_id))
    db.execute(delete(Job).where(Job.user_id == user_id))
    db.execute(delete(EmailCode).where(EmailCode.user_id == user_id))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()

    # Best effort: the rows are already gone, and an orphaned blob is far less
    # harmful than a delete the user cannot complete.
    storage = get_storage()
    for key in file_keys:
        try:
            storage.delete(key)
        except StorageError:
            logger.warning("Could not remove a stored file during account deletion")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
