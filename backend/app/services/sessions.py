"""Creating, checking and revoking sessions.

A stateless JWT cannot be withdrawn. Binding each token to a row here is what
lets sign-out actually end access, and what lets the server — rather than a
browser timer — decide that an idle session is over.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.models.session import Session
from app.models.user import User

# Long user agents are truncated rather than rejected: the value is only ever
# shown back to the user, so a clipped string is better than a failed sign-in.
MAX_USER_AGENT = 400


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; Postgres returns aware ones."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def start_session(db: DbSession, user: User, user_agent: str | None) -> Session:
    now = _now()
    session = Session(
        user_id=user.id,
        # Absolute ceiling, fixed at sign-in. Activity never extends it.
        expires_at=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        last_used_at=now,
        user_agent=(user_agent or "").strip()[:MAX_USER_AGENT] or None,
    )
    db.add(session)
    db.flush()  # assigns the id, which goes into the token
    return session


def load_active(db: DbSession, session_id: uuid.UUID) -> Session | None:
    """Return the session only if it is still usable.

    An idle session is revoked on the spot rather than merely refused, so it
    cannot come back to life if the same token is presented again later.
    """
    session = db.get(Session, session_id)
    if session is None or session.revoked_at is not None:
        return None

    now = _now()

    if _as_aware(session.expires_at) <= now:
        return None

    idle_limit = timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)
    if now - _as_aware(session.last_used_at) > idle_limit:
        session.revoked_at = now
        db.commit()
        return None

    return session


def touch(db: DbSession, session: Session) -> None:
    """Record activity, but not on every single request.

    Idle expiry only needs minute-level accuracy, and writing a row per request
    would turn every authenticated call into a write.
    """
    now = _now()
    if (now - _as_aware(session.last_used_at)).total_seconds() < settings.SESSION_TOUCH_SECONDS:
        return
    session.last_used_at = now
    db.commit()


def revoke(db: DbSession, session: Session) -> None:
    if session.revoked_at is None:
        session.revoked_at = _now()
        db.commit()


def revoke_all_except(db: DbSession, user_id: uuid.UUID, keep: uuid.UUID | None) -> int:
    """Sign out everywhere. Returns how many sessions were ended."""
    stmt = update(Session).where(
        Session.user_id == user_id, Session.revoked_at.is_(None)
    )
    if keep is not None:
        stmt = stmt.where(Session.id != keep)

    result = db.execute(stmt.values(revoked_at=_now()))
    db.commit()
    return result.rowcount or 0


def list_active(db: DbSession, user_id: uuid.UUID) -> list[Session]:
    now = _now()
    rows = db.scalars(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        .order_by(Session.last_used_at.desc())
    ).all()

    # Idle-but-not-yet-revoked rows would otherwise be listed as active until
    # someone tried to use them.
    idle_limit = timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)
    return [r for r in rows if now - _as_aware(r.last_used_at) <= idle_limit]


# Order matters: "Edg" contains no "Chrome", but Chrome's own string contains
# "Safari", and Edge's contains both. Most specific first.
_BROWSERS = [
    ("Edg", "Edge"),
    ("OPR", "Opera"),
    ("Chrome", "Chrome"),
    ("Firefox", "Firefox"),
    ("Safari", "Safari"),
]

_PLATFORMS = [
    ("Android", "Android"),
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Windows", "Windows"),
    ("Mac OS X", "Mac"),
    ("Macintosh", "Mac"),
    ("Linux", "Linux"),
]


def describe_device(user_agent: str | None) -> str:
    """Turn a user agent into something a person can recognise.

    Deliberately crude. The only job is to let someone spot which row is the
    laptop they left at the office, and a full parsing library is a dependency
    and a maintenance burden for a single line of settings text.
    """
    if not user_agent:
        return "Unknown device"

    browser = next((name for token, name in _BROWSERS if token in user_agent), None)
    platform = next((name for token, name in _PLATFORMS if token in user_agent), None)

    if browser and platform:
        return f"{browser} on {platform}"
    return browser or platform or "Unknown device"
