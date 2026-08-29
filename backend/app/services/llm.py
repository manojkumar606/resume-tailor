"""LLM access behind a provider interface.

Nothing above this module imports a vendor SDK. Swapping Gemini for Claude or
adding a fallback provider means adding a class here, not touching the
tailoring logic or the routes.
"""

import json
import logging
import random
import re
import time
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """A provider failure, carrying a message meant for the user.

    Tailoring runs in the background, so this text is written to the row and
    read straight off the screen. It has to be a sentence a person can act on,
    not a status line and a response dict — the technical detail belongs in the
    log, and is put there before this is raised.
    """


class LLMUnavailable(LLMError):
    """Transient: the model was busy or rate limited. Worth trying again."""


# Everything here means "the request was fine, the service could not take it
# right now". A 400 or a 403 would fail identically on every retry, so retrying
# those just wastes the user's time and our quota.
RETRYABLE_CODES = frozenset({429, 500, 502, 503, 504})


def _friendly(code: int | None, status: str | None) -> str:
    """What to tell the user, by status code."""
    if code == 429:
        return (
            "The AI service is rate limited right now. Please try again in a "
            "few minutes."
        )
    if code in {500, 502, 503, 504}:
        return (
            "The AI service is busy at the moment. This usually clears within a "
            "minute or two — please try again."
        )
    if code in {401, 403}:
        return (
            "The AI service rejected our credentials. This is a problem on our "
            "side, not yours."
        )
    if code == 400:
        return "The AI service could not process this request."
    return f"The AI service failed{f' ({status})' if status else ''}. Please try again."


# Module level so tests can replace it and not actually wait.
_sleep = time.sleep


def _backoff_seconds(attempt: int) -> float:
    """Exponential, with jitter so simultaneous retries do not march in step."""
    base = settings.LLM_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
    return base + random.uniform(0, base * 0.25)


class LLMProvider(Protocol):
    model_name: str

    def generate_json(self, *, system: str, prompt: str) -> dict[str, Any]: ...

    def generate_json_from_images(
        self, *, system: str, prompt: str, images: list[tuple[bytes, str]]
    ) -> dict[str, Any]:
        """Same contract, with images. Each entry is (bytes, mime type)."""
        ...


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse a model response that should be JSON.

    Models still wrap JSON in markdown fences even when asked for raw JSON, so
    strip those before giving up.
    """
    if not text or not text.strip():
        raise LLMError("The model returned an empty response")

    cleaned = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError(f"The model did not return valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise LLMError("Expected a JSON object from the model")
    return parsed


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError(
                "GEMINI_API_KEY is not set. Add it to .env to enable tailoring."
            )
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model_name = model

    def _generate(self, *, system: str, contents: Any, temperature: float) -> dict[str, Any]:
        """Call the model, retrying while the failure is worth retrying.

        Retrying is only affordable because tailoring moved to a background
        task: nobody is holding a connection open, so a few seconds of backoff
        costs a slightly later result rather than a timed-out request. A 503
        from an overloaded model is common and almost always clears — surfacing
        it as a dead end made the user redo the work by hand.
        """
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=temperature,
        )

        attempts = max(1, settings.LLM_MAX_ATTEMPTS)
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model_name, contents=contents, config=config
                )
                return _parse_json_response(response.text or "")

            except errors.APIError as exc:
                code = getattr(exc, "code", None)
                status = getattr(exc, "status", None)
                last = attempt == attempts

                if code not in RETRYABLE_CODES or last:
                    logger.error(
                        "Gemini request failed (attempt %s/%s): %s", attempt, attempts, exc
                    )
                    message = _friendly(code, status)
                    if code in RETRYABLE_CODES:
                        raise LLMUnavailable(message) from exc
                    raise LLMError(message) from exc

                delay = _backoff_seconds(attempt)
                logger.warning(
                    "Gemini unavailable (attempt %s/%s, code %s), retrying in %.1fs",
                    attempt, attempts, code, delay,
                )
                _sleep(delay)

            except LLMError:
                # A malformed response from _parse_json_response. Already has a
                # message for the user, and retrying would not change it.
                raise

            except Exception as exc:
                # Network-level: DNS, connection reset, timeout. Worth one more
                # try, for the same reason a 503 is.
                if attempt == attempts:
                    logger.error("Gemini request failed at the network level: %s", exc)
                    raise LLMUnavailable(
                        "Could not reach the AI service. Please try again."
                    ) from exc
                delay = _backoff_seconds(attempt)
                logger.warning(
                    "Gemini network error (attempt %s/%s), retrying in %.1fs: %s",
                    attempt, attempts, delay, exc,
                )
                _sleep(delay)

        # Unreachable: the loop either returns or raises on its final attempt.
        raise LLMError("The AI service failed. Please try again.")

    def generate_json(self, *, system: str, prompt: str) -> dict[str, Any]:
        return self._generate(system=system, contents=prompt, temperature=0.4)

    def generate_json_from_images(
        self, *, system: str, prompt: str, images: list[tuple[bytes, str]]
    ) -> dict[str, Any]:
        from google.genai import types

        # Temperature 0: this is transcription, not writing. Any creativity here
        # shows up as invented job details.
        parts = [
            types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images
        ]
        return self._generate(
            system=system, contents=[*parts, prompt], temperature=0.0
        )


def get_llm_provider() -> LLMProvider:
    """FastAPI dependency. Overridden in tests with a deterministic fake."""
    provider = settings.LLM_PROVIDER.lower()
    if provider == "gemini":
        return GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
    raise LLMError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER!r}")
