from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.main import app
from app.models.user import User
from app.models.verification import EmailVerificationToken
from app.api.deps import get_mailer
from app.services.email import EmailError

SIGNUP = "/api/v1/auth/signup"
VERIFY = "/api/v1/auth/verify"
RESEND = "/api/v1/auth/resend-verification"


def _signup(client, email="new@example.com", password="a-good-password"):
    return client.post(SIGNUP, json={"email": email, "password": password})


# ── Signup ───────────────────────────────────────────────────────────────────


def test_signup_creates_an_unverified_user_and_sends_one_email(client, mailbox):
    r = _signup(client)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["is_verified"] is False

    assert len(mailbox.sent) == 1
    message = mailbox.sent[0]
    assert message["to"] == "new@example.com"
    assert "/verify?token=" in message["text"]
    assert "/verify?token=" in message["html"]


def test_token_is_not_stored_in_plaintext(client, mailbox, db_session):
    _signup(client)
    token = mailbox.last_token_for("new@example.com")

    stored = db_session.scalars(select(EmailVerificationToken)).all()
    assert len(stored) == 1
    # A database leak must not hand out working verification links.
    assert stored[0].token_hash != token
    assert len(stored[0].token_hash) == 64


def test_misconfigured_provider_gives_503_not_a_bare_500(client, monkeypatch):
    """A missing API key is a server misconfiguration, not a crash.

    Regression test: this surfaced in production as "Internal Server Error",
    which said nothing about the cause and looked like the app had fallen over.
    """
    from app.core import config
    from app.services import email as email_module

    monkeypatch.setattr(config.settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(config.settings, "BREVO_API_KEY", "")
    email_module.get_email_provider.cache_clear()
    # Drop the fixture override so the real resolution path runs.
    app.dependency_overrides.pop(get_mailer, None)
    try:
        r = _signup(client)
    finally:
        email_module.get_email_provider.cache_clear()

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "not configured" in detail
    # The API key name must not leak to the caller.
    assert "BREVO_API_KEY" not in detail


def test_unknown_provider_name_is_also_503(client, monkeypatch):
    from app.core import config
    from app.services import email as email_module

    monkeypatch.setattr(config.settings, "EMAIL_PROVIDER", "carrier-pigeon")
    email_module.get_email_provider.cache_clear()
    app.dependency_overrides.pop(get_mailer, None)
    try:
        assert _signup(client).status_code == 503
    finally:
        email_module.get_email_provider.cache_clear()


def test_signup_is_rolled_back_when_the_email_cannot_be_sent(client, db_session):
    class BrokenMailer:
        def send(self, **_):
            raise EmailError("smtp exploded")

    app.dependency_overrides[get_mailer] = lambda: BrokenMailer()
    try:
        r = _signup(client)
    finally:
        app.dependency_overrides.pop(get_mailer, None)

    assert r.status_code == 502
    # Verification is mandatory, so a user whose email never arrived would be
    # permanently locked out. Nothing should have been persisted.
    assert db_session.scalar(select(User).where(User.email == "new@example.com")) is None
    assert db_session.scalars(select(EmailVerificationToken)).all() == []


# ── The gate ─────────────────────────────────────────────────────────────────


def test_unverified_user_is_blocked_from_the_app(client, make_unverified_user):
    headers = make_unverified_user()

    for method, path in [
        ("get", "/api/v1/resumes"),
        ("get", "/api/v1/jobs"),
        ("get", "/api/v1/tailorings"),
    ]:
        r = getattr(client, method)(path, headers=headers)
        assert r.status_code == 403, f"{path} returned {r.status_code}"
        assert "confirm your email" in r.json()["detail"].lower()


def test_unverified_user_can_still_reach_auth_routes(client, make_unverified_user):
    headers = make_unverified_user()
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["is_verified"] is False


def test_gate_returns_403_not_401(client, make_unverified_user):
    """401 would make the client treat the token as dead and sign the user out,
    losing the session they need in order to request a resend."""
    headers = make_unverified_user()
    assert client.get("/api/v1/jobs", headers=headers).status_code == 403


def test_verified_user_can_use_the_app(client, make_user):
    headers = make_user()
    assert client.get("/api/v1/resumes", headers=headers).status_code == 200


# ── Redeeming ────────────────────────────────────────────────────────────────


def test_verify_marks_the_user_and_returns_a_fresh_token(client, mailbox):
    _signup(client)
    r = client.post(VERIFY, json={"token": mailbox.last_token_for("new@example.com")})
    assert r.status_code == 200
    assert r.json()["user"]["is_verified"] is True
    assert r.json()["access_token"]


def test_verify_needs_no_authentication(client, mailbox):
    """The link is opened from an email client, which may be on another device."""
    _signup(client)
    token = mailbox.last_token_for("new@example.com")
    assert client.post(VERIFY, json={"token": token}).status_code == 200


def test_token_is_single_use(client, mailbox):
    _signup(client)
    token = mailbox.last_token_for("new@example.com")
    assert client.post(VERIFY, json={"token": token}).status_code == 200
    assert client.post(VERIFY, json={"token": token}).status_code == 400


def test_unknown_token_is_rejected(client):
    r = client.post(VERIFY, json={"token": "not-a-real-token"})
    assert r.status_code == 400
    assert "invalid or has expired" in r.json()["detail"]


def test_expired_token_is_rejected(client, mailbox, db_session):
    _signup(client)
    token = mailbox.last_token_for("new@example.com")

    row = db_session.scalars(select(EmailVerificationToken)).one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    assert client.post(VERIFY, json={"token": token}).status_code == 400


def test_unknown_and_expired_tokens_give_the_same_message(client, mailbox, db_session):
    _signup(client)
    token = mailbox.last_token_for("new@example.com")
    row = db_session.scalars(select(EmailVerificationToken)).one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    expired = client.post(VERIFY, json={"token": token}).json()["detail"]
    unknown = client.post(VERIFY, json={"token": "nope"}).json()["detail"]
    # Probing tokens should reveal nothing about why one failed.
    assert expired == unknown


def test_verifying_retires_other_outstanding_tokens(
    client, mailbox, db_session, monkeypatch
):
    from app.core import config

    monkeypatch.setattr(config.settings, "EMAIL_RESEND_COOLDOWN_SECONDS", 0)

    _signup(client)
    first = mailbox.last_token_for("new@example.com")
    headers = {"Authorization": f"Bearer {_login(client)}"}

    assert client.post(RESEND, headers=headers).status_code == 202
    second = mailbox.last_token_for("new@example.com")
    assert second != first

    assert client.post(VERIFY, json={"token": second}).status_code == 200
    # The earlier link was already emailed; it must stop working once verified.
    assert client.post(VERIFY, json={"token": first}).status_code == 400


def _login(client, email="new@example.com", password="a-good-password") -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ── Resend ───────────────────────────────────────────────────────────────────


def test_resend_is_rate_limited(client, mailbox):
    _signup(client)
    headers = {"Authorization": f"Bearer {_login(client)}"}

    r = client.post(RESEND, headers=headers)
    assert r.status_code == 429, "the signup email itself should start the cooldown"
    assert r.headers.get("Retry-After")
    # Nothing extra was sent.
    assert len(mailbox.sent) == 1


def test_resend_works_once_the_cooldown_passes(client, mailbox, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "EMAIL_RESEND_COOLDOWN_SECONDS", 0)
    _signup(client)
    headers = {"Authorization": f"Bearer {_login(client)}"}

    assert client.post(RESEND, headers=headers).status_code == 202
    assert len(mailbox.sent) == 2


def test_resend_for_an_already_verified_user_is_a_no_op(client, mailbox, make_user):
    headers = make_user("done@example.com")
    before = len(mailbox.sent)
    r = client.post(RESEND, headers=headers)
    assert r.status_code == 202
    assert "already confirmed" in r.json()["detail"]
    assert len(mailbox.sent) == before


def test_resend_requires_authentication(client):
    assert client.post(RESEND).status_code == 401
