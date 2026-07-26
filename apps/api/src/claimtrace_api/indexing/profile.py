"""The retrieval profile: what makes two index runs comparable.

Vectors from different models are not points in the same space, and neither are
records normalised by different rules or tokenised by different lexical
strategies. Mixing them produces a ranking that looks fine and means nothing, so
compatibility is made explicit rather than assumed.

A profile is the full set of facts that must agree before two search records may
be ranked against each other. Its :attr:`IndexProfile.key` is the canonical
string form, stored on every index run and used both as the idempotency identity
and as the one equality search filters on.
"""

from __future__ import annotations

from dataclasses import dataclass

from claimtrace_api.indexing.embeddings.base import EmbeddingProvider
from claimtrace_api.indexing.normalization import NORMALIZATION_VERSION
from claimtrace_api.retrieval.lexical import LEXICAL_STRATEGY, LEXICAL_STRATEGY_VERSION

#: Separator for the canonical key. A vertical bar cannot occur in a provider
#: name, a model id, or a version string, so the join is unambiguous.
_SEPARATOR = "|"


@dataclass(frozen=True, slots=True)
class IndexProfile:
    """Everything that must match for two index runs to be searched together."""

    embedding_provider: str
    embedding_model: str
    embedding_model_version: str
    embedding_dimension: int
    vectors_normalized: bool
    normalization_version: str
    lexical_strategy: str
    lexical_strategy_version: str

    @property
    def key(self) -> str:
        """Canonical string form. Stored as ``claim_index_runs.profile_key``.

        Field order is fixed by this method and must not be rearranged: existing
        rows would stop matching newly computed keys, silently orphaning every
        index built before the change.
        """
        return _SEPARATOR.join(
            (
                self.embedding_provider,
                self.embedding_model,
                self.embedding_model_version,
                str(self.embedding_dimension),
                "normalized" if self.vectors_normalized else "raw",
                self.normalization_version,
                self.lexical_strategy,
                self.lexical_strategy_version,
            )
        )


def profile_for(provider: EmbeddingProvider) -> IndexProfile:
    """Build the active profile from the configured provider.

    The lexical strategy is a property of this codebase rather than of the
    provider, so it is read from the retriever module: there is exactly one
    lexical implementation, and its version travels with it.
    """
    return IndexProfile(
        embedding_provider=provider.name,
        embedding_model=provider.model,
        embedding_model_version=provider.model_version,
        embedding_dimension=provider.dimension,
        vectors_normalized=provider.normalized,
        normalization_version=NORMALIZATION_VERSION,
        lexical_strategy=LEXICAL_STRATEGY,
        lexical_strategy_version=LEXICAL_STRATEGY_VERSION,
    )
