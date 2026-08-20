"""Sessions: signing out actually ends access, and idleness ends it too.

Before this existed, a token stayed valid for its full week no matter what the
user did — closing the tab, pressing sign out, or losing the laptop.
"""

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.models.session import Session
from app.models.user import User

ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"
SESSIONS = "/api/v1/me/sessions"


def _session_row(db, email: str) -> Session:
    user = db.scalar(select(User).where(User.email == email))
    rows = db.scalars(
        select(Session).where(Session.user_id == user.id).order_by(Session.created_at)
    ).all()
    assert rows, "signing in should have created a session"
    return rows[-1]


def _age(db, row: Session, *, minutes: int) -> None:
    """Backdate last activity, standing in for time passing."""
    row.last_used_at = datetime.now(UTC) - timedelta(minutes=minutes)
    db.commit()


# --- the token itself -------------------------------------------------------


def test_token_carries_a_session_id(client, make_user):
    headers = make_user("sid@example.com")
    token = headers["Authorization"].removeprefix("Bearer ")
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sid"], "the token must name the session it belongs to"


def test_token_without_a_session_id_is_refused(client, make_user, db_session):
    """The shape every token had before this feature. Refused, not trusted —
    otherwise the old tokens would be a way around the whole mechanism."""
    make_user("old@example.com")
    user = db_session.scalar(select(User).where(User.email == "old@example.com"))

    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(minutes=60),
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    r = client.get(ME, headers={"Authorization": f"Bearer {legacy}"})
    assert r.status_code == 401


def test_token_whose_subject_and_session_disagree_is_refused(
    client, make_user, db_session
):
    """A valid session id belonging to a different user than the token's subject."""
    victim = make_user("victim@example.com")
    make_user("attacker@example.com")

    victim_session = _session_row(db_session, "victim@example.com")
    attacker = db_session.scalar(
        select(User).where(User.email == "attacker@example.com")
    )

    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "sub": str(attacker.id),
            "sid": str(victim_session.id),
            "iat": now,
            "exp": now + timedelta(minutes=60),
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    r = client.get(ME, headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401
    # The real token still works, so the forgery did not disturb the session.
    assert client.get(ME, headers=victim).status_code == 200


# --- signing out -----------------------------------------------------------


def test_logout_makes_the_same_token_stop_working(client, make_user):
    headers = make_user("bye@example.com")
    assert client.get(ME, headers=headers).status_code == 200

    assert client.post(LOGOUT, headers=headers).status_code == 204

    r = client.get(ME, headers=headers)
    assert r.status_code == 401, "the token must be dead, not merely forgotten"


def test_logout_does_not_touch_other_devices(client, make_user, sign_in):
    first = make_user("two@example.com")
    second = sign_in("two@example.com")

    client.post(LOGOUT, headers=first)

    assert client.get(ME, headers=first).status_code == 401
    assert client.get(ME, headers=second).status_code == 200


def test_logout_twice_is_not_an_error_for_the_first_call(client, make_user):
    headers = make_user("idem@example.com")
    assert client.post(LOGOUT, headers=headers).status_code == 204
    # The second attempt has no session left to authenticate with.
    assert client.post(LOGOUT, headers=headers).status_code == 401


# --- expiry ----------------------------------------------------------------


def test_idle_for_too_long_signs_the_user_out(client, make_user, db_session):
    headers = make_user("idle@example.com")
    row = _session_row(db_session, "idle@example.com")

    _age(db_session, row, minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES + 1)

    assert client.get(ME, headers=headers).status_code == 401


def test_idle_session_is_revoked_not_merely_refused(client, make_user, db_session):
    """Otherwise a clock change, or a longer timeout later, would bring a
    long-abandoned session back to life."""
    headers = make_user("dead@example.com")
    row = _session_row(db_session, "dead@example.com")
    _age(db_session, row, minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES + 1)

    client.get(ME, headers=headers)

    db_session.refresh(row)
    assert row.revoked_at is not None


def test_activity_inside_the_window_keeps_the_session_alive(
    client, make_user, db_session
):
    headers = make_user("active@example.com")
    row = _session_row(db_session, "active@example.com")

    # Idle for most of the window, but not past it.
    _age(db_session, row, minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES - 5)
    assert client.get(ME, headers=headers).status_code == 200

    # That request should have reset the clock, so the same gap again is fine.
    db_session.refresh(row)
    _age(db_session, row, minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES - 5)
    assert client.get(ME, headers=headers).status_code == 200


def test_absolute_expiry_applies_however_active_the_user_is(
    client, make_user, db_session
):
    headers = make_user("old-session@example.com")
    row = _session_row(db_session, "old-session@example.com")

    # Active right now, but past the ceiling set at sign-in.
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    row.last_used_at = datetime.now(UTC)
    db_session.commit()

    assert client.get(ME, headers=headers).status_code == 401


# --- the device list -------------------------------------------------------


def test_sessions_list_shows_this_device_and_labels_it(client, make_user):
    headers = make_user("list@example.com")

    r = client.get(SESSIONS, headers=headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["is_current"] is True
    assert rows[0]["device"]
    # The raw user agent is never handed back.
    assert "Mozilla" not in str(rows[0])


def test_second_sign_in_appears_as_a_second_device(client, make_user, sign_in):
    make_user("multi@example.com")
    second = sign_in("multi@example.com")

    rows = client.get(SESSIONS, headers=second).json()
    assert len(rows) == 2
    assert [r["is_current"] for r in rows].count(True) == 1


def test_revoking_all_others_leaves_this_device_signed_in(
    client, make_user, sign_in
):
    first = make_user("sweep@example.com")
    second = sign_in("sweep@example.com")
    third = sign_in("sweep@example.com")

    r = client.delete(SESSIONS, headers=third)
    assert r.status_code == 200
    assert r.json()["revoked"] == 2

    assert client.get(ME, headers=third).status_code == 200
    assert client.get(ME, headers=first).status_code == 401
    assert client.get(ME, headers=second).status_code == 401


def test_revoking_one_session_by_id(client, make_user, sign_in):
    first = make_user("one@example.com")
    second = sign_in("one@example.com")

    target = next(
        row for row in client.get(SESSIONS, headers=second).json()
        if not row["is_current"]
    )

    assert client.delete(f"{SESSIONS}/{target['id']}", headers=second).status_code == 204
    assert client.get(ME, headers=first).status_code == 401
    assert client.get(ME, headers=second).status_code == 200


def test_a_revoked_session_disappears_from_the_list(client, make_user, sign_in):
    make_user("gone@example.com")
    second = sign_in("gone@example.com")

    client.delete(SESSIONS, headers=second)
    rows = client.get(SESSIONS, headers=second).json()
    assert len(rows) == 1


def test_an_idle_session_is_not_listed_as_active(
    client, make_user, sign_in, db_session
):
    make_user("stale@example.com")
    second = sign_in("stale@example.com")

    first_row = db_session.scalars(
        select(Session).order_by(Session.created_at)
    ).first()
    _age(db_session, first_row, minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES + 1)

    rows = client.get(SESSIONS, headers=second).json()
    assert len(rows) == 1
    assert rows[0]["is_current"] is True


# --- tenancy ---------------------------------------------------------------


def test_a_user_cannot_see_another_users_sessions(client, make_user):
    make_user("alice@example.com")
    bob = make_user("bob@example.com")

    rows = client.get(SESSIONS, headers=bob).json()
    assert len(rows) == 1
    assert rows[0]["is_current"] is True


def test_a_user_cannot_revoke_another_users_session(client, make_user, db_session):
    alice = make_user("a2@example.com")
    bob = make_user("b2@example.com")

    alice_session = _session_row(db_session, "a2@example.com")

    r = client.delete(f"{SESSIONS}/{alice_session.id}", headers=bob)
    assert r.status_code == 404, "404, not 403 — do not confirm the id exists"

    # Alice is still signed in.
    assert client.get(ME, headers=alice).status_code == 200


def test_revoke_all_only_affects_the_calling_user(client, make_user, sign_in):
    alice = make_user("a3@example.com")
    bob = make_user("b3@example.com")
    sign_in("b3@example.com")

    client.delete(SESSIONS, headers=bob)

    assert client.get(ME, headers=alice).status_code == 200


def test_unknown_session_id_is_a_404(client, make_user):
    headers = make_user("nf@example.com")
    r = client.delete(
        f"{SESSIONS}/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert r.status_code == 404


# --- account deletion ------------------------------------------------------


def test_deleting_the_account_removes_its_sessions(client, make_user, db_session):
    headers = make_user("del@example.com")
    r = client.request(
        "DELETE",
        "/api/v1/me",
        headers=headers,
        json={"confirm_email": "del@example.com"},
    )
    assert r.status_code == 204
    assert db_session.scalars(select(Session)).all() == []
