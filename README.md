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

The unit suite stubs out the LLM and uses SQLite, so it proves the logic but
not the deployment. `scripts/smoke.py` drives the real user journey — signup,
upload, storage round-trip, a live model call, download, and cross-tenant
isolation — against whatever URL you point it at:

```bash
backend/.venv/bin/python scripts/smoke.py                                  # local
backend/.venv/bin/python scripts/smoke.py https://your-api.onrender.com    # deployed
```

It creates two throwaway accounts and leaves them behind.

## Email verification

Verification is mandatory: every route outside `/auth` returns **403** until the
address is confirmed. 403 rather than 401 on purpose — the token is valid and the
caller is authenticated, they just lack permission. A 401 would make the client
discard a good token and sign the user out, losing the session they need to
request a resend.

Tokens are 256 bits of randomness, single-use, and expire after 24 hours. Only a
SHA-256 hash is stored, so a database leak cannot hand out working links. Plain
SHA-256 is right here even though passwords need bcrypt: there is no low-entropy
secret to brute-force, so a slow KDF buys nothing and a fast hash keeps the
lookup a single indexed query.

Resends are rate limited (default 60s), otherwise the endpoint is an easy way to
flood somebody's inbox.

Signup sends the email *before* committing. If delivery fails the whole signup is
rolled back, because an account that never received its link would be permanently
locked out.

### Providers

`EMAIL_PROVIDER=console` writes the link to the log and sends nothing — the
default, so development and tests need no mail account:

```
--- EMAIL (not sent; EMAIL_PROVIDER=console) ---
To: someone@example.com
Subject: Confirm your email for Resume Tailor
...
http://localhost:5173/verify?token=GPWd42WzNUKO...
```

`EMAIL_PROVIDER=brevo` delivers for real. Brevo gives 300 emails/day free and
lets you verify a single sender address without owning a domain, which is why
it's used here rather than Resend.

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
