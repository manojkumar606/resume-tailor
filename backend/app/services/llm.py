"""LLM access behind a provider interface.

Nothing above this module imports a vendor SDK. Swapping Gemini for Claude or
adding a fallback provider means adding a class here, not touching the
tailoring logic or the routes.
"""

import json
import re
from typing import Any, Protocol

from app.core.config import settings


class LLMError(Exception):
    """Raised for any provider failure — network, quota, or unparseable output."""


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
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    temperature=temperature,
                ),
            )
        except Exception as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc

        return _parse_json_response(response.text or "")

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
