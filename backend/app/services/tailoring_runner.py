"""Running a tailoring outside the request that asked for it.

A run takes 10-20 seconds. Holding an HTTP connection open for that long ties
up a worker for the duration and puts the whole feature at the mercy of any
proxy timeout between the browser and the app. The `tailorings` table has
carried a status column since the first migration precisely so this could move
without changing the client contract: the client now polls that column.

Deliberately `BackgroundTasks` rather than a queue. Render bills Background
Workers, and a broker is more machinery than a single-container app needs. The
cost of that choice is stated plainly in `reap_if_stalled`.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.models.job import Job
from app.models.resume import Resume
from app.models.tailoring import Tailoring, TailoringStatus
from app.services.docx_writer import build_resume_docx
from app.services.llm import LLMError, LLMProvider
from app.services.storage import build_key, get_storage
from app.services.tailoring import tailor

logger = logging.getLogger(__name__)


def _finish(db: DbSession, row: Tailoring, status: TailoringStatus, error: str | None):
    row.status = status
    row.error = error
    row.completed_at = datetime.now(UTC)
    db.commit()


def run_tailoring(
    tailoring_id: uuid.UUID,
    provider: LLMProvider,
    session_factory: Callable[[], DbSession],
    *,
    previous_attempt: str | None = None,
    critique: str | None = None,
) -> None:
    """Do the work and record the outcome. Never raises.

    An exception escaping here would be logged by the framework and then lost,
    leaving the row stuck on `running` with the user watching a spinner that
    will never stop. Every failure path has to end in a written status.

    The provider is passed in rather than resolved here on purpose: it is a
    FastAPI dependency, and resolving it internally would step around the
    override the tests use to avoid calling a real model.
    """
    db = session_factory()
    try:
        row = db.get(Tailoring, tailoring_id)
        if row is None:
            # Deleted between the request and the task starting. Nothing to do,
            # and nothing wrong.
            return
        if row.status is not TailoringStatus.PENDING:
            # Already picked up. Guards against a double-schedule.
            return

        row.status = TailoringStatus.RUNNING
        db.commit()

        job = db.get(Job, row.job_id)
        resume = db.get(Resume, row.resume_id)
        if job is None or resume is None or not resume.parsed_text:
            _finish(
                db,
                row,
                TailoringStatus.FAILED,
                "The job or resume was removed before this run started.",
            )
            return

        try:
            result = tailor(
                provider,
                resume_text=resume.parsed_text,
                job_title=job.title,
                company=job.company,
                description=job.description,
                previous_attempt=previous_attempt,
                critique=critique,
            )
        except LLMError as exc:
            _finish(db, row, TailoringStatus.FAILED, str(exc))
            return

        key = build_key(row.user_id, "tailored", f"{job.company}.docx")
        try:
            get_storage().save(key, build_resume_docx(result.tailored_text))
        except Exception as exc:
            logger.exception("Could not store a tailored resume")
            _finish(
                db, row, TailoringStatus.FAILED, f"Could not generate the document: {exc}"
            )
            return

        row.tailored_text = result.tailored_text
        row.match_score = result.match_score
        row.missing_keywords = result.missing_keywords
        row.changes = result.changes
        row.output_file_key = key
        _finish(db, row, TailoringStatus.SUCCEEDED, None)

    except Exception:
        # Anything unforeseen. The row matters more than the traceback, so the
        # status is written first and the exception is logged, not re-raised.
        logger.exception("Tailoring run failed unexpectedly: %s", tailoring_id)
        try:
            row = db.get(Tailoring, tailoring_id)
            if row is not None and row.status in (
                TailoringStatus.PENDING,
                TailoringStatus.RUNNING,
            ):
                db.rollback()
                _finish(
                    db,
                    row,
                    TailoringStatus.FAILED,
                    "Something went wrong on our side. Please try again.",
                )
        except Exception:
            logger.exception("Could not even record the failure: %s", tailoring_id)
    finally:
        db.close()


def reap_if_stalled(db: DbSession, row: Tailoring) -> Tailoring:
    """Fail a run that has been `running` for implausibly long.

    The one case `run_tailoring` cannot handle itself: if the container restarts
    mid-run, the in-process task dies with it and there is nobody left to write
    the failure. Without this the row stays `running` forever and the client
    polls a spinner that will never resolve.

    Checked lazily on read rather than swept on a timer — the only thing that
    cares is a client looking at the row, and a background sweeper would be more
    moving parts for the same result.
    """
    if row.status is not TailoringStatus.RUNNING:
        return row

    started = row.updated_at or row.created_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)

    if datetime.now(UTC) - started <= timedelta(
        minutes=settings.TAILORING_TIMEOUT_MINUTES
    ):
        return row

    _finish(
        db,
        row,
        TailoringStatus.FAILED,
        "This run was interrupted before it finished. Please try again.",
    )
    return row
