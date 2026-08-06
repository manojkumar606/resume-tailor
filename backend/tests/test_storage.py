import uuid

import pytest

from app.services.storage import (
    LocalStorage,
    S3Storage,
    StorageError,
    build_key,
    get_storage,
)


def test_build_key_is_tenant_scoped_and_keeps_the_extension():
    user_id = uuid.uuid4()
    key = build_key(user_id, "resumes", "My Resume 2026.docx")
    assert key.startswith(f"{user_id}/resumes/")
    assert key.endswith(".docx")
    # The original filename must not survive into the key — it is attacker
    # controlled and may contain anything.
    assert "My Resume" not in key


def test_build_key_drops_a_suspicious_extension():
    key = build_key(uuid.uuid4(), "resumes", "payload.tar.gz/../../etc/passwd")
    assert ".." not in key
    assert key.endswith("/") is False


def test_build_key_is_unique_per_call():
    user_id = uuid.uuid4()
    a = build_key(user_id, "resumes", "cv.pdf")
    b = build_key(user_id, "resumes", "cv.pdf")
    assert a != b


def test_local_storage_round_trip(tmp_path):
    store = LocalStorage(tmp_path)
    key = build_key(uuid.uuid4(), "resumes", "cv.docx")

    store.save(key, b"hello")
    assert store.load(key) == b"hello"

    store.delete(key)
    with pytest.raises(StorageError):
        store.load(key)


def test_local_storage_delete_is_idempotent(tmp_path):
    store = LocalStorage(tmp_path)
    key = build_key(uuid.uuid4(), "resumes", "cv.docx")
    # Deleting something that was never there must not raise: cleanup runs
    # after the database row is already gone and cannot be retried.
    store.delete(key)


@pytest.mark.parametrize(
    "bad_key",
    [
        "../../etc/passwd",
        "not-a-uuid/resumes/file.docx",
        "/absolute/path",
        "00000000-0000-0000-0000-000000000000/resumes/../../escape.docx",
        "",
    ],
)
def test_local_storage_rejects_unsafe_keys(tmp_path, bad_key):
    store = LocalStorage(tmp_path)
    with pytest.raises(StorageError):
        store.save(bad_key, b"x")
    with pytest.raises(StorageError):
        store.load(bad_key)


def test_local_storage_cannot_escape_its_root(tmp_path):
    """A key that passes the regex must still resolve inside the root."""
    outside = tmp_path / "outside"
    outside.mkdir()
    store = LocalStorage(tmp_path / "root")

    # Symlink trick: a valid-looking key whose parent points elsewhere.
    valid_uuid = "00000000-0000-0000-0000-000000000000"
    (store.root / valid_uuid).mkdir(parents=True)
    (store.root / valid_uuid / "resumes").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StorageError):
        store.save(f"{valid_uuid}/resumes/leak.docx", b"secret")


def test_s3_storage_names_every_missing_setting():
    with pytest.raises(StorageError) as exc:
        S3Storage(
            endpoint_url="", bucket="", access_key_id="", secret_access_key=""
        )
    message = str(exc.value)
    for name in (
        "S3_ENDPOINT_URL",
        "S3_BUCKET",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
    ):
        assert name in message


def test_unknown_storage_backend_is_rejected(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "STORAGE_BACKEND", "dropbox")
    get_storage.cache_clear()
    try:
        with pytest.raises(StorageError, match="Unknown STORAGE_BACKEND"):
            get_storage()
    finally:
        # Leave the cache clean for the rest of the suite.
        get_storage.cache_clear()
