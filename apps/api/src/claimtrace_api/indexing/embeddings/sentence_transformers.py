"""The real local embedding provider.

Runs a sentence-transformers model in-process on CPU. Nothing leaves the host:
weights are downloaded once into a cache directory and every subsequent load is
local, which is what an on-premise deployment handling confidential patent
material requires.

**Model selection.** The default is ``intfloat/multilingual-e5-small`` (384
dimensions). It was chosen over the larger multilingual options because this
phase is validating a retrieval *architecture* on a CPU-only host: it loads in
seconds rather than minutes, indexes a claim set without a GPU, and keeps the
cache small enough to be a container volume rather than a provisioning step.
BAAI/bge-m3 is stronger on most multilingual benchmarks and is a reasonable
upgrade later - it is also 1024-dimensional, which under this phase's
fixed-width column means a migration, not a settings change.

This is **not** a claim that the default is the best Korean embedding model. No
Korean retrieval benchmark was run to choose it, and the synthetic evaluation in
``evals/`` is far too small to rank models. Swapping in a different
384-dimensional model is a settings change plus a re-index, and that seam is the
actual deliverable here.

**E5 prefixes.** E5 models are trained with ``query:`` and ``passage:`` prefixes
and lose accuracy without them. They are applied automatically for models whose
name identifies them as E5, and the behaviour is visible in ``model_version`` so
an index run records how its text was prepared.

The import of ``sentence_transformers`` is deferred to first use: it pulls torch,
the dependency is an optional extra, and the API, its migrations, and the whole
test suite must run without it installed.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.indexing.embeddings.base import (
    EmbeddingError,
    EmbeddingModelUnavailable,
    Vector,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "sentence-transformers"

#: Applied to models whose name marks them as E5. Matching on the name is crude
#: but it is also exactly how the models are distributed, and getting it wrong
#: degrades quality silently rather than failing, so the choice is recorded in
#: model_version instead of being left implicit.
_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "


class SentenceTransformerEmbeddingProvider:
    """A local sentence-transformers model behind the provider protocol."""

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        cache_dir: Path,
        device: str = "cpu",
        batch_size: int = 16,
    ) -> None:
        self._model_name = model
        self._declared_dimension = dimension
        self._cache_dir = cache_dir
        self._device = device
        self._batch_size = max(1, batch_size)
        self._uses_e5_prefixes = "e5" in model.lower()

        # Loaded on first use, not at construction: building the application must
        # not block on reading half a gigabyte of weights, and a deployment that
        # never indexes anything should never pay for them. The lock keeps two
        # concurrent requests from loading two copies into memory.
        self._model: Any | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        """Identifies how text was prepared, not just which weights were used.

        The prefix scheme is part of what makes two vectors comparable, so it
        belongs in the profile identity: an index built with prefixes and one
        built without must not be searched as though they were the same.
        """
        return f"st1-{'e5' if self._uses_e5_prefixes else 'plain'}"

    @property
    def dimension(self) -> int:
        return self._declared_dimension

    @property
    def normalized(self) -> bool:
        # encode(normalize_embeddings=True) below guarantees unit length, which
        # is what makes pgvector's cosine distance exact for these vectors.
        return True

    def embed_query(self, text: str) -> Vector:
        prefixed = f"{_E5_QUERY_PREFIX}{text}" if self._uses_e5_prefixes else text
        return self._encode([prefixed])[0]

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        prepared = (
            [f"{_E5_PASSAGE_PREFIX}{text}" for text in texts] if self._uses_e5_prefixes else texts
        )
        return self._encode(list(prepared))

    # -- internals ----------------------------------------------------------

    def _load(self) -> Any:
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:  # pragma: no cover - lost the race
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingModelUnavailable(
                    ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value,
                    "The embedding model is not installed. Install the 'embeddings' "
                    "extra, or set EMBEDDING_PROVIDER=fake.",
                ) from exc

            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                model = SentenceTransformer(
                    self._model_name,
                    device=self._device,
                    cache_folder=str(self._cache_dir),
                )
            except Exception as exc:
                # The message can contain a cache path or a URL with a token, so
                # only the exception type is logged and the client sees a fixed
                # sentence.
                logger.error(
                    "embedding model could not be loaded",
                    extra={
                        "embedding_model": self._model_name,
                        "embedding_device": self._device,
                        "error_type": type(exc).__name__,
                    },
                )
                raise EmbeddingModelUnavailable(
                    ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value,
                    "The embedding model could not be loaded. Check that it has been "
                    "downloaded into the model cache and that the service has memory "
                    "available.",
                ) from exc

            # sentence-transformers 5 renamed this; support both rather than
            # pinning the library to a version for one accessor.
            read_dimension = (
                getattr(model, "get_embedding_dimension", None)
                or model.get_sentence_embedding_dimension
            )
            actual = int(read_dimension() or 0)
            if actual != self._declared_dimension:
                # Caught here rather than at insert time: pgvector would reject
                # the row with an opaque error after the run had already started.
                raise EmbeddingError(
                    ErrorCode.EMBEDDING_DIMENSION_MISMATCH.value,
                    f"The configured embedding model produces {actual}-dimensional "
                    f"vectors but this deployment stores {self._declared_dimension}. "
                    "Storing a different width needs a migration.",
                )

            logger.info(
                "embedding model loaded",
                extra={
                    "embedding_provider": PROVIDER_NAME,
                    "embedding_model": self._model_name,
                    "embedding_dimension": actual,
                    "embedding_device": self._device,
                },
            )
            self._model = model
            return model

    def _encode(self, texts: list[str]) -> list[Vector]:
        model = self._load()
        try:
            encoded = model.encode(
                texts,
                batch_size=self._batch_size,
                # Unit vectors, so cosine distance in pgvector is exact and the
                # stored values need no scaling at query time.
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            logger.error(
                "embedding failed",
                extra={
                    "embedding_model": self._model_name,
                    "batch_size": len(texts),
                    "error_type": type(exc).__name__,
                },
            )
            raise EmbeddingModelUnavailable(
                ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value,
                "The embedding model failed while encoding. The service may be out of memory.",
            ) from exc

        vectors = [tuple(float(value) for value in row) for row in encoded]
        for vector in vectors:
            if len(vector) != self._declared_dimension:  # pragma: no cover - checked at load
                raise EmbeddingError(
                    ErrorCode.EMBEDDING_DIMENSION_MISMATCH.value,
                    "The embedding model returned a vector of unexpected width.",
                )
        return vectors
