# Resume Tailor

AI-powered resume tailoring and job application tracker.

Upload a base resume, paste a job posting, get a version of the resume rewritten
for that specific role — then track the application through to offer or rejection.

**Live app** — <https://resume-tailor-seven-ecru.vercel.app>
**API docs** — <https://resume-tailor-api-q27h.onrender.com/docs>

> The API runs on a free Render instance, which sleeps after ~15 minutes idle.
> The first request after a nap can take up to a minute while it wakes.

## Why the server never touches LinkedIn

This project began as a personal script that logged into LinkedIn with a stored
password and auto-applied. That works for one person and fails as a product: it
means holding other people's credentials, it breaks LinkedIn's User Agreement in
a way that gets *users'* accounts banned, and it hits CAPTCHA and IP blocks at
any real volume.

Instead the user brings the job to the app — pasted description, pasted URL, or
(later) a browser extension that captures the page from within their own logged-in
session. No third-party credentials are ever stored server-side.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL (Neon) |
| Auth | JWT bearer tokens, bcrypt |
| Frontend | React + Vite + TypeScript |
| LLM | Gemini (behind a provider interface) |
| Storage | Local disk in dev, S3-compatible in prod |

## Layout

```
backend/          FastAPI service
  app/
    core/         settings, database engine, security primitives
    models/       SQLAlchemy models (all multi-tenant via user_id)
    schemas/      Pydantic request/response contracts
    api/v1/       versioned routes
    services/     business logic (tailoring, parsing, storage)
  alembic/        database migrations
  tests/
frontend/         React SPA
  src/
    lib/          typed API client and shared types
    auth/         session context
    components/   layout, route guard, UI primitives
    pages/        login/signup, dashboard, job detail
```

## Setup

### 1. Secrets

```bash
cp .env.example .env
```

Fill in `.env`. Generate a signing key with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Database

Create a free Postgres project at <https://neon.tech>, copy the connection
string, and put it in `.env` as `DATABASE_URL`.

**Change the prefix from `postgresql://` to `postgresql+psycopg://`** — the
driver is psycopg 3, and SQLAlchemy picks psycopg2 without the explicit prefix.

### 3. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head          # create the schema
.venv/bin/uvicorn app.main:app --reload # http://localhost:8000/docs
```

### 4. Frontend

Requires Node 20+ (`nvm install 22`).

```bash
cd frontend
npm install
npm run dev                             # http://localhost:5173
```

Run both servers at once, in two terminals. Vite proxies `/api` to
`127.0.0.1:8000`, so the browser sees a single origin and CORS never applies in
development — and the client's API base path is the same in dev and production.

### A note on the Gemini model

`GEMINI_MODEL` is set to `gemini-flash-latest`. The pinned `gemini-2.0-flash`
and `gemini-2.0-flash-lite` return 429 with a free-tier quota of `0` on the
current key, and `gemini-2.5-flash*` are closed to new users. `-latest` is a
rolling alias, so the model behind it can change without notice; pin a specific
version once the key has real quota.

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Tests run against in-memory SQLite so no database is needed. This keeps the
suite fast but will not catch Postgres-specific schema issues — those are
covered by running `alembic upgrade head` against real Postgres.

### Smoke test

The unit suite stubs out the LLM and uses SQLite, so it proves the logic but not
the deployment. `scripts/smoke.py` exercises the real thing:

```bash
backend/.venv/bin/python scripts/smoke.py                                  # local
backend/.venv/bin/python scripts/smoke.py https://your-api.onrender.com    # deployed
```

It always checks health and the auth surface — signup issues no token, a wrong
password is refused, bad codes are rejected, resend does not reveal whether an
address exists.

Signing in requires a code emailed at that moment, and no script can read an
inbox, so the rest — upload, storage round-trip, a live model call, download —
runs only with a token. Sign in through the browser and copy it from devtools:

```bash
# in the browser console: localStorage.getItem('resume-tailor.token')
SMOKE_TOKEN=eyJhbGci... backend/.venv/bin/python scripts/smoke.py <url>
```

It leaves one throwaway account behind per run.

## Sign-in: password plus an emailed code

Every sign-in needs both a password and a six-digit code emailed at that moment.
Signup works the same way, so the address is proven before the account is usable.

`/auth/signup` and `/auth/login` return **202** and no token. `/auth/verify-code`
is the only endpoint that mints one — a leaked password is therefore not enough
to get in without also holding the mailbox.

Because of that, a bearer token already implies a confirmed address, so the
client needs no separate "verified" state and there is no holding page. The
backend still refuses unverified accounts with 403 as defence in depth; it is
unreachable through the API, and the test for it builds the state directly.

Codes are stored as an **HMAC keyed with `SECRET_KEY`**, not a bare hash. Six
digits is only a million possibilities, so `sha256(code)` would fall to an
offline sweep the moment the table leaked; without the key the digest is useless.
The user id is mixed in too, so one user's stored digest cannot be matched
against another's code.

Guessing is cheap against six digits, so the defences are layered:

- 10 minute expiry
- single use
- retired after 5 wrong attempts rather than surviving to expiry
- issuing a new code retires any outstanding one
- resend is rate limited, and answers identically whether or not the address
  exists, so it cannot enumerate accounts
- a wrong password sends no email at all, so the endpoint cannot be used to
  spam an inbox using only somebody's address

Codes are emailed, and mail from a Gmail address via Brevo has weak DMARC
alignment, so a message can land in spam. With a code required at every login
that means a locked-out user, not just a delayed signup. The UI says to check
spam and offers resend. The standard remedy if it becomes a real problem is
remembering a device for 30 days so codes are only needed on new ones.

### Providers

`EMAIL_PROVIDER=console` writes the code to the log and sends nothing — the
default, so development and tests need no mail account:

```
--- EMAIL (not sent; EMAIL_PROVIDER=console) ---
To: someone@example.com
Subject: 429173 is your Resume Tailor code
```

`EMAIL_PROVIDER=brevo` delivers for real. Brevo gives 300 emails/day free and
allows a single verified sender address without owning a domain.

## Continuous integration

`.github/workflows/ci.yml` runs the backend suite, the frontend suite, and a
type-checking build on every push and pull request. It needs no secrets: the
tests use in-memory SQLite with fake email and model providers, so CI never
touches Neon, Brevo, Gemini or R2.

The workflow produces the checks; turning them into a **gate** is two dashboard
toggles, because Render and Vercel deploy from the same push independently:

- **Render** → service → Settings → Build & Deploy → *Wait for CI checks to pass*
- **Vercel** → project → Settings → Git → *Ignored Build Step* (or require the
  check via branch protection)

Without those, a red build still deploys.

## Daily reminders

A tracker only works if people come back to it, and nothing else in this app
brings them back.

`.github/workflows/reminders.yml` runs at 03:30 UTC (09:00 IST) and calls
`POST /api/v1/internal/reminders/run`. GitHub Actions is the scheduler because
Render's free plan has no cron; the workflow does no work itself.

Two things earn an email, and nothing else does — a reminder people learn to
ignore is worse than none:

- a deadline within `REMINDER_DEADLINE_DAYS` on something **not yet applied to**
- an application sitting in Applied with no movement for `STALE_APPLICATION_DAYS`

Everything due for one person goes into a single digest, and each card is
stamped so a daily job cannot nag about the same one every morning. The stamp is
written only on a successful send, so a failed email is retried next run rather
than silently skipped for a week.

### Opting out

Reminders default to **on** — a retention feature nobody discovers does nothing.
Turning them off is one toggle in Settings, and every digest carries an
unsubscribe link that works straight from the inbox with no session.

That link matters more than it looks: the digest and the sign-in codes go out
from the same Brevo sender, so a spam complaint degrades delivery of the codes
people need to log in at all. An easy unsubscribe is what prevents that.

The link opens a page with a button rather than unsubscribing on load — mail
clients and security scanners prefetch links, and a bare state-changing GET
would opt people out who never clicked anything. The token is a stateless HMAC:
nothing to clean up, and all it can do is turn reminders off.

The flag never touches sign-in codes. Reminders are optional; codes are how
anyone gets in.

### The endpoint

It authenticates with a shared secret in `X-Cron-Secret`, compared in
constant time. An unset `CRON_SECRET` disables it outright — a blank secret
matching a blank header would leave it open.

Setup: put the same value in Render's environment and in the repository's
**Settings → Secrets and variables → Actions → `CRON_SECRET`**.

## Your data

Settings offers a CSV of every tracked application, and account deletion.

Both matter more here than in most apps: job hunting is usually done while
employed, and being able to leave with your data is a large part of why anyone
trusts the thing with a resume in the first place.

Deletion removes rows in dependency order rather than leaning on the cascade —
`tailorings.resume_id` is `ON DELETE RESTRICT`, so a cascade reaching resumes
first would abort the whole delete. Stored files are removed afterwards on a
best-effort basis: the rows are already gone, and an orphaned blob is far less
harmful than a delete the user cannot complete.

## Deployment

Backend on Render (Docker), frontend on Vercel, database on Neon, files on
Cloudflare R2. The Render service is defined in `render.yaml`, so the deploy is
version-controlled rather than a set of dashboard clicks.

### 1. Cloudflare R2

Local disk cannot be used in production — container filesystems are wiped on
every redeploy and on every sleep/wake cycle, so uploads would silently vanish.

1. Cloudflare dashboard → R2 → create a bucket.
2. R2 → Manage API Tokens → create a token with **Object Read & Write**.
3. Note the bucket name, access key id, secret, and account id. The endpoint is
   `https://<account-id>.r2.cloudflarestorage.com` — no bucket name in it.

### 2. Render

New → Blueprint → point at this repo. Render reads `render.yaml` and prompts for
the values marked `sync: false`:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon string, `postgresql+psycopg://` prefix |
| `GEMINI_API_KEY` | from Google AI Studio |
| `S3_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` |
| `S3_BUCKET` | R2 bucket name |
| `S3_ACCESS_KEY_ID` | R2 token key id |
| `S3_SECRET_ACCESS_KEY` | R2 token secret |
| `CORS_ORIGINS` | the Vercel URL — set after step 3 |

Migrations run automatically on container start.

### 3. Vercel

Import the repo, then:

- **Root directory**: `frontend`
- **Environment variable**: `VITE_API_BASE_URL` = the Render URL
  (e.g. `https://resume-tailor-api.onrender.com`, no trailing slash)

Vite inlines this at *build* time, so changing it requires a redeploy — it is
not read at runtime.

### 4. Close the loop

Set `CORS_ORIGINS` on Render to the Vercel URL and redeploy. Without it the
browser blocks every request.

### Known limits of the free tier

- Render free instances sleep after ~15 minutes idle; the next request pays a
  cold start of roughly a minute.
- Tailoring holds the HTTP request open for 10–20 seconds. It works, but it ties
  up a worker for the duration. Moving it behind a queue is the main reason the
  `tailorings` table carries a `status` column.

## Migrations

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "describe the change"
.venv/bin/alembic upgrade head
```

Always read a generated migration before applying it; autogenerate does not
detect every change (notably column renames, which it sees as drop + add).
