"""Local storage behaviour, including path-traversal resistance."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from claimtrace_api.storage.base import StorageError, validate_storage_key
from claimtrace_api.storage.local import LocalFileStorage, build_storage_key


@pytest.fixture
def storage(storage_root: Path) -> LocalFileStorage:
    return LocalFileStorage(storage_root)


def _digest(data: bytes = b"payload") -> str:
    return hashlib.sha256(data).hexdigest()


def test_round_trip(storage: LocalFileStorage) -> None:
    key = build_storage_key(_digest())

    storage.write(key, b"payload")

    assert storage.exists(key)
    assert storage.read(key) == b"payload"


def test_key_is_content_addressed_not_filename_derived() -> None:
    digest = _digest()

    key = build_storage_key(digest)

    assert key == f"{digest[:2]}/{digest}.pdf"
    assert "payload" not in key


def test_write_is_atomic_leaving_no_temp_files(storage: LocalFileStorage) -> None:
    key = build_storage_key(_digest())

    storage.write(key, b"payload")

    leftovers = list(storage.root.rglob("*.tmp"))
    assert leftovers == []


def test_overwrite_replaces_content(storage: LocalFileStorage) -> None:
    key = build_storage_key(_digest())
    storage.write(key, b"first")

    storage.write(key, b"second")

    assert storage.read(key) == b"second"


def test_delete_is_idempotent(storage: LocalFileStorage) -> None:
    key = build_storage_key(_digest())
    storage.write(key, b"payload")

    storage.delete(key)
    storage.delete(key)

    assert not storage.exists(key)


def test_reading_a_missing_object_raises(storage: LocalFileStorage) -> None:
    with pytest.raises(StorageError):
        storage.read(build_storage_key(_digest(b"absent")))


@pytest.mark.parametrize(
    "hostile_key",
    [
        "../escape.pdf",
        "a/../../escape.pdf",
        "/etc/passwd",
        "..\\windows\\system32",
        "C:/windows/system32",
        "nested/../../../escape",
        "with\x00null",
        "",
        "./relative",
        "trailing/",
    ],
)
def test_traversal_and_absolute_keys_are_rejected(
    storage: LocalFileStorage, hostile_key: str
) -> None:
    with pytest.raises(StorageError):
        storage.write(hostile_key, b"payload")


def test_written_files_stay_inside_the_root(storage: LocalFileStorage, tmp_path: Path) -> None:
    key = build_storage_key(_digest())

    storage.write(key, b"payload")

    written = list(storage.root.rglob("*.pdf"))
    assert len(written) == 1
    assert storage.root in written[0].parents
    # Nothing was created beside the storage root.
    assert not (tmp_path / "escape.pdf").exists()


def test_storage_key_must_come_from_a_digest() -> None:
    with pytest.raises(StorageError):
        build_storage_key("not-a-digest")

    with pytest.raises(StorageError):
        build_storage_key("z" * 64)


def test_valid_keys_pass_validation() -> None:
    assert validate_storage_key("ab/abcdef.pdf") == "ab/abcdef.pdf"
