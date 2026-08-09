"""Issuing and checking the emailed codes used for signup and every login."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.verification import CodePurpose, EmailCode
from app.services.email import EmailProvider

CODE_DIGITS = 6


class CodeError(Exception):
    """Any failure to accept a code. Message is safe to show the user."""


class ResendTooSoon(CodeError):
    def __init__(self, seconds_remaining: int):
        self.seconds_remaining = seconds_remaining
        super().__init__(f"Please wait {seconds_remaining}s before asking for another code.")


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware ones."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _digest(code: str, user_id) -> str:
    """HMAC rather than a bare hash.

    Six digits is a million possibilities, so SHA-256(code) would be reversed
    instantly from a leaked table. Keying with SECRET_KEY makes the digest
    useless without it, and mixing in the user id stops one user's stored digest
    being matched against another's code.
    """
    message = f"{user_id}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def _generate_code() -> str:
    # randbelow, not randint/choice: this is a credential.
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def issue_code(db: Session, user: User, purpose: CodePurpose) -> str:
    """Invalidate any outstanding codes and return a fresh plaintext one.

    The plaintext exists only here and in the email; only the digest is stored.
    """
    outstanding = db.scalars(
        select(EmailCode).where(
            EmailCode.user_id == user.id, EmailCode.used_at.is_(None)
        )
    )
    for row in outstanding:
        # Otherwise an older email would still work after a resend, which
        # confuses users and widens the guessing window.
        row.used_at = _now()

    code = _generate_code()
    db.add(
        EmailCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=_digest(code, user.id),
            expires_at=_now() + timedelta(minutes=settings.LOGIN_CODE_TTL_MINUTES),
        )
    )
    return code


def _render(user: User, code: str, purpose: CodePurpose) -> tuple[str, str, str]:
    name = (user.full_name or "").strip().split(" ")[0] or "there"
    minutes = settings.LOGIN_CODE_TTL_MINUTES
    intro = (
        "Use this code to finish creating your account:"
        if purpose is CodePurpose.SIGNUP
        else "Use this code to sign in:"
    )
    subject = (
        f"{code} is your Resume Tailor code"
    )  # code in the subject so it is visible from the notification

    text = (
        f"Hi {name},\n\n{intro}\n\n    {code}\n\n"
        f"It expires in {minutes} minutes and can only be used once.\n\n"
        "If you did not request this, you can ignore this message — nobody can "
        "get into your account without the code."
    )
    html = (
        '<div style="font-family:system-ui,sans-serif;font-size:15px;'
        'line-height:1.6;color:#111">'
        f"<p>Hi {name},</p><p>{intro}</p>"
        f'<p style="font-size:34px;font-weight:700;letter-spacing:6px;'
        f'margin:24px 0;color:#000">{code}</p>'
        f'<p style="color:#666;font-size:13px">Expires in {minutes} minutes and '
        "can only be used once.</p>"
        '<p style="color:#666;font-size:13px">If you did not request this you can '
        "ignore this message — nobody can get into your account without the code."
        "</p></div>"
    )
    return subject, html, text


def send_code(provider: EmailProvider, user: User, code: str, purpose: CodePurpose) -> None:
    subject, html, text = _render(user, code, purpose)
    provider.send(to=user.email, subject=subject, html=html, text=text)


def seconds_until_resend_allowed(db: Session, user: User) -> int:
    """0 when a resend is permitted, otherwise the remaining cooldown."""
    latest = db.scalar(
        select(EmailCode)
        .where(EmailCode.user_id == user.id)
        .order_by(EmailCode.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return 0

    elapsed = (_now() - _as_aware(latest.created_at)).total_seconds()
    remaining = settings.EMAIL_RESEND_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining) + 1) if remaining > 0 else 0


def consume_code(db: Session, user: User, code: str) -> CodePurpose:
    """Check a code and burn it. Returns what it was for.

    Raises CodeError for anything wrong. The message never distinguishes
    "no code outstanding" from "wrong digits", so the endpoint cannot be used to
    probe whether a code is currently live for an address.
    """
    invalid = CodeError("That code is invalid or has expired. Request a new one.")

    row = db.scalar(
        select(EmailCode)
        .where(EmailCode.user_id == user.id, EmailCode.used_at.is_(None))
        .order_by(EmailCode.created_at.desc())
        .limit(1)
    )
    if row is None or _as_aware(row.expires_at) < _now():
        raise invalid

    if not hmac.compare_digest(row.code_hash, _digest(code.strip(), user.id)):
        row.attempts += 1
        if row.attempts >= settings.LOGIN_CODE_MAX_ATTEMPTS:
            # Retire it rather than leave a known-target code open.
            row.used_at = _now()
        raise invalid

    row.used_at = _now()
    return row.purpose
