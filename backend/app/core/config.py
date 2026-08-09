"""Application settings, loaded from the repo-root .env."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/core/config.py → parents[3] is the repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# In a container only `backend/` is copied, so there is no repo-root .env and
# configuration comes entirely from real environment variables. Passing a
# non-existent path is harmless, but resolving it to None keeps intent obvious.
_ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- App ---
    PROJECT_NAME: str = "Resume Tailor API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    # NoDecode: stop pydantic-settings from JSON-parsing the raw env string,
    # so the validator below can accept a plain comma-separated list.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # --- Security ---
    SECRET_KEY: str = "insecure-dev-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- Database ---
    DATABASE_URL: str = ""

    # --- Email ---
    # console → verification links are logged, nothing is sent. Development
    #           and tests, so no mail account is required.
    # brevo   → real delivery via the Brevo HTTP API.
    EMAIL_PROVIDER: str = "console"
    BREVO_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = ""
    EMAIL_FROM_NAME: str = "Resume Tailor"

    # Where verification links point. This is the frontend, not the API: the
    # user lands on a page which then calls the API with the token.
    FRONTEND_URL: str = "http://localhost:5173"

    EMAIL_VERIFICATION_TTL_HOURS: int = 24
    # Minimum gap between resend requests for one account, so the endpoint
    # cannot be used to flood somebody's inbox.
    EMAIL_RESEND_COOLDOWN_SECONDS: int = 60

    # --- LLM ---
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # --- Storage ---
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: Path = REPO_ROOT / "backend" / "uploads"
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        """Accept a comma-separated string from .env as well as a real list."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # Interactive API docs. Off by default in production, but worth turning on
    # deliberately for a portfolio deployment where the API is the showcase.
    ENABLE_DOCS: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def docs_enabled(self) -> bool:
        return self.ENABLE_DOCS or not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
