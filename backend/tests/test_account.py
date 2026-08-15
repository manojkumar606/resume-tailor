import csv
import io
from datetime import date, timedelta

from sqlalchemy import select

from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.models.tailoring import Tailoring
from app.models.user import User
from app.models.verification import EmailCode
from app.services.unsubscribe import make_token

ME = "/api/v1/me"
EXPORT = "/api/v1/me/export"
UNSUB = "/api/v1/auth/unsubscribe"
QUICK = "/api/v1/applications/quick"
RUN = "/api/v1/internal/reminders/run"


def _card(client, headers, **extra):
    payload = {"title": "Backend Engineer", "company": "Northwind", **extra}
    return client.post(QUICK, headers=headers, json=payload).json()


# ── The toggle ───────────────────────────────────────────────────────────────


def test_reminders_are_on_by_default(client, auth_headers):
    """Opt-out, not opt-in — a retention feature nobody finds does nothing."""
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.json()["reminders_enabled"] is True


def test_the_toggle_can_be_turned_off_and_back_on(client, auth_headers):
    off = client.patch(ME, headers=auth_headers, json={"reminders_enabled": False})
    assert off.status_code == 200
    assert off.json()["reminders_enabled"] is False

    on = client.patch(ME, headers=auth_headers, json={"reminders_enabled": True})
    assert on.json()["reminders_enabled"] is True


def test_opting_out_silences_the_digest(client, auth_headers, cron, mailbox):
    soon = (date.today() + timedelta(days=2)).isoformat()
    _card(client, auth_headers, apply_by=soon)
    client.patch(ME, headers=auth_headers, json={"reminders_enabled": False})

    assert client.post(RUN, headers=cron).json()["emails_sent"] == 0


def test_opting_out_does_not_silence_login_codes(client, auth_headers, mailbox):
    """The whole point of scoping the flag: reminders are optional, codes are
    how anyone gets in at all."""
    client.patch(ME, headers=auth_headers, json={"reminders_enabled": False})

    before = len(mailbox.sent)
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "a-good-password"},
    )
    assert r.status_code == 202
    assert len(mailbox.sent) == before + 1


def test_updating_the_name_leaves_the_toggle_alone(client, auth_headers):
    r = client.patch(ME, headers=auth_headers, json={"full_name": "Manoj Kumar"})
    assert r.json()["full_name"] == "Manoj Kumar"
    assert r.json()["reminders_enabled"] is True


def test_settings_require_authentication(client):
    assert client.patch(ME, json={"reminders_enabled": False}).status_code == 401


# ── Unsubscribe from the email ───────────────────────────────────────────────


def test_the_digest_carries_an_unsubscribe_link(client, auth_headers, cron, mailbox):
    soon = (date.today() + timedelta(days=2)).isoformat()
    _card(client, auth_headers, apply_by=soon)
    client.post(RUN, headers=cron)

    body = mailbox.sent[-1]["text"]
    # Without an easy way out, the alternative is a spam complaint — which harms
    # delivery of the login codes too.
    assert "/unsubscribe?token=" in body


def test_the_link_works_with_no_session(client, auth_headers, db_session):
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    r = client.post(UNSUB, json={"token": make_token(user.id)})
    assert r.status_code == 200
    assert "Sign-in codes are unaffected" in r.json()["detail"]

    db_session.expire_all()
    assert (
        db_session.scalar(select(User).where(User.id == user.id)).reminders_enabled
        is False
    )


def test_a_tampered_token_is_rejected(client, auth_headers, db_session):
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    token = make_token(user.id)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    assert client.post(UNSUB, json={"token": tampered}).status_code == 400
    db_session.expire_all()
    assert (
        db_session.scalar(select(User).where(User.id == user.id)).reminders_enabled
        is True
    )


def test_a_token_for_an_unknown_user_looks_the_same(client):
    """Same response either way, so this cannot be used to probe which ids
    exist."""
    import uuid

    r = client.post(UNSUB, json={"token": make_token(uuid.uuid4())})
    assert r.status_code == 200


def test_garbage_tokens_are_rejected(client):
    for bad in ["", "nonsense", "not-a-uuid.abcdef", "."]:
        r = client.post(UNSUB, json={"token": bad})
        assert r.status_code in (400, 422), bad


# ── Export ───────────────────────────────────────────────────────────────────


def test_export_returns_a_csv_of_applications(client, auth_headers):
    _card(client, auth_headers, title="Role A", status="applied")
    _card(client, auth_headers, title="Role B", company="Acme")

    r = client.get(EXPORT, headers=auth_headers)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert {row["job_title"] for row in rows} == {"Role A", "Role B"}
    assert {row["status"] for row in rows} == {"applied", "saved"}


def test_export_is_empty_but_valid_with_no_applications(client, auth_headers):
    r = client.get(EXPORT, headers=auth_headers)
    assert r.status_code == 200
    reader = csv.DictReader(io.StringIO(r.text))
    assert list(reader) == []
    # Headers still present, so the file opens cleanly in a spreadsheet.
    assert "job_title" in (reader.fieldnames or [])


def test_export_never_leaks_another_users_rows(client, make_user):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    _card(client, alice, title="Alice only")

    rows = list(csv.DictReader(io.StringIO(client.get(EXPORT, headers=bob).text)))
    assert rows == []


# ── Account deletion ─────────────────────────────────────────────────────────


def test_deleting_removes_everything_belonging_to_the_user(
    client, auth_headers, docx_bytes, job_payload, fake_llm, db_session
):
    client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        files={"file": ("cv.docx", docx_bytes, "application/octet-stream")},
    )
    job = client.post("/api/v1/jobs", headers=auth_headers, json=job_payload).json()
    client.post("/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]})
    client.post("/api/v1/applications", headers=auth_headers, json={"job_id": job["id"]})

    r = client.request(
        "DELETE", ME, headers=auth_headers, json={"confirm_email": "user@example.com"}
    )
    assert r.status_code == 204, r.text

    db_session.expire_all()
    for model in (User, Application, Tailoring, Resume, Job, EmailCode):
        assert db_session.scalars(select(model)).all() == [], model.__name__


def test_deletion_requires_the_email_to_match(client, auth_headers, db_session):
    r = client.request(
        "DELETE", ME, headers=auth_headers, json={"confirm_email": "wrong@example.com"}
    )
    assert r.status_code == 400
    # An irreversible action needs more friction than one click.
    assert db_session.scalars(select(User)).all() != []


def test_deletion_is_case_insensitive_on_the_email(client, auth_headers, db_session):
    r = client.request(
        "DELETE", ME, headers=auth_headers, json={"confirm_email": "USER@Example.com"}
    )
    assert r.status_code == 204


def test_deleting_one_account_leaves_the_other_intact(
    client, make_user, job_payload, db_session
):
    alice = make_user("alice@example.com")
    make_user("bob@example.com")
    client.post("/api/v1/jobs", headers=alice, json=job_payload)

    client.request(
        "DELETE", ME, headers=alice, json={"confirm_email": "alice@example.com"}
    )

    db_session.expire_all()
    remaining = db_session.scalars(select(User)).all()
    assert [u.email for u in remaining] == ["bob@example.com"]


def test_deletion_requires_authentication(client):
    r = client.request("DELETE", ME, json={"confirm_email": "user@example.com"})
    assert r.status_code == 401
