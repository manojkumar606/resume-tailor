"""Retrying a busy model.

Written after a real 503 in production on 2026-08-29: "This model is currently
experiencing high demand." One attempt, then a failed row, and the user was
told to do it again by hand. The raw response dict was shown to them as well.
"""

import pytest

from app.services import llm as llm_module
from app.services.llm import GeminiProvider, LLMError, LLMUnavailable


class FakeAPIError(Exception):
    """Stands in for google.genai.errors.APIError, which needs a real response
    object to construct. Only `code` and `status` are read."""

    def __init__(self, code: int, status: str = "UNAVAILABLE"):
        super().__init__(f"{code} {status}")
        self.code = code
        self.status = status


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeResponse:
    def __init__(self, text):
        self.text = text


OK = FakeResponse('{"tailored_text": "x", "match_score": 50}')


@pytest.fixture
def provider(monkeypatch):
    """A GeminiProvider whose client and sleep are both fake, so the retry
    logic is exercised without a network or a real wait."""
    monkeypatch.setattr(llm_module, "_sleep", lambda _s: None)
    # Patch the module the provider imports inside _generate.
    import google.genai.errors as real_errors

    monkeypatch.setattr(real_errors, "APIError", FakeAPIError)

    def _make(outcomes):
        p = GeminiProvider.__new__(GeminiProvider)
        p.model_name = "fake-model"
        p._client = type("C", (), {"models": FakeModels(outcomes)})()
        return p

    return _make


# --- retrying ---------------------------------------------------------------


def test_a_503_is_retried_and_can_succeed(provider):
    p = provider([FakeAPIError(503), OK])
    result = p.generate_json(system="s", prompt="p")
    assert result["match_score"] == 50
    assert p._client.models.calls == 2


def test_it_keeps_trying_up_to_the_limit(provider, monkeypatch):
    monkeypatch.setattr(llm_module.settings, "LLM_MAX_ATTEMPTS", 3)
    p = provider([FakeAPIError(503), FakeAPIError(503), OK])
    p.generate_json(system="s", prompt="p")
    assert p._client.models.calls == 3


def test_it_gives_up_after_the_limit(provider, monkeypatch):
    monkeypatch.setattr(llm_module.settings, "LLM_MAX_ATTEMPTS", 3)
    p = provider([FakeAPIError(503)] * 3)

    with pytest.raises(LLMUnavailable):
        p.generate_json(system="s", prompt="p")
    assert p._client.models.calls == 3


def test_rate_limiting_is_retried_too(provider):
    p = provider([FakeAPIError(429, "RESOURCE_EXHAUSTED"), OK])
    p.generate_json(system="s", prompt="p")
    assert p._client.models.calls == 2


def test_a_network_error_is_retried(provider):
    p = provider([ConnectionError("connection reset"), OK])
    p.generate_json(system="s", prompt="p")
    assert p._client.models.calls == 2


# --- not retrying -----------------------------------------------------------


def test_a_bad_request_is_not_retried(provider):
    """A 400 fails identically every time. Retrying spends the user's time and
    our quota to reach the same answer."""
    p = provider([FakeAPIError(400, "INVALID_ARGUMENT")])

    with pytest.raises(LLMError) as caught:
        p.generate_json(system="s", prompt="p")
    assert not isinstance(caught.value, LLMUnavailable)
    assert p._client.models.calls == 1


def test_bad_credentials_are_not_retried(provider):
    p = provider([FakeAPIError(403, "PERMISSION_DENIED")])

    with pytest.raises(LLMError):
        p.generate_json(system="s", prompt="p")
    assert p._client.models.calls == 1


def test_an_unparseable_response_is_not_retried(provider):
    """The model answered; it just did not answer with JSON. Asking again is
    unlikely to help and the message already says what went wrong."""
    p = provider([FakeResponse("this is not json")])

    with pytest.raises(LLMError):
        p.generate_json(system="s", prompt="p")
    assert p._client.models.calls == 1


# --- what the user is shown -------------------------------------------------


def test_the_message_is_a_sentence_not_a_response_dump(provider, monkeypatch):
    """The real 503 reached the screen as:

        Gemini request failed: 503 UNAVAILABLE. {'error': {'code': 503, ...}}

    That is a log line, not something to show somebody waiting on a resume.
    """
    monkeypatch.setattr(llm_module.settings, "LLM_MAX_ATTEMPTS", 1)
    p = provider([FakeAPIError(503)])

    with pytest.raises(LLMError) as caught:
        p.generate_json(system="s", prompt="p")

    message = str(caught.value)
    assert "busy" in message
    assert "try again" in message.lower()
    for leak in ("{", "}", "'error'", "503", "UNAVAILABLE", "Traceback"):
        assert leak not in message, f"{leak!r} leaked into the user-facing message"


def test_the_rate_limit_message_says_what_to_do(provider, monkeypatch):
    monkeypatch.setattr(llm_module.settings, "LLM_MAX_ATTEMPTS", 1)
    p = provider([FakeAPIError(429, "RESOURCE_EXHAUSTED")])

    with pytest.raises(LLMError) as caught:
        p.generate_json(system="s", prompt="p")
    assert "few minutes" in str(caught.value)


def test_a_credentials_problem_does_not_blame_the_user(provider, monkeypatch):
    monkeypatch.setattr(llm_module.settings, "LLM_MAX_ATTEMPTS", 1)
    p = provider([FakeAPIError(401, "UNAUTHENTICATED")])

    with pytest.raises(LLMError) as caught:
        p.generate_json(system="s", prompt="p")
    assert "not yours" in str(caught.value)


# --- backoff ----------------------------------------------------------------


def test_the_wait_grows_between_attempts(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "LLM_RETRY_BASE_SECONDS", 2.0)
    first = llm_module._backoff_seconds(1)
    second = llm_module._backoff_seconds(2)
    assert 2.0 <= first <= 2.5
    assert 4.0 <= second <= 5.0


def test_the_wait_is_jittered(monkeypatch):
    """Identical delays would make simultaneous retries hit the model in step,
    which is how a busy service stays busy."""
    monkeypatch.setattr(llm_module.settings, "LLM_RETRY_BASE_SECONDS", 2.0)
    samples = {llm_module._backoff_seconds(1) for _ in range(20)}
    assert len(samples) > 1


def test_screenshot_import_gets_the_same_retry(provider):
    """Both call sites go through _generate, so vision imports are covered by
    the same logic rather than needing their own."""
    p = provider([FakeAPIError(503), OK])
    p.generate_json_from_images(system="s", prompt="p", images=[(b"x", "image/png")])
    assert p._client.models.calls == 2
