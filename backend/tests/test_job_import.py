import pytest

from app.services.llm import LLMError
from tests.conftest import PNG_BYTES

PARSE = "/api/v1/jobs/parse-screenshots"


def _upload(client, headers, count=1, mime="image/png", data=PNG_BYTES):
    files = [("files", (f"shot{i}.png", data, mime)) for i in range(count)]
    return client.post(PARSE, headers=headers, files=files)


# ── The happy path ───────────────────────────────────────────────────────────


def test_a_screenshot_becomes_a_prefilled_job(client, auth_headers, fake_llm):
    r = _upload(client, auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["title"] == "Backend Engineer"
    assert body["company"] == "Northwind Labs"
    assert body["apply_by"] == "2026-09-30"
    assert "FastAPI" in body["description"]
    assert body["confidence"] == "high"


def test_parsing_saves_nothing(client, auth_headers, fake_llm):
    """Extraction is fuzzy, so the user confirms before anything is stored."""
    _upload(client, auth_headers)
    assert client.get("/api/v1/jobs", headers=auth_headers).json() == []


def test_several_screenshots_are_sent_as_one_posting(client, auth_headers, fake_llm):
    r = _upload(client, auth_headers, count=3)
    assert r.status_code == 200

    call = fake_llm.calls[-1]
    assert len(call["images"]) == 3
    # A phone screenshot only captures part of a long posting, so the model must
    # be told these are pieces of one job rather than three separate ones.
    assert "one job posting" in call["prompt"]


def test_the_model_is_told_to_transcribe_not_summarise(client, auth_headers, fake_llm):
    _upload(client, auth_headers)
    system = fake_llm.calls[-1]["system"]
    # A summarised description silently produces a worse rewrite later.
    assert "TRANSCRIBING" in system
    assert "verbatim" in system


def test_the_model_is_told_not_to_lose_text_across_images(
    client, auth_headers, fake_llm
):
    """The failure this guards against: a second screenshot showing a fragment
    of the description replacing the fuller version from the first."""
    _upload(client, auth_headers, count=2)
    system = fake_llm.calls[-1]["system"]

    assert "ONE posting" in system
    assert "must NOT replace a fuller version" in system
    assert "longest coherent version" in system


# ── Refusals ─────────────────────────────────────────────────────────────────


def test_a_non_image_is_rejected(client, auth_headers, fake_llm):
    r = client.post(
        PARSE,
        headers=auth_headers,
        files=[("files", ("resume.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    assert r.status_code == 415
    assert fake_llm.calls == []


def test_too_many_screenshots_is_rejected(client, auth_headers, fake_llm):
    r = _upload(client, auth_headers, count=9)
    # Each image costs tokens, so the batch is bounded.
    assert r.status_code == 413
    assert fake_llm.calls == []


def test_an_oversized_image_is_rejected(client, auth_headers, fake_llm, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "MAX_SCREENSHOT_BYTES", 100)
    r = _upload(client, auth_headers, data=PNG_BYTES * 100)
    assert r.status_code == 413
    assert fake_llm.calls == []


def test_an_empty_file_is_rejected(client, auth_headers, fake_llm):
    r = _upload(client, auth_headers, data=b"")
    assert r.status_code == 400


def test_unreadable_images_give_a_useful_message(client, auth_headers, fake_llm):
    fake_llm.image_payload = {
        "title": None,
        "company": None,
        "description": None,
        "confidence": "unreadable",
    }
    r = _upload(client, auth_headers)
    assert r.status_code == 422
    assert "clearer screenshot" in r.json()["detail"]


def test_a_result_with_no_title_or_company_is_refused(client, auth_headers, fake_llm):
    """Description alone is not a job — refuse rather than prefill a blank form."""
    fake_llm.image_payload = {
        "title": None,
        "company": None,
        "description": "Some text that is not a posting.",
        "confidence": "high",
    }
    assert _upload(client, auth_headers).status_code == 422


def test_a_provider_failure_is_reported_not_swallowed(client, auth_headers, fake_llm):
    fake_llm.error = LLMError("quota exceeded")
    r = _upload(client, auth_headers)
    assert r.status_code == 422
    assert "quota exceeded" in r.json()["detail"]


def test_parsing_requires_authentication(client):
    r = client.post(
        PARSE, files=[("files", ("shot.png", PNG_BYTES, "image/png"))]
    )
    assert r.status_code == 401


# ── Field handling ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_date", ["30/09/2026", "next Friday", "", "2026-13-45"])
def test_an_unparseable_deadline_is_dropped(client, auth_headers, fake_llm, bad_date):
    fake_llm.image_payload = {**fake_llm.image_payload, "apply_by": bad_date}
    r = _upload(client, auth_headers)
    assert r.status_code == 200
    # A wrong deadline is worse than none — it would drive a false reminder.
    assert r.json()["apply_by"] is None


def test_a_missing_field_comes_back_null_not_invented(client, auth_headers, fake_llm):
    fake_llm.image_payload = {**fake_llm.image_payload, "location": None}
    assert _upload(client, auth_headers).json()["location"] is None


def test_an_unknown_confidence_value_degrades_to_partial(client, auth_headers, fake_llm):
    fake_llm.image_payload = {**fake_llm.image_payload, "confidence": "extremely sure"}
    assert _upload(client, auth_headers).json()["confidence"] == "partial"


def test_partial_confidence_is_passed_through(client, auth_headers, fake_llm):
    """Tells the UI to warn that the description was cut off."""
    fake_llm.image_payload = {**fake_llm.image_payload, "confidence": "partial"}
    assert _upload(client, auth_headers).json()["confidence"] == "partial"
