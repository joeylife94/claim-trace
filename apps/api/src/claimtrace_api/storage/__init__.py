"""Binary storage boundary for uploaded originals."""

from claimtrace_api.storage.base import FileStorage, StorageError
from claimtrace_api.storage.local import LocalFileStorage

__all__ = ["FileStorage", "LocalFileStorage", "StorageError"]
