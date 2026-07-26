"""Lexical retrieval over PostgreSQL.

## Why this looks the way it does

PostgreSQL has no Korean morphological analyser. The ``simple`` text-search
configuration splits on whitespace and punctuation and lowercases the result -
that is all. For Korean that has one consequence which dominates the whole
design: an agglutinative language attaches particles to nouns, so the corpus
contains ``센서에서`` and ``데이터를`` while a user types ``센서`` and ``데이터``.
Full-text search sees those as unrelated tokens and matches nothing.

So the lexical channel is deliberately two channels feeding one score:

* **Full-text search** over ``to_tsvector('simple', normalized_text)``. Precise
  when a whole word matches exactly - which in practice means numbers, units,
  Latin technical terms, and the ``제1항`` reference forms.
* **Trigram word similarity** from ``pg_trgm``. This is what recovers Korean
  compounds and particle-suffixed forms: ``word_similarity('센서', …)`` finds the
  best-matching window inside the claim rather than comparing whole strings, so a
  short query inside a long claim scores well.

Neither is a substitute for the other, and neither should be oversold. This is
substring and token matching, not morphology: it cannot resolve a synonym, and it
will match a coincidental substring. Real Korean lexical search wants an analyser
such as mecab-ko behind a custom text-search configuration, which is a database
provisioning decision rather than an application change.

## Determinism and safety

Every user-supplied value reaches the database as a bound parameter. The query
text is never concatenated into SQL, and the ``LIKE`` pattern has its wildcards
escaped, so an input like ``' OR 1=1 --`` or ``100%`` is matched as literal text.

The tsquery is built as an OR of one ``plainto_tsquery`` call per normalised
term. ``plainto_tsquery`` is used rather than ``to_tsquery`` because it treats
its argument as plain text: a term containing ``&``, ``|``, ``!`` or a bracket is
data, not tsquery syntax, and cannot raise a syntax error mid-request.

Ranking is a fixed weighted sum of three bounded components, so the same corpus
and query always produce the same order.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Float, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.indexing.normalization import normalize_search_text, query_terms
from claimtrace_api.retrieval.base import Candidate

#: Recorded on every index run. A change to tokenisation, weighting, or the
#: stored representation must bump the version, because records built under the
#: old rules would otherwise be ranked by the new ones.
LEXICAL_STRATEGY = "postgres-simple-fts-trgm"
LEXICAL_STRATEGY_VERSION = "v1"

#: Score weights. They sum to 1.0 and every component is in [0, 1], so a lexical
#: score is always in [0, 1] and comparable across queries.
#:
#: Exact containment is weighted highest because in patent text an exact phrase
#: hit is the strongest signal available - it is the query, verbatim, in the
#: claim. Full-text sits above trigram because a whole-token match is evidence,
#: whereas trigram overlap is a heuristic that can fire on coincidence.
_WEIGHT_FTS = 0.45
_WEIGHT_TRIGRAM = 0.30
_WEIGHT_PHRASE = 0.25

#: ts_rank_cd normalisation flag 32 divides by (rank + 1), mapping an unbounded
#: rank into [0, 1). Without it the full-text component would dominate or vanish
#: depending on document length.
_TS_RANK_NORMALIZATION = 32

#: Minimum ``word_similarity`` for a claim to become a trigram candidate.
#:
#: pg_trgm's default is 0.6, which is far too strict for the case this channel
#: exists to handle. Measured against this corpus, the query ``환경감시모듈``
#: scores 0.286 against the claim reciting ``환경 감시 모듈``: inserting a space
#: changes the trigrams on both sides of every word boundary, so a compound
#: written solid overlaps its spaced form much less than it looks like it should.
#: 0.6 would reject exactly the match the trigram channel was added for.
#:
#: 0.25 is set just below that measurement rather than at some round number, and
#: being permissive costs little: candidates are still ranked by the weighted
#: score below and clipped to the caller's limit, so a weak trigram hit that no
#: other signal supports lands far down the list.
_WORD_SIMILARITY_THRESHOLD = 0.25

_LIKE_ESCAPE = "\\"


class LexicalRetriever:
    """Ranks claim search records by token and trigram overlap."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def retrieve(
        self,
        *,
        query: str,
        index_run_ids: Sequence[uuid.UUID],
        limit: int,
    ) -> list[Candidate]:
        """Return up to ``limit`` lexical candidates, best first.

        ``index_run_ids`` is the set of runs the profile selector has already
        decided are compatible; this retriever never widens that.
        """
        terms = query_terms(query)
        if not terms or not index_run_ids or limit <= 0:
            return []

        normalized_query = normalize_search_text(query)

        # One plainto_tsquery per term, OR-ed together. AND semantics (what
        # plainto_tsquery gives for a whole phrase) would mean a single unmatched
        # word suppresses the entire result - fatal here, because Korean particle
        # attachment guarantees some words will not match exactly.
        tsquery_sql = " || ".join(
            f"plainto_tsquery('simple', :term_{position})" for position in range(len(terms))
        )
        parameters: dict[str, object] = {
            f"term_{position}": term for position, term in enumerate(terms)
        }
        parameters["query_text"] = normalized_query
        parameters["like_pattern"] = f"%{_escape_like(normalized_query)}%"
        parameters["limit"] = limit

        # The `<%` operator reads its threshold from a session GUC whose default
        # (0.6) is wrong for Korean compounds. Setting it explicitly, and locally
        # to this transaction, is what makes the operator usable *and* keeps the
        # result independent of whatever the connection was last used for -
        # otherwise identical queries could rank differently on different
        # connections from the pool.
        await self._session.execute(
            text("SELECT set_config('pg_trgm.word_similarity_threshold', :threshold, true)"),
            {"threshold": str(_WORD_SIMILARITY_THRESHOLD)},
        )

        statement = text(
            f"""
            WITH q AS (SELECT ({tsquery_sql}) AS tsq)
            SELECT
                r.claim_id,
                r.document_id,
                r.claim_number,
                (
                    :w_fts * ts_rank_cd(r.search_vector, q.tsq, {_TS_RANK_NORMALIZATION})
                  + :w_trgm * word_similarity(:query_text, r.normalized_text)
                  + :w_phrase * (
                        CASE WHEN r.normalized_text LIKE :like_pattern ESCAPE '{_LIKE_ESCAPE}'
                             THEN 1.0 ELSE 0.0 END
                    )
                ) AS score
            FROM claim_search_records AS r
            CROSS JOIN q
            WHERE r.index_run_id = ANY(:index_run_ids)
              AND (
                    -- Whole-token match. GIN index on search_vector.
                    r.search_vector @@ q.tsq
                    -- Verbatim substring. GIN trigram index, via LIKE '%…%'.
                 OR r.normalized_text LIKE :like_pattern ESCAPE '{_LIKE_ESCAPE}'
                    -- Approximate substring. Also the trigram index, and the
                    -- only branch that can match a Korean compound written
                    -- without the spaces the claim happens to use.
                 OR :query_text <% r.normalized_text
              )
            ORDER BY score DESC, r.claim_number ASC, r.claim_id ASC
            LIMIT :limit
            """
        ).bindparams(
            bindparam("index_run_ids", value=list(index_run_ids)),
            bindparam("w_fts", value=_WEIGHT_FTS, type_=Float),
            bindparam("w_trgm", value=_WEIGHT_TRIGRAM, type_=Float),
            bindparam("w_phrase", value=_WEIGHT_PHRASE, type_=Float),
        )

        rows = (await self._session.execute(statement, parameters)).all()

        return [
            Candidate(
                claim_id=row.claim_id,
                document_id=row.document_id,
                claim_number=row.claim_number,
                rank=position,
                score=float(row.score),
            )
            for position, row in enumerate(rows, start=1)
        ]


def _escape_like(value: str) -> str:
    """Neutralise LIKE wildcards so the query is matched as literal text.

    Without this, a claim search for ``100%`` would match every record, and one
    for ``_`` would match any single character. The backslash must be escaped
    first, or it would double-escape the escapes added after it.
    """
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
