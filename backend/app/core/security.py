"""Password hashing and JWT creation/verification."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import settings

# bcrypt silently truncates input at 72 bytes; reject longer passwords instead
# of accepting a password whose tail is ignored at both signup and login.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # Malformed hash in the DB — treat as a failed login, never a 500.
        return False


def create_access_token(subject: UUID | str, session_id: UUID | str) -> str:
    """Mint a token bound to a session row.

    The session id is what makes the token revocable. Without it the server has
    no way to refuse a correctly-signed token before it expires, so signing out
    could only ever delete the browser's copy.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "sid": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> tuple[str, str] | None:
    """Return (user id, session id) if the token is valid, else None.

    A token with no session id is refused rather than trusted. Those were issued
    before sessions existed and cannot be revoked, so honouring them would keep
    the original hole open for a week after the fix shipped.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None

    subject = payload.get("sub")
    session_id = payload.get("sid")
    if not subject or not session_id:
        return None
    return subject, session_id
