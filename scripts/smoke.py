#!/usr/bin/env python3
"""End-to-end smoke test: drives the real user journey against a live API.

Written to be pointed at a deployment, not just localhost — the point is to
prove the real thing works, including object storage and the LLM provider,
which unit tests deliberately stub out.

    # local
    backend/.venv/bin/python scripts/smoke.py

    # deployed
    backend/.venv/bin/python scripts/smoke.py https://resume-tailor-api.onrender.com

Email verification is mandatory, and no script can read an inbox, so the run
has two parts:

  * Always — health, signup, and proof that an unverified account is refused.
  * The full journey — only when SMOKE_EMAIL and SMOKE_PASSWORD name an
    already-verified account:

        SMOKE_EMAIL=you@example.com SMOKE_PASSWORD=... \
          backend/.venv/bin/python scripts/smoke.py <url>

Signup leaves a throwaway unverified account behind; harmless, but worth
knowing before running it against something you care about.
"""

from __future__ import annotations

import io
import os
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


def step(text: str) -> None:
    print(f"-> {text}", flush=True)


def main(argv: list[str]) -> int:
    origin = (argv[1] if len(argv) > 1 else DEFAULT_BASE).rstrip("/")
    base = f"{origin}/api/v1"
    print(f"Target: {base}\n")

    client = httpx.Client(base_url=base, timeout=TIMEOUT, follow_redirects=True)
    failures: list[str] = []

    # ── Always run ────────────────────────────────────────────────────────────

    step("health")
    started = time.time()
    r = client.get("/health/ready")
    r.raise_for_status()
    print(f"   {r.json()}  ({time.time() - started:.1f}s — slow means a cold start)")

    step("signup creates an unverified account")
    throwaway = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/signup", json={"email": throwaway, "password": "smoke-pw-123"})
    r.raise_for_status()
    unverified = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if r.json()["user"]["is_verified"] is not False:
        failures.append("a brand new account was already marked verified")
    print(f"   {throwaway}, is_verified={r.json()['user']['is_verified']}")

    step("unverified account is refused by the app")
    for path in ("/resumes", "/jobs", "/tailorings"):
        code = client.get(path, headers=unverified).status_code
        if code != 403:
            failures.append(f"GET {path} gave {code} for an unverified user, expected 403")
    # 401 would make the client discard the token and sign the user out, losing
    # the session they need in order to request a resend.
    print("   403 on /resumes, /jobs, /tailorings")

    step("unverified account can still reach /auth/me")
    if client.get("/auth/me", headers=unverified).status_code != 200:
        failures.append("/auth/me was blocked for an unverified user")

    step("an unknown verification token is rejected")
    if client.post("/auth/verify", json={"token": "definitely-not-real"}).status_code != 400:
        failures.append("a bogus verification token was not rejected with 400")

    # ── Full journey, only with a verified account ─────────────────────────────

    email = os.environ.get("SMOKE_EMAIL")
    password = os.environ.get("SMOKE_PASSWORD")

    if not (email and password):
        print(
            "\nSkipping the full journey: set SMOKE_EMAIL and SMOKE_PASSWORD to a\n"
            "verified account to exercise upload, storage, tailoring and download."
        )
    else:
        step(f"login as {email}")
        r = client.post("/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            print(f"   FAILED {r.status_code}: {r.text[:200]}")
            failures.append("could not log in with SMOKE_EMAIL / SMOKE_PASSWORD")
            return _report(failures)

        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        if not r.json()["user"]["is_verified"]:
            failures.append("SMOKE_EMAIL names an unverified account")
            return _report(failures)

        step("upload resume")
        r = client.post(
            "/resumes",
            headers=headers,
            files={"file": ("resume.docx", sample_resume(), "application/octet-stream")},
        )
        r.raise_for_status()
        resume = r.json()
        print(f"   parsed {len(resume['parsed_text'])} chars")
        if "PostgreSQL" not in resume["parsed_text"]:
            failures.append("table text was not extracted from the .docx")

        step("download the original back (proves storage round-trips)")
        r = client.get(f"/resumes/{resume['id']}/download", headers=headers)
        r.raise_for_status()
        print(f"   {len(r.content)} bytes")
        if r.content[:2] != b"PK":
            failures.append("stored resume did not come back as a valid .docx")

        step("create job")
        r = client.post("/jobs", headers=headers, json=JOB)
        r.raise_for_status()
        job = r.json()

        step("tailor (live LLM call)")
        started = time.time()
        r = client.post("/tailorings", headers=headers, json={"job_id": job["id"]})
        if r.status_code != 201:
            print(f"   FAILED {r.status_code}: {r.text[:400]}")
            failures.append(f"tailoring returned {r.status_code}")
        else:
            t = r.json()
            print(f"   {t['status']} in {time.time() - started:.1f}s")
            print(f"   match_score      : {t['match_score']}")
            print(f"   missing_keywords : {t['missing_keywords']}")

            step("download tailored .docx")
            r = client.get(f"/tailorings/{t['id']}/download", headers=headers)
            r.raise_for_status()
            print(f"   {len(r.content)} bytes")
            if r.content[:2] != b"PK":
                failures.append("tailored file was not a valid .docx")

            step("tenant isolation")
            # The unverified throwaway cannot read anything, so a second
            # verified account is not needed to prove scoping here: the gate
            # already refuses it, and unit tests cover verified cross-tenant
            # access.
            code = client.get(f"/tailorings/{t['id']}", headers=unverified).status_code
            if code != 403:
                failures.append(f"another account got {code} for this tailoring")
            print("   other account refused")

        step("cleanup")
        client.delete(f"/jobs/{job['id']}", headers=headers)
        client.delete(f"/resumes/{resume['id']}", headers=headers)
        print("   removed the job and resume created by this run")

    return _report(failures)


def _report(failures: list[str]) -> int:
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
