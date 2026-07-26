"""A deterministic embedding provider that downloads nothing.

This is not a mock. It is a real implementation of the protocol whose vectors
happen to be derived from a hash rather than from a neural network, and it is
what the entire test suite - unit and integration - runs against. Two properties
make it useful rather than merely fast:

* **Deterministic.** The same text always produces the same vector, in this
  process and the next, so a retrieval test can assert an exact ordering.
* **Lexically sensitive.** Vectors are built from token hashes, so texts sharing
  tokens land closer together than texts that share none. Dense retrieval tests
  therefore exercise real ordering behaviour instead of noise.

What it is *not* is semantic. It cannot match a paraphrase, and no evaluation
number produced with it says anything about retrieval quality. That is the job
of the real provider.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.indexing.embeddings.base import EmbeddingError, Vector
from claimtrace_api.indexing.normalization import normalize_search_text

PROVIDER_NAME = "fake"


class FakeEmbeddingProvider:
    """Hash-based embeddings with the same contract as the real provider."""

    def __init__(
        self,
        *,
        dimension: int = 384,
        model: str = "deterministic-hash",
        model_version: str = "1",
        fail_with: EmbeddingError | None = None,
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._dimension = dimension
        self._model = model
        self._model_version = model_version
        # Lets a test drive the failure paths - model load failure, mid-batch
        # error - through the same object the success paths use.
        self._fail_with = fail_with

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def model(self) -> str:
        return self._model

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def normalized(self) -> bool:
        return True

    def embed_query(self, text: str) -> Vector:
        self._guard()
        return self._vector(text)

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        self._guard()
        return [self._vector(text) for text in texts]

    # -- internals ----------------------------------------------------------

    def _guard(self) -> None:
        if self._fail_with is not None:
            raise self._fail_with

    def _vector(self, text: str) -> Vector:
        """Sum one unit-ish contribution per token, then normalise.

        Each token is hashed to a fixed pseudo-random direction; a text's vector
        is the sum of its tokens' directions. Shared tokens therefore raise the
        cosine similarity between two texts, which is the property the retrieval
        tests rely on.
        """
        components = [0.0] * self._dimension
        tokens = normalize_search_text(text).split(" ")

        for token in tokens:
            if not token:
                continue
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(self._dimension):
                # Two bytes per component, walked cyclically: enough entropy to
                # keep unrelated tokens near-orthogonal at any usable width.
                offset = (index * 2) % len(digest)
                raw = (digest[offset] << 8) | digest[(offset + 1) % len(digest)]
                # Fold the digest position in so the same byte pair does not
                # repeat identically once the walk wraps around.
                mixed = (raw * (index + 1)) % 65_536
                components[index] += (mixed / 32_767.5) - 1.0

        norm = math.sqrt(sum(value * value for value in components))
        if norm == 0.0:
            # Empty or punctuation-only text. A zero vector has no direction and
            # pgvector cannot compute a cosine distance against it, so a fixed
            # unit vector is used instead of silently storing zeros.
            if self._dimension == 0:  # pragma: no cover - rejected in __init__
                raise EmbeddingError(ErrorCode.INTERNAL_ERROR.value, "dimension is zero")
            components[0] = 1.0
            return tuple(components)

        return tuple(value / norm for value in components)
