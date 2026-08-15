import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, status

from app.api.deps import DbSession, Mailer
from app.core.config import settings
from app.services.reminders import send_digests

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/reminders/run")
def run_reminders(
    db: DbSession,
    mailer: Mailer,
    x_cron_secret: str = Header(default=""),
) -> dict:
    """Send the daily digests. Called by a scheduled job, not by a person.

    Machine-to-machine, so it authenticates with a shared secret rather than a
    user session. An unset secret disables the endpoint outright — the failure
    mode of a blank secret matching a blank header would leave it wide open.
    """
    if not settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reminders are not configured.",
        )

    # Constant-time: a plain == leaks how much of the secret was right through
    # timing, which is enough to recover it byte by byte.
    if not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        # Deliberately identical to any other refusal, and logged without the
        # supplied value.
        logger.warning("Reminder run refused: bad or missing cron secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorised"
        )

    result = send_digests(db, mailer)
    logger.info("Reminder run: %s", result)
    return result
