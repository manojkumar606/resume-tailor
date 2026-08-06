def test_signup_returns_token_and_user(client, user_payload):
    r = client.post("/api/v1/auth/signup", json=user_payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    # Email is normalised to lowercase on the way in.
    assert body["user"]["email"] == "alice@example.com"
    assert "hashed_password" not in body["user"]


def test_signup_rejects_duplicate_email_case_insensitively(client, user_payload):
    assert client.post("/api/v1/auth/signup", json=user_payload).status_code == 201
    dupe = {**user_payload, "email": "ALICE@example.com"}
    r = client.post("/api/v1/auth/signup", json=dupe)
    assert r.status_code == 409


def test_login_succeeds_and_me_returns_that_user(client, user_payload):
    client.post("/api/v1/auth/signup", json=user_payload)

    r = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": user_payload["password"]},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_login_with_wrong_password_is_401(client, user_payload):
    client.post("/api/v1/auth/signup", json=user_payload)
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert r.status_code == 401


def test_login_for_unknown_email_gives_same_error_as_wrong_password(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever-123"},
    )
    assert r.status_code == 401
    # Must not reveal whether the account exists.
    assert r.json()["detail"] == "Incorrect email or password"


def test_me_requires_a_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_a_garbage_token(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_short_password_is_rejected(client, user_payload):
    r = client.post(
        "/api/v1/auth/signup", json={**user_payload, "password": "short"}
    )
    assert r.status_code == 422
