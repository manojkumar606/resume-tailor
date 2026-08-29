"""The asynchronous run: what happens when nobody is holding the connection.

Two failure modes matter and neither is visible by inspection. A run that
raises must land on `failed` with a reason, and a run whose process died must
not sit on `running` for ever with a client polling it.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.models.tailoring import Tailoring, TailoringStatus
from app.services.llm import LLMError

TAILORINGS = "/api/v1/tailorings"


def _setup(client, headers, docx_bytes, job_payload):
    client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("resume.docx", docx_bytes, "application/octet-stream")},
    )
    return client.post("/api/v1/jobs", headers=headers, json=job_payload).json()


def _start(client, headers, job):
    r = client.post(TAILORINGS, headers=headers, json={"job_id": job["id"]})
    assert r.status_code == 202, r.text
    return r.json()


# --- the happy path, as the client actually experiences it ------------------


def test_polling_the_row_is_how_the_client_learns_it_finished(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    started = _start(client, auth_headers, job)

    polled = client.get(f"{TAILORINGS}/{started['id']}", headers=auth_headers).json()
    assert polled["id"] == started["id"]
    assert polled["status"] == "succeeded"


def test_the_result_survives_a_page_refresh(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    """Nothing about the result lives in the browser, so reloading finds it."""
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    _start(client, auth_headers, job)

    listed = client.get(
        f"{TAILORINGS}?job_id={job['id']}", headers=auth_headers
    ).json()
    assert len(listed) == 1
    assert listed[0]["status"] == "succeeded"


def test_the_document_is_downloadable_once_the_run_finishes(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    started = _start(client, auth_headers, job)

    r = client.get(f"{TAILORINGS}/{started['id']}/download", headers=auth_headers)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


# --- failure inside the run ------------------------------------------------


def test_a_provider_error_is_recorded_not_lost(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    fake_llm.error = LLMError("the model is having a bad day")
    started = _start(client, auth_headers, job)

    row = client.get(f"{TAILORINGS}/{started['id']}", headers=auth_headers).json()
    assert row["status"] == "failed"
    assert "bad day" in row["error"]
    assert row["completed_at"] is not None


def test_an_unexpected_crash_still_ends_on_failed(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    """Not an LLMError — something nobody predicted. The row must not be left
    running, because a spinner that never stops is worse than an error."""
    fake_llm.error = RuntimeError("something nobody thought of")
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    started = _start(client, auth_headers, job)

    row = client.get(f"{TAILORINGS}/{started['id']}", headers=auth_headers).json()
    assert row["status"] == "failed"
    assert row["error"]
    assert row["completed_at"] is not None


def test_a_failed_run_cannot_be_downloaded(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    fake_llm.error = LLMError("nope")
    started = _start(client, auth_headers, job)

    r = client.get(f"{TAILORINGS}/{started['id']}/download", headers=auth_headers)
    assert r.status_code == 409


# --- the process died mid-run ----------------------------------------------


def _strand(db_session, tailoring_id, *, minutes_ago: int) -> Tailoring:
    """Put a row in the state a container restart leaves behind: running, with
    nothing alive that will ever finish it."""
    row = db_session.get(Tailoring, tailoring_id)
    row.status = TailoringStatus.RUNNING
    row.tailored_text = None
    row.completed_at = None
    row.error = None
    row.updated_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    db_session.commit()
    return row


def test_a_run_stranded_by_a_restart_is_failed_on_read(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    import uuid as _uuid

    job = _setup(client, auth_headers, docx_bytes, job_payload)
    started = _start(client, auth_headers, job)
    _strand(
        db_session,
        _uuid.UUID(started["id"]),
        minutes_ago=settings.TAILORING_TIMEOUT_MINUTES + 1,
    )

    row = client.get(f"{TAILORINGS}/{started['id']}", headers=auth_headers).json()
    assert row["status"] == "failed"
    assert "interrupted" in row["error"]


def test_a_run_that_is_merely_slow_is_left_alone(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    """The reaper must not shoot a run that is still legitimately working."""
    import uuid as _uuid

    job = _setup(client, auth_headers, docx_bytes, job_payload)
    started = _start(client, auth_headers, job)
    _strand(db_session, _uuid.UUID(started["id"]), minutes_ago=0)

    row = client.get(f"{TAILORINGS}/{started['id']}", headers=auth_headers).json()
    assert row["status"] == "running"


def test_the_list_view_reaps_too(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    """The board and history read the list, not the detail, so a stranded row
    would otherwise show as still running there."""
    import uuid as _uuid

    job = _setup(client, auth_headers, docx_bytes, job_payload)
    started = _start(client, auth_headers, job)
    _strand(
        db_session,
        _uuid.UUID(started["id"]),
        minutes_ago=settings.TAILORING_TIMEOUT_MINUTES + 1,
    )

    listed = client.get(TAILORINGS, headers=auth_headers).json()
    assert listed[0]["status"] == "failed"


# --- tenancy still holds ---------------------------------------------------


def test_another_user_cannot_poll_someone_elses_run(
    client, make_user, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    started = _start(client, auth_headers, job)

    intruder = make_user("intruder@example.com")
    r = client.get(f"{TAILORINGS}/{started['id']}", headers=intruder)
    assert r.status_code == 404


def test_only_one_row_is_created_per_request(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    _start(client, auth_headers, job)

    rows = db_session.scalars(select(Tailoring)).all()
    assert len(rows) == 1
    # And the model was called exactly once — not once per poll.
    assert len(fake_llm.calls) == 1
