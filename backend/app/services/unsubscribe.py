"""One-click unsubscribe tokens for the reminder digest.

Someone irritated by an email at 7am will not log in, find a settings page and
flip a toggle — they will press "mark as spam". That matters more here than
usual: the digest and the login codes go out from the same Brevo sender, so
spam complaints degrade deliverability for the six-digit codes, and a code that
lands in spam locks the user out of the app entirely.

So the link has to work straight from the inbox, with no session.

Stateless HMAC rather than a stored token: nothing to clean up, and the only
thing a leaked token can do is turn someone's reminders off — it cannot enable
them, read anything, or authenticate. The purpose string keeps it from being
interchangeable with any other signed value made from the same secret.
"""

import hashlib
import hmac
import uuid

from app.core.config import settings

PURPOSE = "unsubscribe-reminders"


class InvalidUnsubscribeToken(Exception):
    pass


def _signature(user_id: uuid.UUID) -> str:
    message = f"{PURPOSE}:{user_id}".encode()
    return hmac.new(
        settings.SECRET_KEY.encode(), message, hashlib.sha256
    ).hexdigest()[:32]


def make_token(user_id: uuid.UUID) -> str:
    """A token that identifies the user and proves we issued it."""
    return f"{user_id}.{_signature(user_id)}"


def read_token(token: str) -> uuid.UUID:
    """Return the user id, or raise. Never reveals which half was wrong."""
    invalid = InvalidUnsubscribeToken("That unsubscribe link is not valid.")

    raw_id, _, signature = (token or "").strip().partition(".")
    if not raw_id or not signature:
        raise invalid

    try:
        user_id = uuid.UUID(raw_id)
    except ValueError:
        raise invalid from None

    if not hmac.compare_digest(signature, _signature(user_id)):
        raise invalid

    return user_id


def unsubscribe_url(user_id: uuid.UUID) -> str:
    """Points at the frontend, not the API.

    A bare GET that changes state would be unsubscribing people by accident:
    mail clients and security scanners prefetch links in messages. The frontend
    page shows a button, and the state change happens on the POST behind it.
    """
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/unsubscribe?token={make_token(user_id)}"
