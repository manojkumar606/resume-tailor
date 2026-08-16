import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.application import Application
from app.models.tailoring import Tailoring

APPS = "/api/v1/applications"
QUICK = "/api/v1/applications/quick"
JOBS = "/api/v1/jobs"
RESUMES = "/api/v1/resumes"
TAILORINGS = "/api/v1/tailorings"

QUICK_PAYLOAD = {"title": "Backend Engineer", "company": "Northwind"}


def _tailored_card(client, headers, docx_bytes, job_payload):
    """A card whose job has a finished tailoring, still sitting in Saved."""
    client.post(
        RESUMES,
        headers=headers,
        files={"file": ("cv.docx", docx_bytes, "application/octet-stream")},
    )
    job = client.post(JOBS, headers=headers, json=job_payload).json()
    tailoring = client.post(
        TAILORINGS, headers=headers, json={"job_id": job["id"]}
    ).json()
    card = client.post(
        APPS,
        headers=headers,
        json={"job_id": job["id"], "tailoring_id": tailoring["id"]},
    ).json()
    return card, tailoring


def _age_tailoring(db_session, tailoring_id, hours):
    row = db_session.scalar(
        select(Tailoring).where(Tailoring.id == uuid.UUID(tailoring_id))
    )
    row.completed_at = datetime.now(UTC) - timedelta(hours=hours)
    db_session.commit()


# ── Where it came from ───────────────────────────────────────────────────────


def test_source_defaults_to_unknown(client, auth_headers):
    r = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD)
    # Not recording it is the honest default — most people will not bother.
    assert r.json()["source"] == "unknown"


def test_source_can_be_set_on_quick_add(client, auth_headers):
    r = client.post(
        QUICK, headers=auth_headers, json={**QUICK_PAYLOAD, "applied_via": "referral"}
    )
    assert r.json()["source"] == "referral"


def test_source_can_be_changed_later(client, auth_headers):
    card = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()
    r = client.patch(
        f"{APPS}/{card['id']}", headers=auth_headers, json={"source": "company_site"}
    )
    assert r.json()["source"] == "company_site"


def test_an_unknown_source_is_rejected(client, auth_headers):
    card = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()
    r = client.patch(
        f"{APPS}/{card['id']}", headers=auth_headers, json={"source": "carrier_pigeon"}
    )
    assert r.status_code == 422


# ── Interview date ───────────────────────────────────────────────────────────


def test_an_interview_date_can_be_set_and_cleared(client, auth_headers):
    card = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()
    assert card["interview_at"] is None

    when = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    r = client.patch(
        f"{APPS}/{card['id']}", headers=auth_headers, json={"interview_at": when}
    )
    assert r.json()["interview_at"] is not None

    r = client.patch(
        f"{APPS}/{card['id']}", headers=auth_headers, json={"interview_at": None}
    )
    assert r.json()["interview_at"] is None


# ── "Did you apply?" ─────────────────────────────────────────────────────────


def test_no_prompt_without_a_tailoring(client, auth_headers):
    """Nothing has been prepared, so there is nothing to have applied with."""
    r = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD)
    assert r.json()["needs_apply_prompt"] is False


def test_no_prompt_immediately_after_tailoring(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    """Asking while they are still reading the rewrite would be absurd."""
    card, _ = _tailored_card(client, auth_headers, docx_bytes, job_payload)
    assert card["needs_apply_prompt"] is False


def test_the_prompt_appears_once_the_tailoring_is_old_enough(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    card, tailoring = _tailored_card(client, auth_headers, docx_bytes, job_payload)
    _age_tailoring(db_session, tailoring["id"], hours=24)

    r = client.get(f"{APPS}/{card['id']}", headers=auth_headers)
    # A resume was prepared and the board still says Saved — worth asking.
    assert r.json()["needs_apply_prompt"] is True


def test_answering_yes_moves_the_card_and_ends_the_prompt(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    card, tailoring = _tailored_card(client, auth_headers, docx_bytes, job_payload)
    _age_tailoring(db_session, tailoring["id"], hours=24)

    r = client.patch(
        f"{APPS}/{card['id']}", headers=auth_headers, json={"status": "applied"}
    )
    assert r.json()["status"] == "applied"
    assert r.json()["needs_apply_prompt"] is False
    assert r.json()["applied_at"] is not None


def test_answering_not_yet_silences_it_permanently(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    card, tailoring = _tailored_card(client, auth_headers, docx_bytes, job_payload)
    _age_tailoring(db_session, tailoring["id"], hours=24)

    r = client.patch(
        f"{APPS}/{card['id']}",
        headers=auth_headers,
        json={"dismiss_apply_prompt": True},
    )
    assert r.json()["needs_apply_prompt"] is False
    # Still in Saved — they said not yet, not never.
    assert r.json()["status"] == "saved"

    # Being asked the same thing twice is what makes prompts hated.
    again = client.get(f"{APPS}/{card['id']}", headers=auth_headers)
    assert again.json()["needs_apply_prompt"] is False


def test_dismissing_is_not_stored_as_a_column_value(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    """The flag is an action; what persists is when it happened."""
    card, tailoring = _tailored_card(client, auth_headers, docx_bytes, job_payload)
    _age_tailoring(db_session, tailoring["id"], hours=24)

    client.patch(
        f"{APPS}/{card['id']}",
        headers=auth_headers,
        json={"dismiss_apply_prompt": True},
    )

    db_session.expire_all()
    row = db_session.scalar(
        select(Application).where(Application.id == uuid.UUID(card["id"]))
    )
    assert row.apply_prompt_dismissed_at is not None


def test_a_failed_tailoring_never_prompts(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    from app.services.llm import LLMError

    client.post(
        RESUMES,
        headers=auth_headers,
        files={"file": ("cv.docx", docx_bytes, "application/octet-stream")},
    )
    job = client.post(JOBS, headers=auth_headers, json=job_payload).json()

    fake_llm.error = LLMError("quota exceeded")
    client.post(TAILORINGS, headers=auth_headers, json={"job_id": job["id"]})
    fake_llm.error = None

    failed = client.get(
        f"{TAILORINGS}?job_id={job['id']}", headers=auth_headers
    ).json()[0]
    card = client.post(
        APPS,
        headers=auth_headers,
        json={"job_id": job["id"], "tailoring_id": failed["id"]},
    ).json()

    _age_tailoring(db_session, failed["id"], hours=48)
    r = client.get(f"{APPS}/{card['id']}", headers=auth_headers)
    # Nothing was produced, so there was nothing to apply with.
    assert r.json()["needs_apply_prompt"] is False
