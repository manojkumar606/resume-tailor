import pytest

from app.services.llm import LLMError
from app.services.tailoring import parse_result


def _setup(client, headers, docx_bytes, job_payload):
    """Upload a resume and create a job. Returns (resume, job)."""
    resume = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("resume.docx", docx_bytes, "application/octet-stream")},
    ).json()
    job = client.post("/api/v1/jobs", headers=headers, json=job_payload).json()
    return resume, job


def test_tailoring_succeeds_and_stores_the_analysis(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    _, job = _setup(client, auth_headers, docx_bytes, job_payload)

    r = client.post(
        "/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["match_score"] == 78
    assert body["missing_keywords"] == ["Snowflake administration"]
    assert body["changes"]
    assert "EXPERIENCE" in body["tailored_text"]
    assert body["model"] == "fake-model-1"
    assert body["completed_at"] is not None


def test_omitting_resume_id_uses_the_default_resume(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    resume, job = _setup(client, auth_headers, docx_bytes, job_payload)
    r = client.post(
        "/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]}
    )
    assert r.json()["resume_id"] == resume["id"]


def test_prompt_carries_the_job_and_resume_content(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    _, job = _setup(client, auth_headers, docx_bytes, job_payload)
    client.post("/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]})

    assert len(fake_llm.calls) == 1
    prompt = fake_llm.calls[0]["prompt"]
    assert job_payload["company"] in prompt
    assert "Snowflake" in prompt          # from the job description
    assert "reporting pipelines" in prompt  # from the resume
    # The anti-fabrication rule must actually reach the model.
    assert "NEVER invent experience" in fake_llm.calls[0]["system"]


def test_no_resume_at_all_is_400(client, auth_headers, job_payload, fake_llm):
    job = client.post("/api/v1/jobs", headers=auth_headers, json=job_payload).json()
    r = client.post(
        "/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]}
    )
    assert r.status_code == 400
    assert "default resume" in r.json()["detail"]


def test_unknown_job_is_404(client, auth_headers, docx_bytes, fake_llm):
    r = client.post(
        "/api/v1/tailorings",
        headers=auth_headers,
        json={"job_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


def test_llm_failure_is_502_and_the_attempt_is_recorded(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    _, job = _setup(client, auth_headers, docx_bytes, job_payload)
    fake_llm.error = LLMError("quota exceeded")

    r = client.post(
        "/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]}
    )
    assert r.status_code == 502
    assert "quota exceeded" in r.json()["detail"]

    # The failed run must still be visible, with the reason.
    listed = client.get("/api/v1/tailorings", headers=auth_headers).json()
    assert len(listed) == 1
    assert listed[0]["status"] == "failed"
    assert "quota exceeded" in listed[0]["error"]


def test_download_returns_a_docx(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    _, job = _setup(client, auth_headers, docx_bytes, job_payload)
    t = client.post(
        "/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]}
    ).json()

    r = client.get(f"/api/v1/tailorings/{t['id']}/download", headers=auth_headers)
    assert r.status_code == 200
    # A .docx is a zip archive — check the magic bytes rather than the header.
    assert r.content[:2] == b"PK"


def test_download_of_a_failed_tailoring_is_409(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    _, job = _setup(client, auth_headers, docx_bytes, job_payload)
    fake_llm.error = LLMError("boom")
    client.post("/api/v1/tailorings", headers=auth_headers, json={"job_id": job["id"]})

    failed = client.get("/api/v1/tailorings", headers=auth_headers).json()[0]
    r = client.get(f"/api/v1/tailorings/{failed['id']}/download", headers=auth_headers)
    assert r.status_code == 409


def test_filter_by_job_id(client, auth_headers, docx_bytes, job_payload, fake_llm):
    _, job_a = _setup(client, auth_headers, docx_bytes, job_payload)
    job_b = client.post(
        "/api/v1/jobs", headers=auth_headers, json={**job_payload, "title": "Other"}
    ).json()

    client.post("/api/v1/tailorings", headers=auth_headers, json={"job_id": job_a["id"]})
    client.post("/api/v1/tailorings", headers=auth_headers, json={"job_id": job_b["id"]})

    only_a = client.get(
        f"/api/v1/tailorings?job_id={job_a['id']}", headers=auth_headers
    ).json()
    assert len(only_a) == 1
    assert only_a[0]["job_id"] == job_a["id"]


def test_tailorings_are_not_visible_across_tenants(
    client, make_user, docx_bytes, job_payload, fake_llm
):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    _, job = _setup(client, alice, docx_bytes, job_payload)
    t = client.post("/api/v1/tailorings", headers=alice, json={"job_id": job["id"]}).json()

    assert client.get("/api/v1/tailorings", headers=bob).json() == []
    assert client.get(f"/api/v1/tailorings/{t['id']}", headers=bob).status_code == 404
    assert (
        client.get(f"/api/v1/tailorings/{t['id']}/download", headers=bob).status_code
        == 404
    )


def test_cannot_tailor_using_another_users_resume(
    client, make_user, docx_bytes, job_payload, fake_llm
):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    alice_resume, _ = _setup(client, alice, docx_bytes, job_payload)
    bob_job = client.post("/api/v1/jobs", headers=bob, json=job_payload).json()

    r = client.post(
        "/api/v1/tailorings",
        headers=bob,
        json={"job_id": bob_job["id"], "resume_id": alice_resume["id"]},
    )
    assert r.status_code == 404


# ── Unit tests for result parsing ────────────────────────────────────────────


def test_parse_result_requires_tailored_resume():
    with pytest.raises(LLMError):
        parse_result({"match_score": 90})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (150, 100.0),      # clamped
        (-20, 0.0),        # clamped
        ("85", 85.0),      # numeric string
        ("high", None),    # unusable
        (None, None),
        (True, None),      # bool is not a score
    ],
)
def test_match_score_is_clamped_or_dropped(raw, expected):
    result = parse_result({"tailored_resume": "text", "match_score": raw})
    assert result.match_score == expected


def test_non_list_keyword_fields_degrade_to_empty():
    result = parse_result(
        {"tailored_resume": "text", "missing_keywords": "not a list", "changes": None}
    )
    assert result.missing_keywords == []
    assert result.changes == []
