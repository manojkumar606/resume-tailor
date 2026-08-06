# Resume Tailor

AI-powered resume tailoring and job application tracker.

Upload a base resume, paste a job posting, get a version of the resume rewritten
for that specific role — then track the application through to offer or rejection.

## Why the server never touches LinkedIn

An earlier prototype (kept in `legacy/`) logged into LinkedIn with a stored
password and auto-applied. That works for one person and fails as a product:
it means holding other people's credentials, it breaks LinkedIn's User Agreement
in a way that gets *users'* accounts banned, and it hits CAPTCHA and IP blocks at
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
legacy/           original single-user prototype, reference only
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

Requires Node 20+.

```bash
cd frontend
npm install
npm run dev                             # http://localhost:5173
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Tests run against in-memory SQLite so no database is needed. This keeps the
suite fast but will not catch Postgres-specific schema issues — those are
covered by running `alembic upgrade head` against real Postgres.

## Migrations

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "describe the change"
.venv/bin/alembic upgrade head
```

Always read a generated migration before applying it; autogenerate does not
detect every change (notably column renames, which it sees as drop + add).
