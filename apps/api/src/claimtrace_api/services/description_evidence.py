"""D4 description-evidence derivation, indexing, and retrieval.

The invariant is deliberately narrow: description evidence is always a span of
persisted ``document_pages.text``. Normalised/indexed text is a derived search
projection and is never used as a citation coordinate.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import EMBEDDING_DIMENSION, Document, DocumentPage, DocumentStatus
from claimtrace_api.indexing.embeddings.base import EmbeddingProvider
from claimtrace_api.indexing.normalization import normalize_search_text, query_terms
from claimtrace_api.indexing.profile import IndexProfile, profile_for
from claimtrace_api.retrieval.base import RetrievalMode

SEGMENTER_NAME = "korean-patent-description-sections"
SEGMENTER_VERSION = "v1"
EVIDENCE_KIND = "description"

_START_HEADINGS = (
    "발명의설명",
    "발명의상세한설명",
    "기술분야",
    "배경기술",
    "발명의내용",
    "도면의간단한설명",
    "발명을실시하기위한구체적인내용",
)
_STOP_HEADINGS = ("특허청구의범위", "청구범위", "청구항")
_MAX_SEGMENT_CHARS = 700
_MIN_SEGMENT_CHARS = 40


@dataclass(frozen=True, slots=True)
class DescriptionSegment:
    id: uuid.UUID
    document_id: uuid.UUID
    segment_index: int
    section_heading: str | None
    page_number: int
    start_char: int
    end_char: int
    text: str


@dataclass(frozen=True, slots=True)
class DescriptionDerivationOutcome:
    run_id: uuid.UUID
    status: str
    segments: list[DescriptionSegment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created: bool = False


@dataclass(frozen=True, slots=True)
class DescriptionIndexOutcome:
    status: str
    profile: IndexProfile
    indexed_segment_count: int
    created: bool
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DescriptionSearchResult:
    segment: DescriptionSegment
    document_filename: str
    fused_rank: int
    fused_score: float
    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None


@dataclass(frozen=True, slots=True)
class DescriptionSearchOutcome:
    mode: RetrievalMode
    profile: IndexProfile
    dense_candidate_count: int
    lexical_candidate_count: int
    results: list[DescriptionSearchResult] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Candidate:
    segment_id: uuid.UUID
    document_id: uuid.UUID
    segment_index: int
    rank: int
    score: float


@dataclass(frozen=True, slots=True)
class _Page:
    page_number: int
    text: str


class DescriptionEvidenceService:
    """Coordinates source-faithful description derivation and bounded retrieval."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        provider: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings

    @property
    def profile(self) -> IndexProfile:
        return profile_for(self._provider)

    async def derive(self, document_id: uuid.UUID) -> DescriptionDerivationOutcome:
        document = await self._session.get(Document, document_id)
        if document is None:
            raise AppError(ErrorCode.DOCUMENT_NOT_FOUND, "Document not found.")
        if document.status is not DocumentStatus.COMPLETED:
            raise AppError(
                ErrorCode.DOCUMENT_NOT_COMPLETED,
                "Description derivation needs a completed text-based document.",
            )

        existing = await self._existing_run(document_id)
        if existing is not None:
            return await self._hydrate_run(existing.id, existing.status, existing.warnings, False)

        pages = list(
            (
                await self._session.execute(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == document_id)
                    .order_by(DocumentPage.page_number)
                )
            )
            .scalars()
            .all()
        )
        source_pages = [_Page(page_number=page.page_number, text=page.text) for page in pages]
        status, drafts, warnings = derive_description_segments(source_pages)

        run_id = uuid.uuid4()
        await self._session.execute(
            text(
                """
                INSERT INTO description_derivation_runs
                    (id, document_id, status, segmenter_name, segmenter_version,
                     segment_count, warnings)
                VALUES
                    (:id, :document_id, :status, :segmenter_name, :segmenter_version,
                     :segment_count, CAST(:warnings AS jsonb))
                """
            ),
            {
                "id": run_id,
                "document_id": document_id,
                "status": status,
                "segmenter_name": SEGMENTER_NAME,
                "segmenter_version": SEGMENTER_VERSION,
                "segment_count": len(drafts),
                "warnings": _json_array(warnings),
            },
        )

        segments: list[DescriptionSegment] = []
        for draft in drafts:
            segment = DescriptionSegment(
                id=uuid.uuid4(),
                document_id=document_id,
                segment_index=draft.segment_index,
                section_heading=draft.section_heading,
                page_number=draft.page_number,
                start_char=draft.start_char,
                end_char=draft.end_char,
                text=draft.text,
            )
            await self._session.execute(
                text(
                    """
                    INSERT INTO description_segments
                        (id, run_id, document_id, segment_index, section_heading,
                         page_number, start_char, end_char, text, evidence_kind)
                    VALUES
                        (:id, :run_id, :document_id, :segment_index, :section_heading,
                         :page_number, :start_char, :end_char, :text, :evidence_kind)
                    """
                ),
                {
                    "id": segment.id,
                    "run_id": run_id,
                    "document_id": document_id,
                    "segment_index": segment.segment_index,
                    "section_heading": segment.section_heading,
                    "page_number": segment.page_number,
                    "start_char": segment.start_char,
                    "end_char": segment.end_char,
                    "text": segment.text,
                    "evidence_kind": EVIDENCE_KIND,
                },
            )
            segments.append(segment)

        await self._session.commit()
        return DescriptionDerivationOutcome(
            run_id=run_id,
            status=status,
            segments=segments,
            warnings=warnings,
            created=True,
        )

    async def index(self, document_id: uuid.UUID) -> DescriptionIndexOutcome:
        derived = await self.derive(document_id)
        profile = self.profile
        if derived.status != "completed":
            return DescriptionIndexOutcome(
                status="unsupported",
                profile=profile,
                indexed_segment_count=0,
                created=False,
                warnings=derived.warnings,
            )
        if self._provider.dimension != EMBEDDING_DIMENSION:
            raise AppError(
                ErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                f"The configured embedding provider produces {self._provider.dimension}-"
                f"dimensional vectors but this deployment stores {EMBEDDING_DIMENSION}.",
            )

        existing_count = int(
            (
                await self._session.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM description_search_records
                        WHERE document_id = :document_id AND profile_key = :profile_key
                        """
                    ),
                    {"document_id": document_id, "profile_key": profile.key},
                )
            ).scalar_one()
        )
        if existing_count == len(derived.segments):
            return DescriptionIndexOutcome(
                status="completed",
                profile=profile,
                indexed_segment_count=existing_count,
                created=False,
            )

        normalized = [normalize_search_text(segment.text) for segment in derived.segments]
        vectors = self._provider.embed_documents(normalized)
        if len(vectors) != len(derived.segments):
            raise AppError(
                ErrorCode.CLAIM_INDEX_FAILED,
                "The embedding provider returned a different number of vectors than segments.",
            )

        await self._session.execute(
            text(
                """
                DELETE FROM description_search_records
                WHERE document_id = :document_id AND profile_key = :profile_key
                """
            ),
            {"document_id": document_id, "profile_key": profile.key},
        )

        insert = text(
            """
            INSERT INTO description_search_records
                (id, segment_id, document_id, segment_index, profile_key,
                 normalized_text, search_vector, embedding)
            VALUES
                (:id, :segment_id, :document_id, :segment_index, :profile_key,
                 :normalized_text, to_tsvector('simple', :normalized_text), :embedding)
            """
        ).bindparams(bindparam("embedding", type_=Vector(EMBEDDING_DIMENSION)))
        for segment, search_text, vector in zip(
            derived.segments, normalized, vectors, strict=True
        ):
            await self._session.execute(
                insert,
                {
                    "id": uuid.uuid4(),
                    "segment_id": segment.id,
                    "document_id": document_id,
                    "segment_index": segment.segment_index,
                    "profile_key": profile.key,
                    "normalized_text": search_text,
                    "embedding": list(vector),
                },
            )
        await self._session.commit()
        return DescriptionIndexOutcome(
            status="completed",
            profile=profile,
            indexed_segment_count=len(derived.segments),
            created=True,
        )

    async def search(
        self,
        *,
        query: str,
        mode: RetrievalMode,
        document_ids: Sequence[uuid.UUID] | None,
        top_k: int,
        dense_candidate_count: int,
        lexical_candidate_count: int,
    ) -> DescriptionSearchOutcome:
        profile = self.profile
        dense: list[_Candidate] = []
        lexical: list[_Candidate] = []
        if mode in (RetrievalMode.HYBRID, RetrievalMode.DENSE):
            dense = await self._dense(
                query=query,
                profile_key=profile.key,
                document_ids=document_ids,
                limit=dense_candidate_count,
            )
        if mode in (RetrievalMode.HYBRID, RetrievalMode.LEXICAL):
            lexical = await self._lexical(
                query=query,
                profile_key=profile.key,
                document_ids=document_ids,
                limit=lexical_candidate_count,
            )

        fused = _rrf(dense=dense, lexical=lexical, k=self._settings.rrf_k, top_k=top_k)
        results = await self._hydrate_search(fused)
        return DescriptionSearchOutcome(
            mode=mode,
            profile=profile,
            dense_candidate_count=len(dense),
            lexical_candidate_count=len(lexical),
            results=results,
        )

    async def _existing_run(self, document_id: uuid.UUID) -> object | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT id, status, warnings
                    FROM description_derivation_runs
                    WHERE document_id = :document_id
                      AND segmenter_name = :segmenter_name
                      AND segmenter_version = :segmenter_version
                    LIMIT 1
                    """
                ),
                {
                    "document_id": document_id,
                    "segmenter_name": SEGMENTER_NAME,
                    "segmenter_version": SEGMENTER_VERSION,
                },
            )
        ).first()
        return row

    async def _hydrate_run(
        self, run_id: uuid.UUID, status: str, warnings: object, created: bool
    ) -> DescriptionDerivationOutcome:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, document_id, segment_index, section_heading,
                           page_number, start_char, end_char, text
                    FROM description_segments
                    WHERE run_id = :run_id
                    ORDER BY segment_index
                    """
                ),
                {"run_id": run_id},
            )
        ).all()
        segments = [
            DescriptionSegment(
                id=row.id,
                document_id=row.document_id,
                segment_index=row.segment_index,
                section_heading=row.section_heading,
                page_number=row.page_number,
                start_char=row.start_char,
                end_char=row.end_char,
                text=row.text,
            )
            for row in rows
        ]
        warning_list = list(warnings) if isinstance(warnings, list) else []
        return DescriptionDerivationOutcome(
            run_id=run_id,
            status=status,
            segments=segments,
            warnings=warning_list,
            created=created,
        )

    async def _dense(
        self,
        *,
        query: str,
        profile_key: str,
        document_ids: Sequence[uuid.UUID] | None,
        limit: int,
    ) -> list[_Candidate]:
        if limit <= 0:
            return []
        query_vector = self._provider.embed_query(query)
        statement = text(
            """
            SELECT segment_id, document_id, segment_index, distance
            FROM (
                SELECT segment_id, document_id, segment_index,
                       embedding <=> :query_vector AS distance
                FROM description_search_records
                WHERE profile_key = :profile_key
                  AND (:scoped = false OR document_id = ANY(:document_ids))
                ORDER BY embedding <=> :query_vector
                LIMIT :limit
            ) AS nearest
            ORDER BY distance ASC, segment_index ASC, segment_id ASC
            """
        ).bindparams(
            bindparam("query_vector", value=list(query_vector), type_=Vector(EMBEDDING_DIMENSION)),
            bindparam("document_ids", value=list(document_ids) if document_ids else [uuid.UUID(int=0)]),
            bindparam("limit", value=limit),
        )
        rows = (
            await self._session.execute(
                statement,
                {"profile_key": profile_key, "scoped": bool(document_ids)},
            )
        ).all()
        return [
            _Candidate(
                segment_id=row.segment_id,
                document_id=row.document_id,
                segment_index=row.segment_index,
                rank=rank,
                score=1.0 - float(row.distance),
            )
            for rank, row in enumerate(rows, start=1)
        ]

    async def _lexical(
        self,
        *,
        query: str,
        profile_key: str,
        document_ids: Sequence[uuid.UUID] | None,
        limit: int,
    ) -> list[_Candidate]:
        terms = query_terms(query)
        if not terms or limit <= 0:
            return []
        normalized_query = normalize_search_text(query)
        tsquery_sql = " || ".join(
            f"plainto_tsquery('simple', :term_{position})" for position in range(len(terms))
        )
        parameters: dict[str, object] = {
            f"term_{position}": term for position, term in enumerate(terms)
        }
        parameters.update(
            {
                "query_text": normalized_query,
                "like_pattern": f"%{_escape_like(normalized_query)}%",
                "profile_key": profile_key,
                "scoped": bool(document_ids),
            }
        )
        statement = text(
            f"""
            WITH q AS (SELECT ({tsquery_sql}) AS tsq)
            SELECT r.segment_id, r.document_id, r.segment_index,
                   (0.55 * ts_rank_cd(r.search_vector, q.tsq, 32)
                    + 0.30 * word_similarity(:query_text, r.normalized_text)
                    + 0.15 * CASE
                        WHEN r.normalized_text LIKE :like_pattern ESCAPE '\\' THEN 1.0
                        ELSE 0.0
                      END) AS score
            FROM description_search_records AS r
            CROSS JOIN q
            WHERE r.profile_key = :profile_key
              AND (:scoped = false OR r.document_id = ANY(:document_ids))
              AND (
                    r.search_vector @@ q.tsq
                 OR r.normalized_text LIKE :like_pattern ESCAPE '\\'
                 OR :query_text <% r.normalized_text
              )
            ORDER BY score DESC, r.segment_index ASC, r.segment_id ASC
            LIMIT :limit
            """
        ).bindparams(
            bindparam("document_ids", value=list(document_ids) if document_ids else [uuid.UUID(int=0)]),
            bindparam("limit", value=limit),
        )
        await self._session.execute(
            text("SELECT set_config('pg_trgm.word_similarity_threshold', '0.25', true)")
        )
        rows = (await self._session.execute(statement, parameters)).all()
        return [
            _Candidate(
                segment_id=row.segment_id,
                document_id=row.document_id,
                segment_index=row.segment_index,
                rank=rank,
                score=float(row.score),
            )
            for rank, row in enumerate(rows, start=1)
        ]

    async def _hydrate_search(
        self, fused: list[tuple[uuid.UUID, int, float, _Candidate | None, _Candidate | None]]
    ) -> list[DescriptionSearchResult]:
        if not fused:
            return []
        ids = [item[0] for item in fused]
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT s.id, s.document_id, s.segment_index, s.section_heading,
                           s.page_number, s.start_char, s.end_char, s.text,
                           d.original_filename
                    FROM description_segments AS s
                    JOIN documents AS d ON d.id = s.document_id
                    WHERE s.id = ANY(:segment_ids)
                    """
                ).bindparams(bindparam("segment_ids", value=ids))
            )
        ).all()
        by_id = {row.id: row for row in rows}
        results: list[DescriptionSearchResult] = []
        for segment_id, fused_rank, fused_score, dense, lexical in fused:
            row = by_id.get(segment_id)
            if row is None:
                continue
            segment = DescriptionSegment(
                id=row.id,
                document_id=row.document_id,
                segment_index=row.segment_index,
                section_heading=row.section_heading,
                page_number=row.page_number,
                start_char=row.start_char,
                end_char=row.end_char,
                text=row.text,
            )
            results.append(
                DescriptionSearchResult(
                    segment=segment,
                    document_filename=row.original_filename,
                    fused_rank=fused_rank,
                    fused_score=fused_score,
                    dense_rank=dense.rank if dense else None,
                    dense_score=dense.score if dense else None,
                    lexical_rank=lexical.rank if lexical else None,
                    lexical_score=lexical.score if lexical else None,
                )
            )
        return results


@dataclass(frozen=True, slots=True)
class _DraftSegment:
    segment_index: int
    section_heading: str | None
    page_number: int
    start_char: int
    end_char: int
    text: str


def derive_description_segments(
    pages: Sequence[_Page],
) -> tuple[str, list[_DraftSegment], list[str]]:
    """Derive deterministic page-local description spans from persisted page text.

    A recognised Korean description heading is mandatory. Falling back to
    "everything that is not a claim" would silently turn front matter or an
    ambiguous document structure into accepted description evidence, so missing
    structure is an explicit ``unsupported`` outcome.
    """
    drafts: list[_DraftSegment] = []
    active = False
    saw_description_heading = False
    section_heading: str | None = None

    for page in pages:
        region_start = 0 if active else None
        for line in re.finditer(r"[^\n]*(?:\n|$)", page.text):
            raw = line.group(0).rstrip("\n")
            heading = _heading_kind(raw)
            if heading is None:
                continue
            kind, label = heading
            if kind == "stop":
                if not active:
                    continue
                if region_start is not None:
                    _append_region(
                        drafts,
                        page,
                        region_start,
                        line.start(),
                        section_heading,
                    )
                active = False
                return _finalize_derivation(drafts, saw_description_heading)

            saw_description_heading = True
            if active and region_start is not None:
                _append_region(
                    drafts,
                    page,
                    region_start,
                    line.start(),
                    section_heading,
                )
            active = True
            section_heading = label
            region_start = line.end()

        if active and region_start is not None:
            _append_region(drafts, page, region_start, len(page.text), section_heading)

    return _finalize_derivation(drafts, saw_description_heading)


def _append_region(
    drafts: list[_DraftSegment],
    page: _Page,
    start: int,
    end: int,
    section_heading: str | None,
) -> None:
    for chunk_start, chunk_end in _chunk_source_region(page.text, start, end):
        drafts.append(
            _DraftSegment(
                segment_index=len(drafts),
                section_heading=section_heading,
                page_number=page.page_number,
                start_char=chunk_start,
                end_char=chunk_end,
                text=page.text[chunk_start:chunk_end],
            )
        )


def _chunk_source_region(text_value: str, start: int, end: int) -> list[tuple[int, int]]:
    chunks: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        while cursor < end and text_value[cursor].isspace():
            cursor += 1
        if cursor >= end:
            break
        ceiling = min(cursor + _MAX_SEGMENT_CHARS, end)
        boundary = ceiling
        if ceiling < end:
            window_start = min(ceiling, cursor + _MIN_SEGMENT_CHARS)
            candidates = [
                text_value.rfind("\n\n", window_start, ceiling),
                text_value.rfind("\n", window_start, ceiling),
                text_value.rfind("다. ", window_start, ceiling),
                text_value.rfind(". ", window_start, ceiling),
                text_value.rfind(" ", window_start, ceiling),
            ]
            usable = [candidate for candidate in candidates if candidate >= window_start]
            if usable:
                boundary = max(usable) + 1
        while boundary > cursor and text_value[boundary - 1].isspace():
            boundary -= 1
        if boundary - cursor >= _MIN_SEGMENT_CHARS:
            chunks.append((cursor, boundary))
        cursor = max(boundary, cursor + 1)
    return chunks


def _heading_kind(value: str) -> tuple[str, str] | None:
    compact = re.sub(r"[\s\[\]【】<>〈〉()（）0-9.·-]", "", value)
    if not compact or len(compact) > 40:
        return None
    for heading in _STOP_HEADINGS:
        if compact == heading or compact.startswith(heading):
            return "stop", heading
    for heading in _START_HEADINGS:
        if compact == heading or compact.startswith(heading):
            return "start", heading
    return None


def _finalize_derivation(
    drafts: list[_DraftSegment], saw_description_heading: bool
) -> tuple[str, list[_DraftSegment], list[str]]:
    if drafts:
        return "completed", drafts, []
    if not saw_description_heading:
        return "unsupported", [], ["description_heading_not_found"]
    return "unsupported", [], ["description_heading_found_but_no_substantive_text"]


def _rrf(
    *,
    dense: list[_Candidate],
    lexical: list[_Candidate],
    k: int,
    top_k: int,
) -> list[tuple[uuid.UUID, int, float, _Candidate | None, _Candidate | None]]:
    dense_by_id = {item.segment_id: item for item in dense}
    lexical_by_id = {item.segment_id: item for item in lexical}
    ids = set(dense_by_id) | set(lexical_by_id)
    ranked = []
    for segment_id in ids:
        dense_item = dense_by_id.get(segment_id)
        lexical_item = lexical_by_id.get(segment_id)
        score = 0.0
        if dense_item is not None:
            score += 1.0 / (k + dense_item.rank)
        if lexical_item is not None:
            score += 1.0 / (k + lexical_item.rank)
        segment_index = (
            dense_item.segment_index if dense_item is not None else lexical_item.segment_index
        )
        ranked.append((segment_id, score, segment_index, dense_item, lexical_item))
    ranked.sort(key=lambda item: (-item[1], item[2], str(item[0])))
    return [
        (segment_id, rank, score, dense_item, lexical_item)
        for rank, (segment_id, score, _, dense_item, lexical_item) in enumerate(
            ranked[:top_k], start=1
        )
    ]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _json_array(values: list[str]) -> str:
    escaped = [value.replace("\\", "\\\\").replace('"', '\\"') for value in values]
    return "[" + ",".join(f'"{value}"' for value in escaped) + "]"