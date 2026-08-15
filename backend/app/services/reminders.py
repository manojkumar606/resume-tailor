"""The daily nudge.

A tracker only works if people come back to it, and nothing else in this app
brings them back. This is the one thing that does.

Two things are worth an email, and nothing else is: a deadline about to pass on
something not yet applied to, and an application that has gone quiet. Everything
else would be noise, and a reminder people learn to ignore is worse than none.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.application import Application, ApplicationStatus
from app.models.user import User
from app.services.email import EmailError, EmailProvider
from app.services.unsubscribe import unsubscribe_url

logger = logging.getLogger(__name__)


@dataclass
class UserDigest:
    user: User
    closing: list[Application] = field(default_factory=list)
    quiet: list[Application] = field(default_factory=list)

    @property
    def applications(self) -> list[Application]:
        return [*self.closing, *self.quiet]


def _as_aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; Postgres returns aware ones."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def collect_digests(db: Session, today: date | None = None) -> list[UserDigest]:
    """Group everything due a nudge by user, so nobody gets three emails."""
    today = today or datetime.now(UTC).date()
    deadline_cutoff = today + timedelta(days=settings.REMINDER_DEADLINE_DAYS)
    stale_before = datetime.now(UTC) - timedelta(days=settings.STALE_APPLICATION_DAYS)
    cooldown_before = datetime.now(UTC) - timedelta(days=settings.REMINDER_COOLDOWN_DAYS)

    rows = db.scalars(
        select(Application)
        .options(joinedload(Application.job), joinedload(Application.user))
        .where(
            Application.status.in_(
                [ApplicationStatus.SAVED, ApplicationStatus.APPLIED]
            ),
            # Never nag about the same card twice in one cooldown window.
            or_(
                Application.reminded_at.is_(None),
                Application.reminded_at < cooldown_before,
            ),
        )
    ).unique()

    digests: dict[str, UserDigest] = {}

    for row in rows:
        # Opted out, or disabled. Reminders are optional; login codes are not,
        # and this flag deliberately does not touch those.
        if not row.user.is_active or not row.user.reminders_enabled:
            continue

        digest = digests.setdefault(str(row.user_id), UserDigest(user=row.user))

        # Closing soon, and not yet applied to — the only case where a deadline
        # still means anything.
        if (
            row.status is ApplicationStatus.SAVED
            and row.job.apply_by is not None
            and today <= row.job.apply_by <= deadline_cutoff
        ):
            digest.closing.append(row)
            continue

        # Applied and gone quiet. Interviewing, Offer and Rejected are resolved
        # states where silence means nothing.
        if (
            row.status is ApplicationStatus.APPLIED
            and _as_aware(row.updated_at) < stale_before
        ):
            digest.quiet.append(row)

    return [d for d in digests.values() if d.applications]


def _render(digest: UserDigest) -> tuple[str, str, str]:
    name = (digest.user.full_name or "").strip().split(" ")[0] or "there"
    board_url = f"{settings.FRONTEND_URL.rstrip('/')}/board"

    if digest.closing and not digest.quiet:
        subject = f"{len(digest.closing)} closing soon"
    elif digest.quiet and not digest.closing:
        subject = f"{len(digest.quiet)} still waiting on a reply"
    else:
        subject = (
            f"{len(digest.closing)} closing soon, "
            f"{len(digest.quiet)} waiting on a reply"
        )

    text_lines = [f"Hi {name},", ""]
    html_parts = [
        '<div style="font-family:system-ui,sans-serif;font-size:15px;'
        'line-height:1.6;color:#111">',
        f"<p>Hi {name},</p>",
    ]

    if digest.closing:
        text_lines.append("Closing soon — you have not applied yet:")
        html_parts.append("<p><strong>Closing soon — not applied yet</strong></p><ul>")
        for row in digest.closing:
            days = (row.job.apply_by - datetime.now(UTC).date()).days
            when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
            line = f"{row.job.title} at {row.job.company} — closes {when}"
            text_lines.append(f"  - {line}")
            html_parts.append(f"<li>{line}</li>")
        text_lines.append("")
        html_parts.append("</ul>")

    if digest.quiet:
        text_lines.append("No reply yet — worth a follow-up:")
        html_parts.append("<p><strong>No reply yet — worth a follow-up</strong></p><ul>")
        for row in digest.quiet:
            days = (datetime.now(UTC) - _as_aware(row.updated_at)).days
            line = f"{row.job.title} at {row.job.company} — {days} days quiet"
            text_lines.append(f"  - {line}")
            html_parts.append(f"<li>{line}</li>")
        text_lines.append("")
        html_parts.append("</ul>")

    stop = unsubscribe_url(digest.user.id)
    text_lines += [
        f"Your board: {board_url}",
        "",
        f"Stop these reminders: {stop}",
        "",
        "— Resume Tailor",
    ]
    html_parts.append(
        f'<p><a href="{board_url}" style="display:inline-block;background:#e5162a;'
        'color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none">'
        "Open your board</a></p>"
        # In every digest, because the alternative to an easy unsubscribe is a
        # spam complaint, and that harms delivery of the login codes too.
        f'<p style="color:#666;font-size:12px">Do not want these? '
        f'<a href="{stop}" style="color:#666">Turn reminders off</a>. '
        "Sign-in codes are unaffected.</p></div>"
    )

    return subject, "".join(html_parts), "\n".join(text_lines)


def send_digests(db: Session, provider: EmailProvider) -> dict[str, int]:
    """Send one digest per user and stamp what was included.

    Stamps only on success: a card whose email failed should be picked up by the
    next run rather than silently skipped for a week.
    """
    sent = 0
    failed = 0
    reminded = 0
    now = datetime.now(UTC)

    for digest in collect_digests(db):
        subject, html, text = _render(digest)
        try:
            provider.send(to=digest.user.email, subject=subject, html=html, text=text)
        except EmailError as exc:
            failed += 1
            logger.warning("Reminder digest failed for one user: %s", exc)
            continue

        sent += 1
        for row in digest.applications:
            row.reminded_at = now
            reminded += 1

    db.commit()
    return {"emails_sent": sent, "emails_failed": failed, "applications": reminded}
