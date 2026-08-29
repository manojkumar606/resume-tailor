"""Database engine, session factory, and the FastAPI session dependency."""

from collections.abc import Callable, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.base import Base  # noqa: F401  (re-exported for Alembic)

if not settings.DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Create a free Postgres at https://neon.tech, "
        "then put the connection string in .env using the postgresql+psycopg:// prefix."
    )

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # Neon closes idle connections; revalidate before use
    pool_recycle=300,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> Callable[[], Session]:
    """The session factory, as a dependency.

    Background work outlives the request, and the request's session is closed
    the moment the response is sent — so a task has to open its own. Injected
    rather than imported directly so tests can point it at their in-memory
    database instead of the real engine.
    """
    return SessionLocal
