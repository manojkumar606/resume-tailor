SIGNUP = "/api/v1/auth/signup"
LOGIN = "/api/v1/auth/login"
VERIFY = "/api/v1/auth/verify-code"
ME = "/api/v1/auth/me"


def test_signup_issues_no_token_only_a_code(client, user_payload, mailbox):
    r = client.post(SIGNUP, json=user_payload)
    assert r.status_code == 202, r.text
    body = r.json()

    # The whole point: a password alone never yields a session.
    assert "access_token" not in body
    assert body["status"] == "code_sent"
    assert body["email"] == "alice@example.com"  # normalised
    assert body["expires_in_minutes"] > 0

    assert len(mailbox.sent) == 1
    assert mailbox.last_code_for("alice@example.com").isdigit()


def test_signup_then_code_gives_a_session(client, user_payload, mailbox):
    client.post(SIGNUP, json=user_payload)
    r = client.post(
        VERIFY,
        json={
            "email": user_payload["email"],
            "code": mailbox.last_code_for("alice@example.com"),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["is_verified"] is True
    assert "hashed_password" not in r.json()["user"]

    token = r.json()["access_token"]
    me = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_signup_rejects_duplicate_email_case_insensitively(client, user_payload):
    assert client.post(SIGNUP, json=user_payload).status_code == 202
    dupe = {**user_payload, "email": "ALICE@example.com"}
    assert client.post(SIGNUP, json=dupe).status_code == 409


def test_login_issues_no_token_only_a_code(client, make_user, mailbox):
    make_user("bob@example.com")
    before = len(mailbox.sent)

    r = client.post(LOGIN, json={"email": "bob@example.com", "password": "a-good-password"})
    assert r.status_code == 202, r.text
    assert "access_token" not in r.json()
    # A second email went out for the login step.
    assert len(mailbox.sent) == before + 1


def test_login_with_wrong_password_is_401_and_sends_nothing(client, make_user, mailbox):
    make_user("bob@example.com")
    before = len(mailbox.sent)

    r = client.post(LOGIN, json={"email": "bob@example.com", "password": "wrong-password"})
    assert r.status_code == 401
    # No code for a failed password, or the endpoint becomes a way to spam an
    # inbox using only somebody's address.
    assert len(mailbox.sent) == before


def test_login_for_unknown_email_gives_same_error_as_wrong_password(client):
    r = client.post(LOGIN, json={"email": "nobody@example.com", "password": "whatever-123"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"


def test_full_sign_in_round_trip(client, make_user, sign_in):
    make_user("bob@example.com")
    headers = sign_in("bob@example.com")
    assert client.get(ME, headers=headers).status_code == 200


def test_me_requires_a_token(client):
    assert client.get(ME).status_code == 401


def test_me_rejects_a_garbage_token(client):
    r = client.get(ME, headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_short_password_is_rejected(client, user_payload):
    r = client.post(SIGNUP, json={**user_payload, "password": "short"})
    assert r.status_code == 422
