"""Local filesystem implementation of :class:`FileStorage`.

Chosen because ClaimTrace is an on-premise product: the originals stay on the
same host as the database, with no object-store dependency. The interface is
narrow enough that another backend is a new class, not a refactor.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from claimtrace_api.storage.base import StorageError, validate_storage_key

logger = logging.getLogger(__name__)


def build_storage_key(sha256: str, *, suffix: str = ".pdf") -> str:
    """Derive a content-addressed key from a digest.

    Content addressing gives deduplication for free and guarantees the client's
    filename never influences where bytes land. The two-character prefix keeps
    directories from growing to millions of sibling entries.
    """
    digest = sha256.lower()
    if len(digest) != 64 or not all(char in "0123456789abcdef" for char in digest):
        raise StorageError("storage key must be derived from a hex sha256 digest")
    return f"{digest[:2]}/{digest}{suffix}"


class LocalFileStorage:
    """Stores objects under a configured root directory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, key: str) -> Path:
        """Map a key to an absolute path that is provably inside the root."""
        validate_storage_key(key)
        candidate = (self._root / key).resolve()
        # Even with a validated key, confirm the resolved path stays inside the
        # root: a symlink inside the storage tree could otherwise redirect a write.
        if candidate != self._root and self._root not in candidate.parents:
            raise StorageError("resolved path escapes the storage root")
        return candidate

    def write(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to a sibling temp file and rename: a reader never observes a
            # partially written original, even if the process dies mid-write.
            handle, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(handle, "wb") as tmp_file:
                    tmp_file.write(data)
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())
                os.replace(tmp_path, path)
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            logger.error("storage write failed", extra={"reason": type(exc).__name__})
            raise StorageError("could not write the uploaded file") from exc

    def read(self, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError("could not read the stored file") from exc

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("could not delete the stored file") from exc
