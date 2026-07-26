"""The storage contract.

Storage is addressed by an opaque *storage key* that the application generates.
A key never derives from a client-supplied filename, and it never leaves the
server: the API exposes document ids, not paths.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

#: Keys are restricted to a shallow, printable, relative form. Anything else -
#: absolute paths, ``..`` segments, backslashes, NUL bytes, drive letters - is
#: rejected before it can reach a filesystem call.
STORAGE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*$")


class StorageError(Exception):
    """The backing store could not satisfy the request."""


def validate_storage_key(key: str) -> str:
    """Return ``key`` if it is a safe relative key, otherwise raise.

    Defence in depth: keys are generated internally, so a violation means a bug
    or an injection attempt rather than ordinary bad input.
    """
    if not key or len(key) > 512:
        raise StorageError("storage key has an invalid length")
    if not STORAGE_KEY_PATTERN.fullmatch(key):
        raise StorageError("storage key contains disallowed characters")
    if any(segment in {".", ".."} for segment in key.split("/")):
        raise StorageError("storage key must not contain relative path segments")
    return key


@runtime_checkable
class FileStorage(Protocol):
    """Content storage for uploaded originals."""

    def write(self, key: str, data: bytes) -> None:
        """Persist ``data`` under ``key``, replacing any existing object atomically."""

    def read(self, key: str) -> bytes:
        """Return the stored bytes.

        Raises:
            StorageError: the object is missing or unreadable.
        """

    def exists(self, key: str) -> bool:
        """Whether an object is stored under ``key``."""

    def delete(self, key: str) -> None:
        """Remove the object. Missing objects are not an error."""
