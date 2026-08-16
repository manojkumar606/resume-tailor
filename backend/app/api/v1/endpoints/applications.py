import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import DbSession, VerifiedUser
from app.core.config import settings
from app.models.application import Application, ApplicationSource, ApplicationStatus
from app.models.job import Job
from app.models.tailoring import Tailoring, TailoringStatus
from app.schemas.application import (
    ApplicationCreate,
    ApplicationQuickCreate,
    ApplicationRead,
    ApplicationUpdate,
)

router = APIRouter(prefix="/applications", tags=["applications"])

# Reaching any of these means the application was actually submitted, so
# applied_at gets stamped on the way out of SAVED.
SUBMITTED_STATUSES = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEWING,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
}


def _as_aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; Postgres returns aware ones."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# Long enough that the prompt does not appear while they are still reading the
# rewrite, short enough to catch them on the next visit.
APPLY_PROMPT_AFTER_HOURS = 12


def _needs_apply_prompt(application: Application) -> bool:
    """Whether to ask "did you apply?".

    Only for a card still in Saved that has a finished tailoring: the app knows
    a resume was prepared for this role, so a board still showing Saved is
    probably out of date rather than deliberate. Dismissing it is permanent —
    being asked twice about the same thing is what makes prompts hated.
    """
    if application.status is not ApplicationStatus.SAVED:
        return False
    if application.apply_prompt_dismissed_at is not None:
        return False

    tailoring = application.tailoring
    if tailoring is None or tailoring.status is not TailoringStatus.SUCCEEDED:
        return False

    completed = tailoring.completed_at or tailoring.created_at
    age = datetime.now(UTC) - _as_aware(completed)
    return age >= timedelta(hours=APPLY_PROMPT_AFTER_HOURS)


def _serialize(application: Application) -> ApplicationRead:
    """Attach the derived fields a board card needs."""
    now = datetime.now(UTC)
    days_since_update = (now - _as_aware(application.updated_at)).days

    apply_by = application.job.apply_by
    days_until_deadline = (apply_by - date.today()).days if apply_by else None

    # Only Applied goes stale: Saved has nothing to chase yet, and Interviewing,
    # Offer and Rejected are all resolved states where silence means nothing.
    is_stale = (
        application.status is ApplicationStatus.APPLIED
        and days_since_update >= settings.STALE_APPLICATION_DAYS
    )

    return ApplicationRead(
        id=application.id,
        status=application.status,
        applied_at=application.applied_at,
        notes=application.notes,
        created_at=application.created_at,
        updated_at=application.updated_at,
        source=application.source,
        interview_at=application.interview_at,
        job=application.job,
        tailoring=application.tailoring,
        is_stale=is_stale,
        days_since_update=days_since_update,
        days_until_deadline=days_until_deadline,
        needs_apply_prompt=_needs_apply_prompt(application),
    )


def _load(db: DbSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = db.scalar(
        select(Application)
        .options(joinedload(Application.job), joinedload(Application.tailoring))
        .where(Application.id == application_id, Application.user_id == user_id)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


def _reject_duplicate(db: DbSession, user_id: uuid.UUID, job_id: uuid.UUID) -> None:
    existing = db.scalar(
        select(Application.id).where(
            Application.user_id == user_id, Application.job_id == job_id
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That job is already on your board.",
        )


def _stamp_applied_at(application: Application, new_status: ApplicationStatus) -> None:
    if new_status in SUBMITTED_STATUSES and application.applied_at is None:
        application.applied_at = datetime.now(UTC)


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def track_job(
    payload: ApplicationCreate, current_user: VerifiedUser, db: DbSession
) -> ApplicationRead:
    """Put an existing job on the board."""
    job = db.scalar(
        select(Job).where(Job.id == payload.job_id, Job.user_id == current_user.id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    _reject_duplicate(db, current_user.id, job.id)

    if payload.tailoring_id is not None:
        owned = db.scalar(
            select(Tailoring.id).where(
                Tailoring.id == payload.tailoring_id,
                Tailoring.user_id == current_user.id,
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Tailoring not found")

    application = Application(
        user_id=current_user.id,
        job_id=job.id,
        tailoring_id=payload.tailoring_id,
        status=payload.status,
        notes=payload.notes,
        applied_at=payload.applied_at,
        source=payload.source,
    )
    _stamp_applied_at(application, payload.status)

    db.add(application)
    db.commit()
    return _serialize(_load(db, current_user.id, application.id))


@router.post(
    "/quick", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED
)
def quick_add(
    payload: ApplicationQuickCreate, current_user: VerifiedUser, db: DbSession
) -> ApplicationRead:
    """Create the job and its board card together, with no tailoring.

    This is the common case in a real hunt — a role applied to through a referral
    or a company site, where involving the model would be pointless. Requiring
    two calls, or a full job description, would make logging it a chore.
    """
    job = Job(
        user_id=current_user.id,
        title=payload.title.strip(),
        company=payload.company.strip(),
        location=payload.location,
        source_url=payload.source_url,
        apply_by=payload.apply_by,
        description=payload.description,
        source=payload.source,
    )
    db.add(job)
    db.flush()  # assigns job.id without committing

    application = Application(
        user_id=current_user.id,
        job_id=job.id,
        status=payload.status,
        notes=payload.notes,
        source=payload.applied_via,
    )
    _stamp_applied_at(application, payload.status)

    db.add(application)
    db.commit()
    return _serialize(_load(db, current_user.id, application.id))


@router.get("", response_model=list[ApplicationRead])
def list_applications(
    current_user: VerifiedUser,
    db: DbSession,
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ApplicationRead]:
    """The whole board in one call.

    joinedload avoids a query per card for the job and tailoring — with five
    columns of cards that would be the difference between 1 query and 60.
    """
    stmt = (
        select(Application)
        .options(joinedload(Application.job), joinedload(Application.tailoring))
        .where(Application.user_id == current_user.id)
    )
    if status_filter is not None:
        stmt = stmt.where(Application.status == status_filter)

    stmt = stmt.order_by(Application.updated_at.desc()).limit(limit).offset(offset)
    return [_serialize(row) for row in db.scalars(stmt).unique()]


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: uuid.UUID, current_user: VerifiedUser, db: DbSession
) -> ApplicationRead:
    return _serialize(_load(db, current_user.id, application_id))


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    current_user: VerifiedUser,
    db: DbSession,
) -> ApplicationRead:
    """Move a card, edit its notes, or attach a tailoring."""
    application = _load(db, current_user.id, application_id)
    fields = payload.model_dump(exclude_unset=True)

    if "tailoring_id" in fields and fields["tailoring_id"] is not None:
        owned = db.scalar(
            select(Tailoring.id).where(
                Tailoring.id == fields["tailoring_id"],
                Tailoring.user_id == current_user.id,
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Tailoring not found")

    if "status" in fields and fields["status"] is not None:
        _stamp_applied_at(application, fields["status"])

    # Not a column: answering "not yet" records when, so the prompt stops.
    if fields.pop("dismiss_apply_prompt", None):
        application.apply_prompt_dismissed_at = datetime.now(UTC)

    for field, value in fields.items():
        setattr(application, field, value)

    db.commit()
    return _serialize(_load(db, current_user.id, application_id))


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: uuid.UUID, current_user: VerifiedUser, db: DbSession
) -> Response:
    """Removes the card. The job and any tailorings are left alone, so this is
    "stop tracking", not "delete my work"."""
    application = _load(db, current_user.id, application_id)
    db.delete(application)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
