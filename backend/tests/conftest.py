"""Test fixtures.

Tests run against an in-memory SQLite database so the suite needs no network
and no running Postgres. That is a deliberate trade-off: it keeps CI fast, but
it will not catch Postgres-specific schema problems. Migrations are still
verified against real Postgres via `alembic upgrade head`.
"""

import os
import tempfile

# Must be set before app.core.config is imported anywhere — Settings is cached
# with lru_cache and reads the environment once, at first import.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
# Keep uploads out of the real backend/uploads directory.
os.environ.setdefault(
    "LOCAL_STORAGE_DIR", tempfile.mkdtemp(prefix="resume-tailor-tests-")
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.llm import get_llm_provider  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection, so :memory: persists
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user_payload():
    return {
        "email": "Alice@Example.com",
        "password": "correct-horse-battery",
        "full_name": "Alice Example",
    }


@pytest.fixture
def make_user(client):
    """Create a user and return their Authorization header.

    Two distinct users in one test is the setup that catches cross-tenant leaks,
    so this is a factory rather than a single fixture.
    """

    def _make(email: str = "user@example.com", password: str = "a-good-password"):
        r = client.post(
            "/api/v1/auth/signup", json={"email": email, "password": password}
        )
        assert r.status_code == 201, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest.fixture
def auth_headers(make_user):
    return make_user()


@pytest.fixture
def docx_bytes():
    """A minimal but realistic .docx, including a table (skills are usually
    laid out in one, and table text is easy to drop during extraction)."""
    import io

    from docx import Document

    doc = Document()
    doc.add_paragraph("Manoj Kumar")
    doc.add_paragraph("Senior Data Analyst")
    doc.add_paragraph("Built reporting pipelines in SQL and Python.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Skills"
    table.rows[0].cells[1].text = "SQL, Python, dbt"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


DEFAULT_LLM_PAYLOAD = {
    "tailored_resume": (
        "Manoj Kumar\n"
        "EXPERIENCE\n"
        "- Built reporting pipelines in SQL and Python for analytics teams.\n"
        "SKILLS\n"
        "- SQL, Python, dbt, Snowflake\n"
    ),
    "match_score": 78,
    "missing_keywords": ["Snowflake administration"],
    "changes": ["Surfaced dbt experience in the skills section"],
}


class FakeLLM:
    """Deterministic stand-in for a real provider.

    Records its calls so tests can assert on what was actually sent to the
    model, and never touches the network.
    """

    model_name = "fake-model-1"

    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else dict(DEFAULT_LLM_PAYLOAD)
        self.error = error
        self.calls: list[dict] = []

    def generate_json(self, *, system: str, prompt: str) -> dict:
        self.calls.append({"system": system, "prompt": prompt})
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.fixture
def fake_llm(client):
    fake = FakeLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_provider, None)


@pytest.fixture
def job_payload():
    return {
        "title": "Senior Data Analyst",
        "company": "Acme Corp",
        "location": "Remote",
        "description": (
            "We are looking for a Senior Data Analyst with 5+ years of "
            "experience in SQL, Python and data visualisation. Experience "
            "with dbt and Snowflake strongly preferred."
        ),
    }
