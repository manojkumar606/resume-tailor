import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models.application import Application

APPS = "/api/v1/applications"
QUICK = "/api/v1/applications/quick"
JOBS = "/api/v1/jobs"


QUICK_PAYLOAD = {
    "title": "Backend Engineer",
    "company": "Northwind Labs",
    "location": "Remote",
    "source_url": "https://example.com/jobs/123",
}


# ── Quick add: the tracker must work without the model ────────────────────────


def test_quick_add_creates_a_card_with_no_description(client, auth_headers):
    r = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD)
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["status"] == "saved"
    assert body["job"]["title"] == "Backend Engineer"
    assert body["job"]["source_url"] == QUICK_PAYLOAD["source_url"]
    # The whole point: logging an application must not require a job posting.
    assert body["job"]["has_description"] is False
    assert body["tailoring"] is None


def test_quick_add_as_already_applied_stamps_the_date(client, auth_headers):
    r = client.post(
        QUICK, headers=auth_headers, json={**QUICK_PAYLOAD, "status": "applied"}
    )
    assert r.status_code == 201
    # Someone logging a past application should not also have to set the date.
    assert r.json()["applied_at"] is not None


def test_quick_add_rejects_a_description_too_short_to_tailor(client, auth_headers):
    r = client.post(
        QUICK, headers=auth_headers, json={**QUICK_PAYLOAD, "description": "short"}
    )
    assert r.status_code == 422
    # Empty is a choice; two words is a mistake.
    assert "at least" in r.text


def test_quick_add_treats_a_blank_description_as_absent(client, auth_headers):
    r = client.post(
        QUICK, headers=auth_headers, json={**QUICK_PAYLOAD, "description": "   "}
    )
    assert r.status_code == 201
    assert r.json()["job"]["has_description"] is False


# ── Tracking an existing job ──────────────────────────────────────────────────


def test_track_an_existing_job(client, auth_headers, job_payload):
    job = client.post(JOBS, headers=auth_headers, json=job_payload).json()
    r = client.post(APPS, headers=auth_headers, json={"job_id": job["id"]})
    assert r.status_code == 201
    assert r.json()["job"]["id"] == job["id"]
    assert r.json()["job"]["has_description"] is True


def test_the_same_job_cannot_be_tracked_twice(client, auth_headers, job_payload):
    job = client.post(JOBS, headers=auth_headers, json=job_payload).json()
    assert client.post(APPS, headers=auth_headers, json={"job_id": job["id"]}).status_code == 201

    r = client.post(APPS, headers=auth_headers, json={"job_id": job["id"]})
    # Two cards for one role makes the board confusing and the funnel wrong.
    assert r.status_code == 409
    assert "already on your board" in r.json()["detail"]


def test_tracking_an_unknown_job_is_404(client, auth_headers):
    r = client.post(
        APPS,
        headers=auth_headers,
        json={"job_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


# ── Moving cards ──────────────────────────────────────────────────────────────


def test_moving_to_applied_stamps_applied_at(client, auth_headers):
    app_ = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()
    assert app_["applied_at"] is None

    r = client.patch(
        f"{APPS}/{app_['id']}", headers=auth_headers, json={"status": "applied"}
    )
    assert r.status_code == 200
    assert r.json()["applied_at"] is not None


def test_applied_at_is_not_overwritten_on_later_moves(client, auth_headers):
    app_ = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()
    first = client.patch(
        f"{APPS}/{app_['id']}", headers=auth_headers, json={"status": "applied"}
    ).json()["applied_at"]

    later = client.patch(
        f"{APPS}/{app_['id']}", headers=auth_headers, json={"status": "interviewing"}
    ).json()["applied_at"]

    # The date they applied does not change when they reach the interview.
    assert later == first


def test_moving_straight_to_rejected_still_stamps_applied_at(client, auth_headers):
    app_ = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()
    r = client.patch(
        f"{APPS}/{app_['id']}", headers=auth_headers, json={"status": "rejected"}
    )
    # You cannot be rejected from something you never applied to.
    assert r.json()["applied_at"] is not None


def test_notes_can_be_set_and_cleared(client, auth_headers):
    app_ = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()

    r = client.patch(
        f"{APPS}/{app_['id']}",
        headers=auth_headers,
        json={"notes": "Referred by Priya, recruiter calling Tuesday"},
    )
    assert "Priya" in r.json()["notes"]

    r = client.patch(f"{APPS}/{app_['id']}", headers=auth_headers, json={"notes": None})
    assert r.json()["notes"] is None


# ── Derived fields ────────────────────────────────────────────────────────────


def test_a_fresh_application_is_not_stale(client, auth_headers):
    r = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD)
    assert r.json()["is_stale"] is False
    assert r.json()["days_since_update"] == 0


def test_applied_goes_stale_after_the_threshold(
    client, auth_headers, db_session, monkeypatch
):
    from app.core import config

    monkeypatch.setattr(config.settings, "STALE_APPLICATION_DAYS", 14)

    app_ = client.post(
        QUICK, headers=auth_headers, json={**QUICK_PAYLOAD, "status": "applied"}
    ).json()

    row = db_session.scalar(select(Application).where(Application.id == uuid.UUID(app_["id"])))
    row.updated_at = datetime.now(UTC) - timedelta(days=20)
    db_session.commit()

    r = client.get(f"{APPS}/{app_['id']}", headers=auth_headers)
    assert r.json()["is_stale"] is True
    assert r.json()["days_since_update"] >= 14


def test_saved_never_goes_stale(client, auth_headers, db_session):
    """Nothing to chase on a job you have not applied to yet."""
    app_ = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()

    row = db_session.scalar(select(Application).where(Application.id == uuid.UUID(app_["id"])))
    row.updated_at = datetime.now(UTC) - timedelta(days=90)
    db_session.commit()

    assert client.get(f"{APPS}/{app_['id']}", headers=auth_headers).json()["is_stale"] is False


def test_interviewing_never_goes_stale(client, auth_headers, db_session):
    app_ = client.post(
        QUICK, headers=auth_headers, json={**QUICK_PAYLOAD, "status": "interviewing"}
    ).json()

    row = db_session.scalar(select(Application).where(Application.id == uuid.UUID(app_["id"])))
    row.updated_at = datetime.now(UTC) - timedelta(days=90)
    db_session.commit()

    assert client.get(f"{APPS}/{app_['id']}", headers=auth_headers).json()["is_stale"] is False


def test_deadline_countdown(client, auth_headers):
    deadline = date.today() + timedelta(days=5)
    r = client.post(
        QUICK,
        headers=auth_headers,
        json={**QUICK_PAYLOAD, "apply_by": deadline.isoformat()},
    )
    assert r.json()["days_until_deadline"] == 5


def test_a_passed_deadline_reports_negative(client, auth_headers):
    deadline = date.today() - timedelta(days=3)
    r = client.post(
        QUICK,
        headers=auth_headers,
        json={**QUICK_PAYLOAD, "apply_by": deadline.isoformat()},
    )
    assert r.json()["days_until_deadline"] == -3


def test_no_deadline_reports_none(client, auth_headers):
    r = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD)
    assert r.json()["days_until_deadline"] is None


# ── Board listing ─────────────────────────────────────────────────────────────


def test_list_returns_the_whole_board(client, auth_headers):
    for i, status_value in enumerate(["saved", "applied", "interviewing"]):
        client.post(
            QUICK,
            headers=auth_headers,
            json={**QUICK_PAYLOAD, "title": f"Role {i}", "status": status_value},
        )

    r = client.get(APPS, headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 3
    # Each card carries its job, so the board needs one request, not one per card.
    assert all(card["job"]["title"] for card in r.json())


def test_list_can_filter_by_status(client, auth_headers):
    client.post(QUICK, headers=auth_headers, json={**QUICK_PAYLOAD, "title": "A"})
    client.post(
        QUICK,
        headers=auth_headers,
        json={**QUICK_PAYLOAD, "title": "B", "status": "applied"},
    )

    r = client.get(f"{APPS}?status=applied", headers=auth_headers)
    assert len(r.json()) == 1
    assert r.json()[0]["job"]["title"] == "B"


# ── Deletion ──────────────────────────────────────────────────────────────────


def test_delete_removes_the_card_but_keeps_the_job(client, auth_headers, job_payload):
    job = client.post(JOBS, headers=auth_headers, json=job_payload).json()
    app_ = client.post(APPS, headers=auth_headers, json={"job_id": job["id"]}).json()

    assert client.delete(f"{APPS}/{app_['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"{APPS}/{app_['id']}", headers=auth_headers).status_code == 404
    # "Stop tracking" must not destroy the job or any tailoring done for it.
    assert client.get(f"{JOBS}/{job['id']}", headers=auth_headers).status_code == 200


# ── Tenant isolation ──────────────────────────────────────────────────────────


def test_applications_are_not_visible_across_tenants(client, make_user):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    app_ = client.post(QUICK, headers=alice, json=QUICK_PAYLOAD).json()

    assert client.get(APPS, headers=bob).json() == []
    assert client.get(f"{APPS}/{app_['id']}", headers=bob).status_code == 404
    assert client.patch(
        f"{APPS}/{app_['id']}", headers=bob, json={"status": "offer"}
    ).status_code == 404
    assert client.delete(f"{APPS}/{app_['id']}", headers=bob).status_code == 404


def test_cannot_track_another_users_job(client, make_user, job_payload):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    job = client.post(JOBS, headers=alice, json=job_payload).json()
    r = client.post(APPS, headers=bob, json={"job_id": job["id"]})
    assert r.status_code == 404


def test_cannot_attach_another_users_tailoring(
    client, make_user, job_payload, docx_bytes, fake_llm
):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    client.post(
        "/api/v1/resumes",
        headers=alice,
        files={"file": ("cv.docx", docx_bytes, "application/octet-stream")},
    )
    alice_job = client.post(JOBS, headers=alice, json=job_payload).json()
    alice_tailoring = client.post(
        "/api/v1/tailorings", headers=alice, json={"job_id": alice_job["id"]}
    ).json()

    bob_card = client.post(QUICK, headers=bob, json=QUICK_PAYLOAD).json()
    r = client.patch(
        f"{APPS}/{bob_card['id']}",
        headers=bob,
        json={"tailoring_id": alice_tailoring["id"]},
    )
    assert r.status_code == 404


def test_applications_require_authentication(client):
    assert client.get(APPS).status_code == 401
    assert client.post(QUICK, json=QUICK_PAYLOAD).status_code == 401


# ── Tailoring still needs a description ───────────────────────────────────────


def test_tailoring_a_job_with_no_description_is_422(
    client, auth_headers, docx_bytes, fake_llm
):
    client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        files={"file": ("cv.docx", docx_bytes, "application/octet-stream")},
    )
    card = client.post(QUICK, headers=auth_headers, json=QUICK_PAYLOAD).json()

    r = client.post(
        "/api/v1/tailorings", headers=auth_headers, json={"job_id": card["job"]["id"]}
    )
    assert r.status_code == 422
    assert "no description" in r.json()["detail"]
    # And no wasted model call.
    assert fake_llm.calls == []
