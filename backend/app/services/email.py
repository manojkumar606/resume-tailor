"""Email delivery behind a provider interface.

Same shape as services/llm.py: nothing above this module knows which service
sends the mail. Development and tests use the console provider, so no mail
account or network access is needed to exercise the verification flow.
"""

import logging
from functools import lru_cache
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class EmailError(Exception):
    pass


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, html: str, text: str) -> None: ...


class ConsoleEmailProvider:
    """Logs the message instead of sending it.

    The verification link is printed in full so the flow can be completed from
    the terminal during development.
    """

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.warning(
            "\n--- EMAIL (not sent; EMAIL_PROVIDER=console) ---\n"
            "To: %s\nSubject: %s\n\n%s\n"
            "-----------------------------------------------",
            to,
            subject,
            text,
        )


class BrevoEmailProvider:
    def __init__(self, api_key: str, from_address: str, from_name: str):
        missing = [
            name
            for name, value in (
                ("BREVO_API_KEY", api_key),
                ("EMAIL_FROM_ADDRESS", from_address),
            )
            if not value
        ]
        if missing:
            raise EmailError(
                f"EMAIL_PROVIDER=brevo but these are unset: {', '.join(missing)}"
            )
        self._api_key = api_key
        self._sender = {"email": from_address, "name": from_name}

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        import requests

        try:
            response = requests.post(
                BREVO_ENDPOINT,
                json={
                    "sender": self._sender,
                    "to": [{"email": to}],
                    "subject": subject,
                    "htmlContent": html,
                    "textContent": text,
                },
                headers={
                    "api-key": self._api_key,
                    "content-type": "application/json",
                    "accept": "application/json",
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            raise EmailError(f"Could not reach Brevo: {exc}") from exc

        if response.status_code >= 400:
            # Brevo puts the useful detail in the body, not the status line.
            raise EmailError(
                f"Brevo rejected the message ({response.status_code}): "
                f"{response.text[:300]}"
            )


@lru_cache
def get_email_provider() -> EmailProvider:
    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "console":
        return ConsoleEmailProvider()
    if provider == "brevo":
        return BrevoEmailProvider(
            settings.BREVO_API_KEY,
            settings.EMAIL_FROM_ADDRESS,
            settings.EMAIL_FROM_NAME,
        )
    raise EmailError(f"Unknown EMAIL_PROVIDER: {settings.EMAIL_PROVIDER!r}")
