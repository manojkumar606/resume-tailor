"""File storage behind one interface.

Routes and services deal in opaque string *keys*, never filesystem paths, so
swapping local disk for S3/R2 in production is a config change rather than a
code change.
"""

import re
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

# Keys we generate look like "<user-uuid>/resumes/<uuid>.docx". Anything that
# does not match is rejected before it reaches the filesystem — this is what
# stops a crafted key from escaping the storage root via "../".
_SAFE_KEY = re.compile(r"^[0-9a-fA-F-]{36}/[a-z_]+/[0-9a-zA-Z._-]+$")


class StorageError(Exception):
    pass


def build_key(user_id: uuid.UUID, kind: str, filename: str) -> str:
    """Generate a collision-free, tenant-scoped storage key.

    The original filename is never used as the stored name — only its
    extension is kept, and only if it looks sane.
    """
    suffix = Path(filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix or ""):
        suffix = ""
    return f"{user_id}/{kind}/{uuid.uuid4()}{suffix}"


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def load(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalStorage(StorageBackend):
    """Development backend. Not suitable for production: most PaaS filesystems
    are ephemeral, so uploads vanish on redeploy."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.match(key):
            raise StorageError(f"Unsafe storage key: {key!r}")
        path = (self.root / key).resolve()
        # Belt and braces: even with the regex, confirm we stayed inside root.
        if not path.is_relative_to(self.root):
            raise StorageError(f"Storage key escapes root: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"No stored object for key: {key!r}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)


class S3Storage(StorageBackend):
    """Any S3-compatible object store. Configured for Cloudflare R2 by default.

    Used in production because container filesystems are ephemeral: a redeploy
    or a sleep/wake cycle on a free host wipes local uploads.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
    ):
        missing = [
            name
            for name, value in (
                ("S3_ENDPOINT_URL", endpoint_url),
                ("S3_BUCKET", bucket),
                ("S3_ACCESS_KEY_ID", access_key_id),
                ("S3_SECRET_ACCESS_KEY", secret_access_key),
            )
            if not value
        ]
        if missing:
            raise StorageError(
                f"STORAGE_BACKEND=s3 but these are unset: {', '.join(missing)}"
            )

        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            # R2 has no regions but the SDK insists on one; "auto" is what
            # Cloudflare documents.
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    @staticmethod
    def _check(key: str) -> str:
        # Same validation as the local backend. Object stores treat "../" as a
        # literal key rather than traversal, but a consistent key shape means a
        # key written by one backend is always readable by the other.
        if not _SAFE_KEY.match(key):
            raise StorageError(f"Unsafe storage key: {key!r}")
        return key

    def save(self, key: str, data: bytes) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self._client.put_object(Bucket=self.bucket, Key=self._check(key), Body=data)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Could not upload {key!r}: {exc}") from exc

    def load(self, key: str) -> bytes:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            response = self._client.get_object(
                Bucket=self.bucket, Key=self._check(key)
            )
            return response["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            # Map "not there" to the same error the local backend raises, so
            # callers return 404 rather than 500.
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise StorageError(f"No stored object for key: {key!r}") from exc
            raise StorageError(f"Could not read {key!r}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Could not read {key!r}: {exc}") from exc

    def delete(self, key: str) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._check(key))
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Could not delete {key!r}: {exc}") from exc


@lru_cache
def get_storage() -> StorageBackend:
    """Cached: building a boto3 client per request is measurable overhead, and
    LocalStorage would re-run mkdir every time."""
    backend = settings.STORAGE_BACKEND.lower()

    if backend == "local":
        return LocalStorage(settings.LOCAL_STORAGE_DIR)

    if backend == "s3":
        return S3Storage(
            endpoint_url=settings.S3_ENDPOINT_URL,
            bucket=settings.S3_BUCKET,
            access_key_id=settings.S3_ACCESS_KEY_ID,
            secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        )

    raise StorageError(f"Unknown STORAGE_BACKEND: {settings.STORAGE_BACKEND!r}")
