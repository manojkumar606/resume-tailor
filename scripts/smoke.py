#!/usr/bin/env python3
"""End-to-end smoke test: drives the whole user journey against a live API.

Written to be pointed at a deployment, not just localhost — the point is to
prove the real thing works, including object storage and the LLM provider,
which unit tests deliberately stub out.

    # local
    backend/.venv/bin/python scripts/smoke.py

    # deployed
    backend/.venv/bin/python scripts/smoke.py https://resume-tailor-api.onrender.com

Creates two throwaway accounts and leaves them behind; harmless, but worth
knowing before running it against something you care about.
"""

from __future__ import annotations

import io
import sys
import time
import uuid

import httpx
from docx import Document

DEFAULT_BASE = "http://127.0.0.1:8000"

# Render free instances sleep after inactivity and can take ~60s to wake, so
# the first request needs a far longer timeout than a warm one would.
TIMEOUT = httpx.Timeout(180.0, connect=90.0)

JOB = {
    "title": "Backend Engineer (Python)",
    "company": "Northwind Labs",
    "location": "Remote, India",
    "description": (
        "We are hiring a Backend Engineer to build and scale our Python API "
        "platform. You will design REST APIs with FastAPI, model data in "
        "PostgreSQL, and own services end to end. Requirements: 2+ years of "
        "Python, strong SQL, experience with REST API design, familiarity "
        "with Docker and CI/CD pipelines. Nice to have: Kubernetes, AWS, and "
        "async task queues such as Celery."
    ),
}


def sample_resume() -> bytes:
    """A small but realistic .docx, including a table — skills are usually laid
    out in one, and table text is easy to lose during extraction."""
    doc = Document()
    for line in (
        "Sample Candidate",
        "sample@example.com | Hyderabad, India",
        "SUMMARY",
        "Software engineer with 3 years building backend services.",
        "EXPERIENCE",
        "Software Engineer, Example Corp - 2022 to present",
        "- Built Python services that process assessment data.",
        "- Automated reporting, cutting manual effort by 6 hours a week.",
        "EDUCATION",
        "B.Tech, Computer Science - 2022",
    ):
        doc.add_paragraph(line)

    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Skills"
    table.rows[0].cells[1].text = "Python, SQL, PostgreSQL, FastAPI, Git"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def step(n: int, text: str) -> None:
    print(f"{n}. {text}", flush=True)


def main(argv: list[str]) -> int:
    origin = (argv[1] if len(argv) > 1 else DEFAULT_BASE).rstrip("/")
    base = f"{origin}/api/v1"
    print(f"Target: {base}\n")

    client = httpx.Client(base_url=base, timeout=TIMEOUT, follow_redirects=True)
    failures: list[str] = []

    step(1, "health")
    started = time.time()
    r = client.get("/health/ready")
    r.raise_for_status()
    print(f"   {r.json()}  ({time.time() - started:.1f}s — slow means a cold start)")

    step(2, "signup")
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": "smoke-test-pw-123"})
    r.raise_for_status()
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    print(f"   {email}")

    step(3, "upload resume")
    r = client.post(
        "/resumes",
        headers=headers,
        files={"file": ("resume.docx", sample_resume(), "application/octet-stream")},
    )
    r.raise_for_status()
    resume = r.json()
    print(f"   parsed {len(resume['parsed_text'])} chars, default={resume['is_default']}")
    if "PostgreSQL" not in resume["parsed_text"]:
        failures.append("table text was not extracted from the .docx")

    step(4, "download the original back (proves storage round-trips)")
    r = client.get(f"/resumes/{resume['id']}/download", headers=headers)
    r.raise_for_status()
    print(f"   {len(r.content)} bytes returned")
    if r.content[:2] != b"PK":
        failures.append("stored resume did not come back as a valid .docx")

    step(5, "create job")
    r = client.post("/jobs", headers=headers, json=JOB)
    r.raise_for_status()
    job = r.json()
    print(f"   {job['title']} @ {job['company']}")

    step(6, "tailor (live LLM call)")
    started = time.time()
    r = client.post("/tailorings", headers=headers, json={"job_id": job["id"]})
    if r.status_code != 201:
        print(f"   FAILED {r.status_code}: {r.text[:400]}")
        failures.append(f"tailoring returned {r.status_code}")
        tailoring = None
    else:
        tailoring = r.json()
        print(f"   {tailoring['status']} in {time.time() - started:.1f}s via {tailoring['model']}")
        print(f"   match_score      : {tailoring['match_score']}")
        print(f"   missing_keywords : {tailoring['missing_keywords']}")

    if tailoring:
        step(7, "download tailored .docx")
        r = client.get(f"/tailorings/{tailoring['id']}/download", headers=headers)
        r.raise_for_status()
        print(f"   {len(r.content)} bytes")
        if r.content[:2] != b"PK":
            failures.append("tailored file was not a valid .docx")

    step(8, "tenant isolation")
    other = client.post(
        "/auth/signup",
        json={"email": f"other-{uuid.uuid4().hex[:8]}@example.com", "password": "other-pw-123"},
    )
    other.raise_for_status()
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    if client.get("/resumes", headers=other_headers).json():
        failures.append("a second user could see the first user's resumes")
    if client.get(f"/resumes/{resume['id']}", headers=other_headers).status_code != 404:
        failures.append("a second user could fetch the first user's resume by id")
    if tailoring:
        code = client.get(f"/tailorings/{tailoring['id']}", headers=other_headers).status_code
        if code != 404:
            failures.append(f"a second user got {code} for another user's tailoring, expected 404")
    print("   second user sees nothing and gets 404s")

    print()
    if failures:
        print("SMOKE TEST FAILED")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
