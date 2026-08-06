def test_create_and_fetch_job(client, auth_headers, job_payload):
    r = client.post("/api/v1/jobs", headers=auth_headers, json=job_payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == job_payload["title"]
    assert body["source"] == "manual"

    got = client.get(f"/api/v1/jobs/{body['id']}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["description"] == job_payload["description"]


def test_list_omits_description(client, auth_headers, job_payload):
    client.post("/api/v1/jobs", headers=auth_headers, json=job_payload)
    r = client.get("/api/v1/jobs", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert "description" not in r.json()[0]


def test_too_short_description_is_rejected(client, auth_headers, job_payload):
    r = client.post(
        "/api/v1/jobs", headers=auth_headers, json={**job_payload, "description": "hi"}
    )
    assert r.status_code == 422


def test_patch_updates_only_supplied_fields(client, auth_headers, job_payload):
    job = client.post("/api/v1/jobs", headers=auth_headers, json=job_payload).json()

    r = client.patch(
        f"/api/v1/jobs/{job['id']}", headers=auth_headers, json={"location": "Hyderabad"}
    )
    assert r.status_code == 200
    assert r.json()["location"] == "Hyderabad"
    # Untouched fields must survive a partial update.
    assert r.json()["title"] == job_payload["title"]


def test_delete_job(client, auth_headers, job_payload):
    job = client.post("/api/v1/jobs", headers=auth_headers, json=job_payload).json()
    assert client.delete(
        f"/api/v1/jobs/{job['id']}", headers=auth_headers
    ).status_code == 204
    assert client.get(
        f"/api/v1/jobs/{job['id']}", headers=auth_headers
    ).status_code == 404


def test_pagination(client, auth_headers, job_payload):
    for i in range(5):
        client.post(
            "/api/v1/jobs", headers=auth_headers, json={**job_payload, "title": f"Role {i}"}
        )
    page = client.get("/api/v1/jobs?limit=2&offset=0", headers=auth_headers).json()
    assert len(page) == 2


def test_jobs_are_not_visible_across_tenants(client, make_user, job_payload):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    job = client.post("/api/v1/jobs", headers=alice, json=job_payload).json()

    assert client.get("/api/v1/jobs", headers=bob).json() == []
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=bob).status_code == 404
    assert client.patch(
        f"/api/v1/jobs/{job['id']}", headers=bob, json={"title": "Hijacked"}
    ).status_code == 404
    assert client.delete(f"/api/v1/jobs/{job['id']}", headers=bob).status_code == 404


def test_jobs_require_authentication(client, job_payload):
    assert client.post("/api/v1/jobs", json=job_payload).status_code == 401
    assert client.get("/api/v1/jobs").status_code == 401
