# Working on this repo

Resume tailoring and job-application tracking. FastAPI + Postgres (Neon) on
Render, React + Vite on Vercel, Cloudflare R2 for files, Gemini for the LLM.

`README.md` has setup and architecture. This file is the things that are not
obvious from the code, and that have already cost a production incident or a
broken test suite once.

## Ground rules

- **One user's data is never reachable by another.** Every table has `user_id`,
  every query filters by it, and a row belonging to someone else is a **404,
  not a 403** — a 403 confirms the id exists.
- **Never migrate production ahead of the code.** The container runs
  `alembic upgrade head && uvicorn`, so a migration the code does not know about
  takes the whole app down. This happened on 2026-08-12. Code and migration ship
  in the same push, always.
- **Push a branch and open a PR for anything that is code.** Render's "wait for
  CI checks to pass" gate is **on** since 2026-08-29, so a red build no longer
  reaches production — that was the catastrophic case and it is closed. What a
  PR still buys is a `main` that is never red, and a place to read a change
  before it is merged. Docs-only changes can go straight to `main`.
- **Error text that reaches a user is a sentence, not a log line.** A raw
  provider response on screen is a bug. Log the detail, raise the sentence.

## Backend

- Python 3.12, SQLAlchemy 2.0 (`Mapped` / `mapped_column`), Alembic, PyJWT,
  bcrypt used directly. Run things with `backend/.venv/bin/python`.
- `app/services/llm.py` is a provider seam: **nothing above it imports a vendor
  SDK.** Swapping Gemini for another provider is a new class here, not a
  refactor. Same shape for `services/email.py` and `services/storage.py`.
- Auth is email OTP at every sign-in. Codes are stored HMAC-SHA256 keyed with
  `SECRET_KEY` — six digits is a million possibilities, so a bare hash is not
  enough.
- Every token names a row in `sessions`. A token with no `sid` is refused, not
  trusted. Idle expiry is enforced server-side; the browser timer is a courtesy.
- Tailoring is **asynchronous**: `POST /tailorings` returns 202 with a `pending`
  row and the client polls. Validation stays synchronous, so a bad request is
  still an immediate 4xx.

### Migrations

- `sa.Enum` inside `add_column` does **not** emit `CREATE TYPE` on Postgres —
  only `create_table` does. Create the type explicitly with
  `sa.Enum(...).create(op.get_bind(), checkfirst=True)`.
- In `downgrade`, drop the enum **after** the table that uses it.
- Match the model exactly, including `server_default=sa.text('now()')` on the
  timestamp columns, or `alembic check` fails in CI.
- **SQLite cannot run the migration chain** — the initial migration uses
  Postgres-only types. Tests use `Base.metadata.create_all` instead. The
  `migrations` CI job against real Postgres is the only real verification.

### Tests

`backend/.venv/bin/python -m pytest -q` — around 100 seconds.

- Tests use in-memory SQLite with `StaticPool` and go through the **real**
  sign-up → emailed code → verify flow. No fixture writes `is_verified`
  directly, so a fixture cannot pass while the real path is broken.
- **Anything a test needs to fake must be a FastAPI dependency**, or the
  override silently does not apply. This has bitten twice: a mailer hidden as a
  module-level helper, and a background task that called `SessionLocal()`
  directly and quietly opened a second, empty database. Background tasks
  receive their provider and session factory as arguments.
- **Mutation-check anything that matters.** Break the behaviour on purpose and
  confirm the tests fail. Several tests here look obviously correct and were
  only proven by doing this.

## Frontend

- React 19, Vite, TypeScript with `erasableSyntaxOnly` (so **no constructor
  parameter properties**), Tailwind 4, React Router 7.
- **Dark only.** Colours come from `@theme` tokens in `index.css`
  (`canvas`, `panel`, `raised`, `edge`, `ink`, `ink-muted`, `ink-faint`,
  `brand`). No `dark:` variants anywhere.
- All animation respects `prefers-reduced-motion`.
- `lib/api.ts` is the only place that talks to the API. Two rules that fixed a
  bug reported twice: credential endpoints are **never** sent a bearer token,
  and "your session expired" requires that a token was actually sent.
- `npx vitest run` collects `src/**/*.test.ts` — **`.tsx` is not collected**, so
  there are no component render tests yet.

## Deploying

Merging to `main` deploys both. Check CI first:
<https://github.com/manojkumar606/resume-tailor/actions>

CI has three jobs: `backend`, `frontend`, and `migrations` (upgrade → downgrade
base → upgrade → `alembic check` against real Postgres). It has caught three
real bugs that would otherwise have reached production.

## Where the plan lives

`SPRINT.md` in the repo root — **not committed** (it is in `.git/info/exclude`).
It holds what is being built next, what was deliberately dropped and why, and
what is waiting on the owner. Read it before starting a feature, and update its
status when one lands.
