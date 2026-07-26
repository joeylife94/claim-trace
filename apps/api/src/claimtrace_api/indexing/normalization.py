"""The normalised search representation.

Two things are built here, and the distinction between them is the whole point
of the module:

* :func:`normalize_search_text` folds text into a form that matches
  consistently. It is applied identically to indexed claims and to incoming
  queries, because a query normalised differently from the corpus simply will
  not match.
* :func:`build_search_text` assembles what actually gets indexed: a short
  deterministic header of searchable claim facts, followed by the claim body.

**Normalised text is not a coordinate system.** Folding changes string lengths -
a full-width digit becomes one ASCII digit, a run of spaces becomes one - so an
offset into normalised text addresses nothing in the source document. Provenance
is resolved through ``claim_spans`` against ``document_pages.text``, and nothing
in this module is ever allowed to become a citation. The original ``claims.text``
is never modified; every function here returns a new string.
"""

from __future__ import annotations

import re
import unicodedata

from claimtrace_api.db.models import ClaimType

#: Bumped when a change here would make previously indexed records match
#: differently. Part of the index profile identity, so old runs stay
#: distinguishable instead of being silently reinterpreted.
NORMALIZATION_VERSION = "nfkc-v1"

#: Collapses every run of Unicode whitespace - including the ideographic space
#: U+3000, which NFKC leaves alone - to a single ASCII space.
_WHITESPACE = re.compile(r"\s+", re.UNICODE)

#: Korean tokens for each structural classification. Indexed so that a query
#: written the way a patent professional writes it ("독립항") can match, and in
#: Korean rather than English because the corpus is Korean.
_CLAIM_TYPE_TOKENS: dict[ClaimType, str] = {
    ClaimType.INDEPENDENT: "독립항",
    ClaimType.DEPENDENT: "종속항",
    ClaimType.MULTIPLE_DEPENDENT: "다중종속항",
    ClaimType.UNKNOWN: "분류미상",
}


def normalize_search_text(value: str) -> str:
    """Fold text into the form used for both indexing and querying.

    Applies, in order:

    1. **NFKC**, which also maps full-width digits and Latin letters to ASCII, so
       ``１００도`` and ``100도`` become the same string.
    2. **Line-ending normalisation** - CRLF and CR to LF - before whitespace
       collapsing, so a claim reconstructed on one platform matches the same
       claim reconstructed on another.
    3. **Whitespace collapsing** to single spaces, with the ends stripped.
    4. **Case folding**, which is a no-op for Hangul but makes the small amount
       of Latin text in a Korean patent (units, chemical symbols, an English
       fallback claim) match case-insensitively.

    Punctuation is deliberately left alone. Stripping it would merge
    ``제1항`` with ``제1 항`` but would also destroy decimal points and hyphenated
    part numbers, which are exactly the tokens a patent search needs to keep.
    """
    folded = unicodedata.normalize("NFKC", value)
    folded = folded.replace("\r\n", "\n").replace("\r", "\n")
    return _WHITESPACE.sub(" ", folded).strip().casefold()


def build_search_text(
    *,
    claim_number: int,
    claim_type: ClaimType,
    dependencies: list[int],
    body: str,
) -> str:
    """Assemble the text that is embedded and tokenised for one claim.

    The header carries only facts already persisted and already deterministic -
    the claim's number, its structural classification, and the claim numbers it
    references. They are included because each is a thing people actually search
    for ("청구항 3", "독립항", "제1항을 인용하는"), and because a dependent claim's
    body alone does not say what it depends on in a form full-text search can
    tokenise.

    The body is the claim text exactly as reconstructed from its spans. It is
    normalised, not edited: no sentence is dropped, reordered, or truncated, so
    what was indexed is what the document says.
    """
    header = [f"청구항 {claim_number}", _CLAIM_TYPE_TOKENS[claim_type]]
    if dependencies:
        header.append("인용 " + " ".join(f"제{number}항" for number in sorted(dependencies)))

    return normalize_search_text(" ".join(header) + "\n" + body)


def query_terms(query: str, *, limit: int = 32) -> list[str]:
    """Split a normalised query into the terms the lexical channel ORs together.

    Whitespace splitting only - the same tokenisation PostgreSQL's ``simple``
    configuration applies, so the terms sent as parameters line up with the
    lexemes in the stored ``tsvector``. ``limit`` bounds the size of the
    generated query: without it a pathological input would build a tsquery with
    thousands of branches.
    """
    return normalize_search_text(query).split(" ")[:limit] if query.strip() else []
