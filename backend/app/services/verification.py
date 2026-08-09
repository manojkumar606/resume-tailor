"""Issuing and redeeming email verification tokens."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.verification import EmailVerificationToken
from app.services.email import EmailProvider


class VerificationError(Exception):
    pass


class ResendTooSoon(VerificationError):
    def __init__(self, seconds_remaining: int):
        self.seconds_remaining = seconds_remaining
        super().__init__(
            f"Please wait {seconds_remaining}s before requesting another email."
        )


def _hash(token: str) -> str:
    """Plain SHA-256 rather than bcrypt.

    Correct here but not for passwords: this token is 256 bits of true
    randomness, so there is nothing to brute-force and no need for a slow KDF.
    A fast hash also keeps the lookup a single indexed query.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def build_verification_url(token: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/verify?token={quote(token)}"


def _render_email(user: User, url: str) -> tuple[str, str, str]:
    name = (user.full_name or "").strip().split(" ")[0] or "there"
    hours = settings.EMAIL_VERIFICATION_TTL_HOURS

    subject = "Confirm your email for Resume Tailor"
    text = (
        f"Hi {name},\n\n"
        "Confirm your email address to start using Resume Tailor:\n\n"
        f"{url}\n\n"
        f"This link expires in {hours} hours.\n\n"
        "If you did not create this account, you can ignore this message."
    )
    html = (
        f'<div style="font-family:system-ui,sans-serif;font-size:15px;'
        f'line-height:1.6;color:#111">'
        f"<p>Hi {name},</p>"
        f"<p>Confirm your email address to start using Resume Tailor:</p>"
        f'<p><a href="{url}" style="display:inline-block;background:#e5162a;'
        f'color:#fff;padding:10px 18px;border-radius:8px;'
        f'text-decoration:none">Confirm email</a></p>'
        f'<p style="color:#666;font-size:13px">Or paste this into your browser:'
        f'<br><span style="word-break:break-all">{url}</span></p>'
        f'<p style="color:#666;font-size:13px">This link expires in {hours} '
        f"hours. If you did not create this account, ignore this message.</p>"
        f"</div>"
    )
    return subject, html, text


def issue_token(db: Session, user: User) -> str:
    """Create a token row and return the plaintext token.

    The plaintext is returned rather than stored — this is the only moment it
    exists, and it goes straight into the email.
    """
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=_now() + timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS),
        )
    )
    return token


def send_verification_email(provider: EmailProvider, user: User, token: str) -> None:
    subject, html, text = _render_email(user, build_verification_url(token))
    provider.send(to=user.email, subject=subject, html=html, text=text)


def seconds_until_resend_allowed(db: Session, user: User) -> int:
    """0 when a resend is permitted, otherwise the remaining cooldown."""
    latest = db.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id)
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return 0

    created = latest.created_at
    # SQLite hands back naive datetimes; Postgres returns aware ones.
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)

    elapsed = (_now() - created).total_seconds()
    remaining = settings.EMAIL_RESEND_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining) + (1 if remaining > 0 else 0))


def redeem_token(db: Session, token: str) -> User:
    """Mark the user verified. Raises VerificationError for any bad token."""
    row = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == _hash(token)
        )
    )
    # Identical message for unknown, used and expired tokens: a caller probing
    # tokens learns nothing about which of the three it hit.
    invalid = VerificationError("That verification link is invalid or has expired.")

    if row is None or row.used_at is not None:
        raise invalid

    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < _now():
        raise invalid

    user = db.get(User, row.user_id)
    if user is None:
        raise invalid

    row.used_at = _now()
    user.is_verified = True

    # Retire any other outstanding tokens — once verified, older links that were
    # emailed should stop working.
    others = db.scalars(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    for other in others:
        other.used_at = _now()

    return user
