import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.application import Application

RUN = "/api/v1/internal/reminders/run"
QUICK = "/api/v1/applications/quick"

SECRET = "test-cron-secret"


@pytest.fixture
def cron(monkeypatch):
    """Enable the endpoint and return the header that authenticates it."""
    from app.core import config

    monkeypatch.setattr(config.settings, "CRON_SECRET", SECRET)
    return {"X-Cron-Secret": SECRET}


def _card(client, headers, **extra):
    payload = {"title": "Backend Engineer", "company": "Northwind", **extra}
    r = client.post(QUICK, headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _age(db_session, card_id, days):
    row = db_session.scalar(
        select(Application).where(Application.id == uuid.UUID(card_id))
    )
    row.updated_at = datetime.now(UTC) - timedelta(days=days)
    db_session.commit()
    return row


# ── Authentication ───────────────────────────────────────────────────────────


def test_a_missing_secret_is_refused(client, cron):
    assert client.post(RUN).status_code == 401


def test_a_wrong_secret_is_refused(client, cron, mailbox):
    r = client.post(RUN, headers={"X-Cron-Secret": "not-the-secret"})
    assert r.status_code == 401
    assert mailbox.sent == []


def test_an_unset_secret_disables_the_endpoint(client, monkeypatch):
    """A blank secret matching a blank header would leave this wide open."""
    from app.core import config

    monkeypatch.setattr(config.settings, "CRON_SECRET", "")
    assert client.post(RUN, headers={"X-Cron-Secret": ""}).status_code == 503


# ── What earns an email ──────────────────────────────────────────────────────


def test_a_deadline_closing_soon_is_reminded(client, auth_headers, cron, mailbox):
    soon = (date.today() + timedelta(days=2)).isoformat()
    _card(client, auth_headers, apply_by=soon)

    r = client.post(RUN, headers=cron)
    assert r.status_code == 200
    assert r.json()["emails_sent"] == 1
    assert "closing soon" in mailbox.sent[-1]["subject"]


def test_a_distant_deadline_is_left_alone(client, auth_headers, cron, mailbox):
    far = (date.today() + timedelta(days=30)).isoformat()
    _card(client, auth_headers, apply_by=far)

    # Signing the user up already sent a login code, so count the delta rather
    # than expecting an empty mailbox.
    before = len(mailbox.sent)
    assert client.post(RUN, headers=cron).json()["emails_sent"] == 0
    assert len(mailbox.sent) == before


def test_a_deadline_already_applied_to_is_left_alone(
    client, auth_headers, cron, mailbox
):
    """Nothing to chase once it is submitted."""
    soon = (date.today() + timedelta(days=2)).isoformat()
    _card(client, auth_headers, apply_by=soon, status="applied")

    assert client.post(RUN, headers=cron).json()["emails_sent"] == 0


def test_a_quiet_application_is_reminded(client, auth_headers, cron, mailbox, db_session):
    card = _card(client, auth_headers, status="applied")
    _age(db_session, card["id"], 30)

    r = client.post(RUN, headers=cron)
    assert r.json()["emails_sent"] == 1
    assert "waiting on a reply" in mailbox.sent[-1]["subject"]


def test_a_recent_application_is_left_alone(client, auth_headers, cron, mailbox):
    _card(client, auth_headers, status="applied")
    assert client.post(RUN, headers=cron).json()["emails_sent"] == 0


@pytest.mark.parametrize("resolved", ["interviewing", "offer", "rejected"])
def test_resolved_states_are_never_chased(
    client, auth_headers, cron, mailbox, db_session, resolved
):
    """Silence means nothing once the outcome is known."""
    card = _card(client, auth_headers, status=resolved)
    _age(db_session, card["id"], 90)

    assert client.post(RUN, headers=cron).json()["emails_sent"] == 0


# ── One email per person ─────────────────────────────────────────────────────


def test_several_cards_become_one_digest(
    client, auth_headers, cron, mailbox, db_session
):
    soon = (date.today() + timedelta(days=1)).isoformat()
    _card(client, auth_headers, title="Closing A", apply_by=soon)
    _card(client, auth_headers, title="Closing B", apply_by=soon)
    quiet = _card(client, auth_headers, title="Quiet one", status="applied")
    _age(db_session, quiet["id"], 30)

    r = client.post(RUN, headers=cron)
    # Three nudges must not mean three emails.
    assert r.json()["emails_sent"] == 1
    assert r.json()["applications"] == 3

    body = mailbox.sent[-1]["text"]
    for title in ("Closing A", "Closing B", "Quiet one"):
        assert title in body


def test_each_user_gets_their_own(client, make_user, cron, mailbox, db_session):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    soon = (date.today() + timedelta(days=1)).isoformat()

    _card(client, alice, apply_by=soon)
    _card(client, bob, apply_by=soon)

    assert client.post(RUN, headers=cron).json()["emails_sent"] == 2
    recipients = {m["to"] for m in mailbox.sent[-2:]}
    assert recipients == {"alice@example.com", "bob@example.com"}


# ── Not nagging ──────────────────────────────────────────────────────────────


def test_the_same_card_is_not_reminded_twice_in_a_row(
    client, auth_headers, cron, mailbox
):
    soon = (date.today() + timedelta(days=2)).isoformat()
    _card(client, auth_headers, apply_by=soon)

    assert client.post(RUN, headers=cron).json()["emails_sent"] == 1
    # A daily job must not email about the same card every morning.
    assert client.post(RUN, headers=cron).json()["emails_sent"] == 0


def test_it_comes_round_again_after_the_cooldown(
    client, auth_headers, cron, mailbox, db_session, monkeypatch
):
    from app.core import config

    monkeypatch.setattr(config.settings, "REMINDER_COOLDOWN_DAYS", 7)
    soon = (date.today() + timedelta(days=2)).isoformat()
    card = _card(client, auth_headers, apply_by=soon)

    assert client.post(RUN, headers=cron).json()["emails_sent"] == 1

    row = db_session.scalar(
        select(Application).where(Application.id == uuid.UUID(card["id"]))
    )
    row.reminded_at = datetime.now(UTC) - timedelta(days=10)
    db_session.commit()

    assert client.post(RUN, headers=cron).json()["emails_sent"] == 1


def test_a_failed_send_is_not_stamped(client, auth_headers, cron, db_session):
    """Otherwise a card whose email failed goes quiet for a whole week."""
    from app.api.deps import get_mailer
    from app.main import app
    from app.services.email import EmailError

    class BrokenMailer:
        def send(self, **_):
            raise EmailError("smtp exploded")

    soon = (date.today() + timedelta(days=2)).isoformat()
    card = _card(client, auth_headers, apply_by=soon)

    app.dependency_overrides[get_mailer] = lambda: BrokenMailer()
    try:
        r = client.post(RUN, headers=cron)
    finally:
        app.dependency_overrides.pop(get_mailer, None)

    assert r.json() == {"emails_sent": 0, "emails_failed": 1, "applications": 0}

    db_session.expire_all()
    row = db_session.scalar(
        select(Application).where(Application.id == uuid.UUID(card["id"]))
    )
    assert row.reminded_at is None


def test_nothing_due_sends_nothing(client, auth_headers, cron, mailbox):
    _card(client, auth_headers)
    assert client.post(RUN, headers=cron).json() == {
        "emails_sent": 0,
        "emails_failed": 0,
        "applications": 0,
    }
