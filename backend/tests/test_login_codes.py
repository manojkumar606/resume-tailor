from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.deps import get_mailer
from app.main import app
from app.models.user import User
from app.models.verification import CodePurpose, EmailCode
from app.services.email import EmailError

SIGNUP = "/api/v1/auth/signup"
LOGIN = "/api/v1/auth/login"
VERIFY = "/api/v1/auth/verify-code"
RESEND = "/api/v1/auth/resend-code"

EMAIL = "new@example.com"
PASSWORD = "a-good-password"


def _signup(client, email=EMAIL, password=PASSWORD):
    return client.post(SIGNUP, json={"email": email, "password": password})


def _submit(client, code, email=EMAIL):
    return client.post(VERIFY, json={"email": email, "code": code})


# ── Storage ──────────────────────────────────────────────────────────────────


def test_code_is_not_stored_in_recoverable_form(client, mailbox, db_session):
    _signup(client)
    code = mailbox.last_code_for(EMAIL)

    rows = db_session.scalars(select(EmailCode)).all()
    assert len(rows) == 1
    assert code not in rows[0].code_hash
    assert len(rows[0].code_hash) == 64
    # HMAC, not a bare hash: six digits would otherwise fall to an offline sweep
    # the moment the table leaked.
    import hashlib

    assert rows[0].code_hash != hashlib.sha256(code.encode()).hexdigest()


def test_signup_records_the_purpose(client, mailbox, db_session):
    _signup(client)
    assert db_session.scalars(select(EmailCode)).one().purpose is CodePurpose.SIGNUP


def test_login_records_the_purpose_and_leaves_one_live_code(
    client, make_user, db_session
):
    """Asserted via "the only unused code" rather than "the newest row".

    created_at cannot break the tie: SQLite's CURRENT_TIMESTAMP has one-second
    resolution, so rows written in the same test share a timestamp. It does not
    matter to the code under test, because issuing a code retires any
    outstanding one — so exactly one is ever live.
    """
    make_user(EMAIL)
    client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})

    live = db_session.scalars(
        select(EmailCode).where(EmailCode.used_at.is_(None))
    ).all()
    assert len(live) == 1
    assert live[0].purpose is CodePurpose.LOGIN


# ── Every login needs a code ──────────────────────────────────────────────────


def test_a_second_login_needs_a_fresh_code(client, make_user, mailbox, sign_in):
    make_user(EMAIL)
    sign_in(EMAIL)

    first_code = mailbox.last_code_for(EMAIL)
    client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    second_code = mailbox.last_code_for(EMAIL)

    assert second_code != first_code
    # The previous code must not still open the door.
    assert _submit(client, first_code).status_code == 400
    assert _submit(client, second_code).status_code == 200


def test_issuing_a_code_retires_the_previous_one(client, mailbox, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "EMAIL_RESEND_COOLDOWN_SECONDS", 0)

    _signup(client)
    first = mailbox.last_code_for(EMAIL)

    assert client.post(RESEND, json={"email": EMAIL}).status_code == 202
    second = mailbox.last_code_for(EMAIL)
    assert second != first

    assert _submit(client, first).status_code == 400
    assert _submit(client, second).status_code == 200


# ── Rejection paths ───────────────────────────────────────────────────────────


def test_wrong_code_is_rejected(client, mailbox):
    _signup(client)
    real = mailbox.last_code_for(EMAIL)
    wrong = "000000" if real != "000000" else "111111"
    assert _submit(client, wrong).status_code == 400


def test_code_is_single_use(client, mailbox):
    _signup(client)
    code = mailbox.last_code_for(EMAIL)
    assert _submit(client, code).status_code == 200
    assert _submit(client, code).status_code == 400


def test_expired_code_is_rejected(client, mailbox, db_session):
    _signup(client)
    code = mailbox.last_code_for(EMAIL)

    row = db_session.scalars(select(EmailCode)).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    assert _submit(client, code).status_code == 400


def test_code_is_retired_after_too_many_wrong_attempts(
    client, mailbox, db_session, monkeypatch
):
    from app.core import config

    monkeypatch.setattr(config.settings, "LOGIN_CODE_MAX_ATTEMPTS", 3)

    _signup(client)
    real = mailbox.last_code_for(EMAIL)
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(3):
        assert _submit(client, wrong).status_code == 400

    # Six digits is guessable, so the code must stop being a live target rather
    # than surviving until its expiry.
    assert _submit(client, real).status_code == 400
    db_session.expire_all()
    assert db_session.scalars(select(EmailCode)).one().used_at is not None


def test_unknown_email_and_wrong_code_look_identical(client, mailbox):
    _signup(client)
    real = mailbox.last_code_for(EMAIL)
    wrong = "000000" if real != "000000" else "111111"

    unknown = client.post(VERIFY, json={"email": "nobody@example.com", "code": "123456"})
    bad_code = _submit(client, wrong)

    assert unknown.status_code == bad_code.status_code == 400
    # Probing must not reveal whether an address is registered.
    assert unknown.json()["detail"] == bad_code.json()["detail"]


@pytest.mark.parametrize("bad", ["12345", "1234567", "abcdef", "12 34 5"])
def test_malformed_codes_are_rejected_before_lookup(client, bad):
    assert client.post(VERIFY, json={"email": EMAIL, "code": bad}).status_code == 422


def test_code_with_spaces_or_dashes_is_accepted(client, mailbox):
    """People paste codes straight out of the email, punctuation included."""
    _signup(client)
    code = mailbox.last_code_for(EMAIL)
    spaced = f"{code[:3]} {code[3:]}"
    assert _submit(client, spaced).status_code == 200


# ── Delivery failure ─────────────────────────────────────────────────────────


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
    # A code nobody received would start the resend cooldown and block the retry.
    assert db_session.scalar(select(User).where(User.email == EMAIL)) is None
    assert db_session.scalars(select(EmailCode)).all() == []


def test_misconfigured_provider_gives_503_not_a_bare_500(client, monkeypatch):
    from app.core import config
    from app.services import email as email_module

    monkeypatch.setattr(config.settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(config.settings, "BREVO_API_KEY", "")
    email_module.get_email_provider.cache_clear()
    app.dependency_overrides.pop(get_mailer, None)
    try:
        r = _signup(client)
    finally:
        email_module.get_email_provider.cache_clear()

    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]
    assert "BREVO_API_KEY" not in r.json()["detail"]


# ── Resend ───────────────────────────────────────────────────────────────────


def test_resend_is_rate_limited(client, mailbox):
    _signup(client)
    r = client.post(RESEND, json={"email": EMAIL})
    assert r.status_code == 429, "the signup email itself starts the cooldown"
    assert r.headers.get("Retry-After")
    assert len(mailbox.sent) == 1


def test_resend_for_an_unknown_address_says_the_same_thing(client, mailbox):
    known = _signup(client) and client.post(RESEND, json={"email": "nobody@example.com"})
    assert known.status_code == 202
    # Identical response regardless of existence, so this cannot enumerate users.
    assert "if that address has an account" in known.json()["detail"].lower()
    # ...and nothing was actually sent to a stranger.
    assert all(m["to"] != "nobody@example.com" for m in mailbox.sent)


# ── The verification gate (defence in depth) ──────────────────────────────────


def test_gate_still_blocks_a_token_whose_account_was_unverified(
    client, make_user, unverify
):
    """Unreachable through the API now, since a token requires a code — kept as
    defence in depth, so it is tested by building the state directly."""
    headers = make_user(EMAIL)
    assert client.get("/api/v1/resumes", headers=headers).status_code == 200

    unverify(EMAIL)
    r = client.get("/api/v1/resumes", headers=headers)
    assert r.status_code == 403
    assert "confirm your email" in r.json()["detail"].lower()
