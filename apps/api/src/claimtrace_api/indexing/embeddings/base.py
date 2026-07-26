"""The embedding provider contract.

A provider turns text into vectors and describes itself. It touches no database,
no session, no HTTP, and no pgvector type: it takes ``str`` and returns tuples of
``float``. That is what makes swapping the model a new class rather than a change
to the indexing service, and what lets the whole test suite run without a model.

Queries and documents are embedded through *separate* methods on purpose. Several
current retrieval models - the E5 family among them - are trained with asymmetric
prefixes and score measurably worse when a query is embedded as though it were a
document. A single ``embed()`` would make that mistake unrepresentable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

#: A single embedding. A tuple rather than a list so a vector cannot be mutated
#: after the provider has validated it.
Vector = tuple[float, ...]


class EmbeddingError(Exception):
    """Embedding could not be performed.

    ``code`` is an :class:`~claimtrace_api.core.errors.ErrorCode` value, carried
    as a plain string so this module stays independent of the HTTP layer.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EmbeddingModelUnavailable(EmbeddingError):
    """The model could not be loaded or executed.

    A missing optional dependency, a cache miss with no network, or an
    out-of-memory failure. Retryable in principle, which is why it is distinct
    from a dimension mismatch.
    """


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns claim text and queries into dense vectors."""

    @property
    def name(self) -> str:
        """Stable provider identifier, persisted on every index run."""

    @property
    def model(self) -> str:
        """Model identifier, persisted on every index run."""

    @property
    def model_version(self) -> str:
        """Model revision. Part of the index profile identity.

        A model published under a mutable name can change underneath a cache, so
        this is recorded separately from :attr:`model` rather than assumed.
        """

    @property
    def dimension(self) -> int:
        """Width of every vector this provider returns."""

    @property
    def normalized(self) -> bool:
        """Whether returned vectors are unit length.

        When true, pgvector's cosine distance is exact and the stored vectors
        need no further scaling.
        """

    def embed_query(self, text: str) -> Vector:
        """Embed one search query.

        Raises:
            EmbeddingError: the query could not be embedded.
        """

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed claim search texts, in order.

        The returned list is positionally aligned with ``texts`` - element *i* is
        the embedding of ``texts[i]`` - because the caller pairs them back up
        with claim rows by index. An empty input returns an empty list.

        Raises:
            EmbeddingError: the batch could not be embedded.
        """
