"""The embedding provider boundary.

No test here downloads or executes a real model. The deterministic provider is
tested for the properties the indexing service actually depends on, and the
sentence-transformers implementation is tested only for the metadata it can
report without loading weights - which is the point of making loading lazy.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.indexing.embeddings.base import (
    EmbeddingError,
    EmbeddingModelUnavailable,
    EmbeddingProvider,
)
from claimtrace_api.indexing.embeddings.fake import FakeEmbeddingProvider
from claimtrace_api.indexing.embeddings.sentence_transformers import (
    SentenceTransformerEmbeddingProvider,
)


@pytest.fixture
def provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dimension=384)


# -- protocol conformance ---------------------------------------------------


def test_both_implementations_satisfy_the_protocol():
    """The seam is only real if both sides actually fit it."""
    assert isinstance(FakeEmbeddingProvider(), EmbeddingProvider)
    assert isinstance(
        SentenceTransformerEmbeddingProvider(
            model="intfloat/multilingual-e5-small",
            dimension=384,
            cache_dir=Path("/nonexistent"),
        ),
        EmbeddingProvider,
    )


def test_provider_identity_is_reported(provider: FakeEmbeddingProvider):
    assert provider.name == "fake"
    assert provider.model == "deterministic-hash"
    assert provider.model_version == "1"
    assert provider.dimension == 384
    assert provider.normalized is True


def test_real_provider_reports_metadata_without_loading_the_model():
    """Construction must not touch the filesystem or the network."""
    real = SentenceTransformerEmbeddingProvider(
        model="intfloat/multilingual-e5-small",
        dimension=384,
        cache_dir=Path("/nonexistent/cache"),
    )

    assert real.name == "sentence-transformers"
    assert real.model == "intfloat/multilingual-e5-small"
    assert real.dimension == 384
    assert real.normalized is True


def test_model_version_records_the_prefix_scheme():
    """An index built with E5 prefixes is not comparable with one built without."""
    e5 = SentenceTransformerEmbeddingProvider(
        model="intfloat/multilingual-e5-small", dimension=384, cache_dir=Path("/tmp")
    )
    plain = SentenceTransformerEmbeddingProvider(
        model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        dimension=384,
        cache_dir=Path("/tmp"),
    )

    assert e5.model_version != plain.model_version


# -- determinism and shape --------------------------------------------------


def test_the_same_text_always_produces_the_same_vector(provider: FakeEmbeddingProvider):
    assert provider.embed_query("센서 데이터") == provider.embed_query("센서 데이터")


def test_a_fresh_provider_produces_the_same_vectors():
    """Determinism has to survive a process boundary, not just a call."""
    text = "하우징과 체결구를 포함하는 장치"
    assert FakeEmbeddingProvider().embed_query(text) == FakeEmbeddingProvider().embed_query(text)


def test_every_vector_has_the_declared_dimension():
    for dimension in (8, 64, 384):
        vectors = FakeEmbeddingProvider(dimension=dimension).embed_documents(["가", "나"])
        assert all(len(vector) == dimension for vector in vectors)


def test_vectors_are_unit_length(provider: FakeEmbeddingProvider):
    """Cosine distance in pgvector is only exact for normalised vectors."""
    for text in ("센서", "하우징과 체결구", "제1항에 있어서 금속 재질인 장치"):
        norm = math.sqrt(sum(value * value for value in provider.embed_query(text)))
        assert norm == pytest.approx(1.0)


def test_empty_text_still_yields_a_usable_unit_vector(provider: FakeEmbeddingProvider):
    """pgvector cannot compute a cosine distance against a zero vector."""
    vector = provider.embed_query("")

    assert len(vector) == 384
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)


def test_a_zero_dimension_provider_is_rejected_at_construction():
    with pytest.raises(ValueError, match="dimension"):
        FakeEmbeddingProvider(dimension=0)


# -- batch behaviour --------------------------------------------------------


def test_batch_output_is_positionally_aligned_with_its_input(provider: FakeEmbeddingProvider):
    """The indexing service pairs vectors back to claims by index; order is load-bearing."""
    texts = ["첫번째 청구항", "두번째 청구항", "세번째 청구항"]

    batch = provider.embed_documents(texts)

    assert len(batch) == 3
    for position, text in enumerate(texts):
        assert batch[position] == provider.embed_documents([text])[0]


def test_reordering_the_input_reorders_the_output(provider: FakeEmbeddingProvider):
    forward = provider.embed_documents(["가나다", "라마바"])
    reversed_ = provider.embed_documents(["라마바", "가나다"])

    assert forward == list(reversed(reversed_))


def test_an_empty_batch_returns_an_empty_list(provider: FakeEmbeddingProvider):
    assert provider.embed_documents([]) == []


# -- semantic-ish behaviour the retrieval tests rely on ---------------------


def test_texts_sharing_tokens_are_closer_than_texts_that_share_none(
    provider: FakeEmbeddingProvider,
):
    """Not semantics - but enough structure that dense ordering tests mean something."""
    query = provider.embed_query("센서 데이터 수집")
    related = provider.embed_query("센서 데이터 수집 장치")
    unrelated = provider.embed_query("완전히 다른 내용 문서")

    assert _cosine(query, related) > _cosine(query, unrelated)


# -- failure handling -------------------------------------------------------


def test_a_provider_that_cannot_load_its_model_raises_a_typed_error():
    failing = FakeEmbeddingProvider(
        fail_with=EmbeddingModelUnavailable(
            ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value, "model missing"
        )
    )

    with pytest.raises(EmbeddingModelUnavailable) as caught:
        failing.embed_documents(["가"])

    assert caught.value.code == ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value


def test_query_embedding_fails_the_same_way_as_batch_embedding():
    failing = FakeEmbeddingProvider(
        fail_with=EmbeddingError(ErrorCode.CLAIM_INDEX_FAILED.value, "boom")
    )

    with pytest.raises(EmbeddingError):
        failing.embed_query("센서")


def test_a_missing_optional_dependency_is_reported_as_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    """Running without the 'embeddings' extra must give a clear, retryable error."""
    import builtins

    real_import = builtins.__import__

    def refuse_sentence_transformers(name: str, *args: object, **kwargs: object) -> object:
        if name == "sentence_transformers":
            raise ImportError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_sentence_transformers)

    real = SentenceTransformerEmbeddingProvider(
        model="intfloat/multilingual-e5-small", dimension=384, cache_dir=Path("/tmp")
    )

    with pytest.raises(EmbeddingModelUnavailable) as caught:
        real.embed_query("센서")

    assert caught.value.code == ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value
    assert "embeddings" in caught.value.message


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
