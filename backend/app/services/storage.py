"""File storage behind one interface.

Routes and services deal in opaque string *keys*, never filesystem paths, so
swapping local disk for S3/R2 in production is a config change rather than a
code change.
"""

import re
import uuid
from abc import ABC, abstractmethod
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


def get_storage() -> StorageBackend:
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "local":
        return LocalStorage(settings.LOCAL_STORAGE_DIR)
    if backend == "s3":
        raise StorageError(
            "The S3 backend is not implemented yet. Set STORAGE_BACKEND=local "
            "for development."
        )
    raise StorageError(f"Unknown STORAGE_BACKEND: {settings.STORAGE_BACKEND!r}")
