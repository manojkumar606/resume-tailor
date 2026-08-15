"""Read a job posting out of screenshots.

Why screenshots rather than fetching the URL: the major boards block
server-side fetching outright — LinkedIn and Naukri need auth and ban
datacenter IPs, Indeed sits behind Cloudflare. A screenshot has already been
rendered by the user's own logged-in browser, so none of that applies. It is
the one approach that works on the sites people actually use.

The result is never saved directly. It fills a form the user confirms, because
extraction is fuzzy and a silently-wrong company name is worse than no import.
"""

from datetime import date
from typing import Any

from app.core.config import settings
from app.services.llm import LLMError, LLMProvider

SUPPORTED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class ImportError_(Exception):
    """Raised when the screenshots cannot be read. Message is user-facing."""


IMPORT_SYSTEM = """You extract job posting details from screenshots.

You are TRANSCRIBING, not summarising or writing. Rules:
- Copy the job description text exactly as it appears. Do not condense it, do
  not rephrase it, do not fill in gaps.
- If a field is not visible in the images, return null for it. Never guess a
  company name from a logo you are unsure of, and never invent a deadline.
- Several screenshots may be different parts of ONE posting. Stitch the
  description together in reading order and do not repeat overlapping text.
- Ignore anything that is not part of the posting: navigation, adverts,
  "similar jobs" lists, cookie banners, the user's own browser chrome.

Return ONLY a JSON object with exactly these keys:
{
  "title": "the job title, or null",
  "company": "the hiring company, or null",
  "location": "location as written, or null",
  "apply_by": "closing date as YYYY-MM-DD, or null if none is shown",
  "description": "the posting body, transcribed verbatim, or null",
  "confidence": "high | partial | unreadable"
}

Use "partial" when you can read the posting but the description is clearly cut
off, and "unreadable" when the images are not a job posting or are illegible.
Do not wrap the JSON in markdown fences."""


def _clean(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned[:limit] if cleaned else None


def _parse_date(value: Any) -> date | None:
    """Only accept a real ISO date. A malformed one is dropped rather than
    guessed at — a wrong deadline is worse than no deadline."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_screenshots(
    provider: LLMProvider, images: list[tuple[bytes, str]]
) -> dict[str, Any]:
    """Return the fields read from the images, for the user to confirm."""
    if not images:
        raise ImportError_("No screenshots were uploaded.")
    if len(images) > settings.MAX_SCREENSHOTS:
        raise ImportError_(
            f"Please upload at most {settings.MAX_SCREENSHOTS} screenshots at once."
        )

    prompt = (
        f"These {len(images)} image(s) show one job posting. Extract it."
        if len(images) > 1
        else "This image shows a job posting. Extract it."
    )

    try:
        payload = provider.generate_json_from_images(
            system=IMPORT_SYSTEM, prompt=prompt, images=images
        )
    except LLMError as exc:
        raise ImportError_(f"Could not read the screenshots: {exc}") from exc

    confidence = payload.get("confidence")
    if confidence not in {"high", "partial", "unreadable"}:
        confidence = "partial"

    title = _clean(payload.get("title"), 300)
    company = _clean(payload.get("company"), 200)

    if confidence == "unreadable" or not (title or company):
        raise ImportError_(
            "That doesn't look like a job posting, or the text was too small to "
            "read. Try a clearer screenshot, or type the details in."
        )

    return {
        "title": title,
        "company": company,
        "location": _clean(payload.get("location"), 200),
        "apply_by": _parse_date(payload.get("apply_by")),
        "description": _clean(payload.get("description"), 50_000),
        "confidence": confidence,
    }
