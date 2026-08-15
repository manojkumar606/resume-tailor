TAILORINGS = "/api/v1/tailorings"
JOBS = "/api/v1/jobs"
RESUMES = "/api/v1/resumes"

CHIPS = ["Too long", "Wrong emphasis"]


def _setup(client, headers, docx_bytes, job_payload):
    client.post(
        RESUMES,
        headers=headers,
        files={"file": ("cv.docx", docx_bytes, "application/octet-stream")},
    )
    return client.post(JOBS, headers=headers, json=job_payload).json()


def _tailor(client, headers, job_id, **extra):
    return client.post(TAILORINGS, headers=headers, json={"job_id": job_id, **extra})


# ── The prompt ───────────────────────────────────────────────────────────────


def test_a_first_run_sends_no_previous_attempt(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    _tailor(client, auth_headers, job["id"])

    prompt = fake_llm.calls[0]["prompt"]
    assert "YOUR PREVIOUS ATTEMPT" not in prompt
    assert "WHAT THE CANDIDATE SAYS IS WRONG" not in prompt


def test_a_refine_sends_the_previous_text_and_the_complaints(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    first = _tailor(client, auth_headers, job["id"]).json()

    r = _tailor(
        client,
        auth_headers,
        job["id"],
        refine_of=first["id"],
        feedback=CHIPS,
        feedback_notes="Lead with the platform work, not the reporting.",
    )
    assert r.status_code == 201, r.text

    prompt = fake_llm.calls[-1]["prompt"]
    # The model needs the text it is revising, or it just starts over.
    assert first["tailored_text"] in prompt
    for chip in CHIPS:
        assert chip in prompt
    assert "Lead with the platform work" in prompt


def test_the_no_fabrication_rule_is_restated_after_the_critique(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    """The complaints are user-supplied text. "Make me sound stronger" must not
    read as licence to invent, so the rule is repeated after them rather than
    left only in the system prompt."""
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    first = _tailor(client, auth_headers, job["id"]).json()

    _tailor(
        client,
        auth_headers,
        job["id"],
        refine_of=first["id"],
        feedback=["Make me sound stronger"],
    )

    prompt = fake_llm.calls[-1]["prompt"]
    critique_at = prompt.index("WHAT THE CANDIDATE SAYS IS WRONG")
    rule_at = prompt.index("Do not add any experience")
    assert rule_at > critique_at


# ── Lineage ──────────────────────────────────────────────────────────────────


def test_a_refine_records_what_it_came_from(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    first = _tailor(client, auth_headers, job["id"]).json()
    assert first["refine_of_id"] is None
    assert first["feedback"] is None

    second = _tailor(
        client, auth_headers, job["id"], refine_of=first["id"], feedback=CHIPS
    ).json()

    assert second["refine_of_id"] == first["id"]
    assert second["feedback"] == CHIPS


def test_both_versions_survive_in_the_history(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    first = _tailor(client, auth_headers, job["id"]).json()
    _tailor(client, auth_headers, job["id"], refine_of=first["id"], feedback=CHIPS)

    history = client.get(f"{TAILORINGS}?job_id={job['id']}", headers=auth_headers).json()
    # Refining must not overwrite — the earlier version stays downloadable.
    assert len(history) == 2


# ── Refusals ─────────────────────────────────────────────────────────────────


def test_refining_with_no_complaint_is_rejected(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    first = _tailor(client, auth_headers, job["id"]).json()
    before = len(fake_llm.calls)

    r = _tailor(client, auth_headers, job["id"], refine_of=first["id"])
    assert r.status_code == 422
    # Re-running the identical prompt is exactly what the loop exists to avoid.
    assert len(fake_llm.calls) == before


def test_blank_feedback_notes_alone_is_not_a_complaint(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    first = _tailor(client, auth_headers, job["id"]).json()

    r = _tailor(
        client, auth_headers, job["id"], refine_of=first["id"], feedback_notes="   "
    )
    assert r.status_code == 422


def test_refining_a_version_from_another_job_is_rejected(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job_a = _setup(client, auth_headers, docx_bytes, job_payload)
    job_b = client.post(
        JOBS, headers=auth_headers, json={**job_payload, "title": "Other role"}
    ).json()

    from_a = _tailor(client, auth_headers, job_a["id"]).json()

    r = _tailor(
        client, auth_headers, job_b["id"], refine_of=from_a["id"], feedback=CHIPS
    )
    # Silently revising against the wrong posting would produce nonsense.
    assert r.status_code == 400
    assert "different job" in r.json()["detail"]


def test_refining_a_failed_version_is_rejected(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    from app.services.llm import LLMError

    job = _setup(client, auth_headers, docx_bytes, job_payload)
    fake_llm.error = LLMError("quota exceeded")
    client.post(TAILORINGS, headers=auth_headers, json={"job_id": job["id"]})
    fake_llm.error = None

    failed = client.get(f"{TAILORINGS}?job_id={job['id']}", headers=auth_headers).json()[0]
    assert failed["status"] == "failed"

    r = _tailor(client, auth_headers, job["id"], refine_of=failed["id"], feedback=CHIPS)
    assert r.status_code == 409
    assert "nothing to refine" in r.json()["detail"]


def test_cannot_refine_another_users_version(
    client, make_user, docx_bytes, job_payload, fake_llm
):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    alice_job = _setup(client, alice, docx_bytes, job_payload)
    alice_version = _tailor(client, alice, alice_job["id"]).json()

    bob_job = _setup(client, bob, docx_bytes, job_payload)
    r = _tailor(
        client, bob, bob_job["id"], refine_of=alice_version["id"], feedback=CHIPS
    )
    assert r.status_code == 404


def test_too_many_feedback_items_is_rejected(
    client, auth_headers, docx_bytes, job_payload, fake_llm
):
    job = _setup(client, auth_headers, docx_bytes, job_payload)
    first = _tailor(client, auth_headers, job["id"]).json()

    r = _tailor(
        client,
        auth_headers,
        job["id"],
        refine_of=first["id"],
        feedback=[f"complaint {i}" for i in range(20)],
    )
    # Unbounded feedback is a cheap way to blow up the prompt.
    assert r.status_code == 422
