"""Deterministic rule-based parser for Korean patent claims.

Rules only: regular expressions over persisted page text, plus arithmetic on
character offsets. No model, no embedding, no similarity, no legal reasoning.
The same input always produces the same graph.

Two design points carry most of the correctness:

1. **Scanning uses a temporary joined buffer; provenance never does.** Pages are
   concatenated so a claim can be matched across a page break, and every buffer
   offset is mapped straight back to ``(page_number, start_char, end_char)``
   before anything leaves this module. No flattened offset is ever returned.
2. **A claim reference must carry a dependency particle.** ``제1항에 있어서`` is a
   reference; a bare number in technical prose is not. Requiring the particle is
   what keeps "탄소 1항" or "도 3" out of the dependency graph.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from claimtrace_api.db.models import ClaimType
from claimtrace_api.parsing.claims.base import (
    PAGE_SPAN_SEPARATOR,
    ClaimParserError,
    ClaimTextSpan,
    ParsedClaim,
    ParsedClaimSet,
    ParseWarning,
    SourcePage,
    WarningCode,
)

PARSER_NAME = "korean-rule-based-claims"
PARSER_VERSION = "0.1.0"

#: Full-width digits appear in some Korean filings. Translating them preserves
#: string length, so offsets are unaffected.
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_DIGIT = r"[0-9０-９]"

_OPEN_BRACKET = r"[\[\【〔<]"
_CLOSE_BRACKET = r"[\]\】〕>]"

#: 【청구항 1】 / [청구항 1] / 청구항 1 / 청구항 제1항 / 청구항 1.
_KOREAN_HEADING = re.compile(
    rf"^[ \t]*(?P<open>{_OPEN_BRACKET})?[ \t]*"
    rf"청구항[ \t]*(?:제[ \t]*)?(?P<number>{_DIGIT}{{1,4}})[ \t]*항?[ \t]*"
    rf"(?P<close>{_CLOSE_BRACKET})?[ \t]*[.:]?",
    re.MULTILINE,
)

#: Minimal English fallback, deliberately isolated: the whole line must be the
#: heading, which keeps it from matching prose that happens to say "claim 1".
_ENGLISH_HEADING = re.compile(
    rf"^[ \t]*{_OPEN_BRACKET}?[ \t]*Claim[ \t]+(?P<number>{_DIGIT}{{1,4}})[ \t]*"
    rf"{_CLOSE_BRACKET}?[ \t]*[.:]?[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)

#: Particles that turn a preceding claim number into a dependency reference.
_DEPENDENCY_PARTICLE = (
    r"(?:에[ \t]*있어서|에[ \t]*따른|에[ \t]*따라|에[ \t]*기재된|에[ \t]*기재의|에[ \t]*의한)"
)

#: Anything in this set immediately after a bare "청구항 N" means the text is a
#: reference inside a sentence, not a heading on its own. Deliberately unanchored:
#: it is applied with ``match(text, pos)``, where a leading ``^`` would only match
#: at a line start and would therefore never fire mid-line.
_REFERENCE_CONTINUATION = re.compile(
    r"[ \t]*(?:에[ \t]*(?:있어서|따른|따라|기재|의한)|또는|및|내지|과|와|,)"
)

_CLAIMS_SECTION_HEADING = re.compile(
    rf"^[ \t]*{_OPEN_BRACKET}?[ \t]*(?:특허청구범위|청구범위|청구의[ \t]*범위)[ \t]*"
    rf"{_CLOSE_BRACKET}?[ \t]*$",
    re.MULTILINE,
)

#: Sections that can only follow the claims. Used to stop the last claim's body
#: from swallowing the abstract or the drawing list.
_POST_CLAIMS_SECTION = re.compile(
    rf"^[ \t]*{_OPEN_BRACKET}?[ \t]*(?:요약서|요약|초록|도면|명세서)[ \t]*"
    rf"{_CLOSE_BRACKET}?[ \t]*$",
    re.MULTILINE,
)

_REFERENCE_RUN = (
    rf"(?:제[ \t]*{_DIGIT}{{1,4}}[ \t]*항|청구항[ \t]*{_DIGIT}{{1,4}})"
    rf"(?:[ \t]*(?:내지|또는|및|과|와|,)[ \t]*"
    rf"(?:제[ \t]*{_DIGIT}{{1,4}}[ \t]*항|청구항[ \t]*{_DIGIT}{{1,4}}))*"
    r"(?:[ \t]*중[ \t]*어느[ \t]*한[ \t]*항)?"
)

_DEPENDENCY_CLAUSE = re.compile(rf"(?P<run>{_REFERENCE_RUN})[ \t]*{_DEPENDENCY_PARTICLE}")

_RUN_TOKEN = re.compile(
    rf"(?:제[ \t]*(?P<a>{_DIGIT}{{1,4}})[ \t]*항)"
    rf"|(?:청구항[ \t]*(?P<b>{_DIGIT}{{1,4}}))"
    r"|(?P<conn>내지|또는|및|과|와|,)"
)


def _to_int(raw: str) -> int:
    return int(raw.translate(_FULLWIDTH_DIGITS))


def _rejected(heading: _Heading) -> _Heading:
    """Keep a heading as a boundary while producing no claim from it."""
    return _Heading(
        claim_number=heading.claim_number,
        start=heading.start,
        body_start=heading.body_start,
        accepted=False,
    )


@dataclass(frozen=True, slots=True)
class _PageWindow:
    """Where one page lives inside the temporary scan buffer."""

    page_number: int
    text: str
    start: int

    @property
    def end(self) -> int:
        return self.start + len(self.text)


@dataclass(frozen=True, slots=True)
class _Heading:
    claim_number: int
    #: Buffer offset where the heading itself starts (used as the previous claim's end).
    start: int
    #: Buffer offset just past the heading, where the claim body begins.
    body_start: int
    #: False for a heading that is recorded as a boundary but produces no claim -
    #: a duplicate or a malformed number. It still terminates the previous claim,
    #: otherwise that claim's span would swallow this heading and its body.
    accepted: bool = True


class _ScanBuffer:
    """Pages joined for matching, with an exact map back to page coordinates."""

    def __init__(self, pages: Sequence[SourcePage]) -> None:
        self._windows: list[_PageWindow] = []
        cursor = 0
        for index, page in enumerate(pages):
            if index > 0:
                cursor += len(PAGE_SPAN_SEPARATOR)
            self._windows.append(
                _PageWindow(page_number=page.page_number, text=page.text, start=cursor)
            )
            cursor += len(page.text)
        self.text = PAGE_SPAN_SEPARATOR.join(page.text for page in pages)

    @property
    def page_texts(self) -> dict[int, str]:
        return {window.page_number: window.text for window in self._windows}

    def spans_for(self, start: int, end: int) -> tuple[ClaimTextSpan, ...]:
        """Map a buffer range onto ordered, page-relative spans.

        Leading and trailing whitespace is excluded by moving the boundaries, not
        by editing text, so every returned offset still addresses the persisted
        page exactly. Separator positions fall between windows and are therefore
        never part of a span.
        """
        start, end = self._trim(start, end)
        if start >= end:
            return ()

        spans: list[ClaimTextSpan] = []
        for window in self._windows:
            overlap_start = max(start, window.start)
            overlap_end = min(end, window.end)
            if overlap_start >= overlap_end:
                continue
            spans.append(
                ClaimTextSpan(
                    sequence_number=len(spans),
                    page_number=window.page_number,
                    start_char=overlap_start - window.start,
                    end_char=overlap_end - window.start,
                )
            )
        return tuple(spans)

    def _trim(self, start: int, end: int) -> tuple[int, int]:
        start = max(0, start)
        end = min(len(self.text), end)
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and self.text[end - 1].isspace():
            end -= 1
        return start, end


class KoreanRuleBasedClaimParser:
    """Extracts a claim graph from Korean patent claim text."""

    @property
    def name(self) -> str:
        return PARSER_NAME

    @property
    def version(self) -> str:
        return PARSER_VERSION

    def parse(self, pages: Sequence[SourcePage]) -> ParsedClaimSet:
        if not pages:
            return ParsedClaimSet(claims=(), parser_name=self.name, parser_version=self.version)

        buffer = _ScanBuffer(pages)
        warnings: list[ParseWarning] = []

        region_start, region_end = self._claims_region(buffer.text)
        headings = self._find_headings(buffer.text, region_start, region_end, warnings)
        if not any(heading.accepted for heading in headings):
            return ParsedClaimSet(
                claims=(),
                parser_name=self.name,
                parser_version=self.version,
                warnings=tuple(warnings),
            )

        bodies = self._extract_bodies(buffer, headings, region_end, warnings)
        claims = self._resolve_dependencies(bodies, warnings)

        validate_spans(claims, pages)
        self._detect_cycles(claims, warnings)

        return ParsedClaimSet(
            claims=claims,
            parser_name=self.name,
            parser_version=self.version,
            warnings=tuple(warnings),
        )

    # -- claims region ------------------------------------------------------

    def _claims_region(self, text: str) -> tuple[int, int]:
        """Bound the claims portion of the document.

        A 【청구범위】 heading marks the start when present. The end is the first
        section that can only follow the claims; without one, the region runs to
        the end of the document.
        """
        section = _CLAIMS_SECTION_HEADING.search(text)
        start = section.end() if section else 0

        end = len(text)
        for candidate in _POST_CLAIMS_SECTION.finditer(text, start):
            end = candidate.start()
            break
        return start, end

    # -- headings -----------------------------------------------------------

    def _find_headings(
        self, text: str, region_start: int, region_end: int, warnings: list[ParseWarning]
    ) -> list[_Heading]:
        candidates = self._korean_headings(text, region_start, region_end)
        if not candidates:
            candidates = self._english_headings(text, region_start, region_end)

        headings: list[_Heading] = []
        seen: set[int] = set()
        previous_number: int | None = None

        for candidate in candidates:
            number = candidate.claim_number
            if number < 1:
                warnings.append(
                    ParseWarning(
                        code=WarningCode.MALFORMED_CLAIM_NUMBER,
                        message=f"Ignored a claim heading with a non-positive number: {number}.",
                    )
                )
                headings.append(_rejected(candidate))
                continue
            if number in seen:
                # Keeping the first occurrence rather than the last: the document
                # order is the only ordering evidence available, and silently
                # replacing a claim would change what a citation points at. The
                # rejected heading is still kept as a boundary.
                warnings.append(
                    ParseWarning(
                        code=WarningCode.DUPLICATE_CLAIM_NUMBER,
                        message=(
                            f"Claim {number} appears more than once; "
                            "only the first occurrence was kept."
                        ),
                        claim_number=number,
                    )
                )
                headings.append(_rejected(candidate))
                continue
            if previous_number is not None and number < previous_number:
                warnings.append(
                    ParseWarning(
                        code=WarningCode.CLAIMS_OUT_OF_ORDER,
                        message=(
                            f"Claim {number} appears after claim {previous_number} in the document."
                        ),
                        claim_number=number,
                    )
                )

            seen.add(number)
            previous_number = number
            headings.append(candidate)

        return headings

    def _korean_headings(self, text: str, start: int, end: int) -> list[_Heading]:
        headings: list[_Heading] = []
        for match in _KOREAN_HEADING.finditer(text, start, end):
            bracketed = bool(match.group("open") or match.group("close"))
            if not bracketed and _REFERENCE_CONTINUATION.match(text, match.end()):
                # "청구항 1에 있어서" is a dependency reference that happens to begin
                # a line, not the heading of claim 1.
                continue
            headings.append(
                _Heading(
                    claim_number=_to_int(match.group("number")),
                    start=match.start(),
                    body_start=match.end(),
                )
            )
        return headings

    def _english_headings(self, text: str, start: int, end: int) -> list[_Heading]:
        return [
            _Heading(
                claim_number=_to_int(match.group("number")),
                start=match.start(),
                body_start=match.end(),
            )
            for match in _ENGLISH_HEADING.finditer(text, start, end)
        ]

    # -- bodies and spans ---------------------------------------------------

    def _extract_bodies(
        self,
        buffer: _ScanBuffer,
        headings: list[_Heading],
        region_end: int,
        warnings: list[ParseWarning],
    ) -> list[tuple[int, tuple[ClaimTextSpan, ...], str]]:
        """Turn each heading into (claim_number, spans, reconstructed text)."""
        page_text = buffer.page_texts
        bodies: list[tuple[int, tuple[ClaimTextSpan, ...], str]] = []

        for index, heading in enumerate(headings):
            # Every heading bounds the previous claim, accepted or not.
            body_end = headings[index + 1].start if index + 1 < len(headings) else region_end
            if not heading.accepted:
                continue
            spans = buffer.spans_for(heading.body_start, body_end)
            if not spans:
                warnings.append(
                    ParseWarning(
                        code=WarningCode.EMPTY_CLAIM_BODY,
                        message=(
                            f"Claim {heading.claim_number} has no text after its heading "
                            "and was not recorded."
                        ),
                        claim_number=heading.claim_number,
                    )
                )
                continue

            text = reconstruct_text(spans, page_text)
            bodies.append((heading.claim_number, spans, text))

        return bodies

    # -- dependencies -------------------------------------------------------

    def _resolve_dependencies(
        self,
        bodies: list[tuple[int, tuple[ClaimTextSpan, ...], str]],
        warnings: list[ParseWarning],
    ) -> tuple[ParsedClaim, ...]:
        known = {number for number, _, _ in bodies}
        claims: list[ParsedClaim] = []

        for claim_number, spans, text in bodies:
            detected = self._detected_references(claim_number, text, warnings)

            resolved: list[int] = []
            for reference in detected:
                if reference == claim_number:
                    warnings.append(
                        ParseWarning(
                            code=WarningCode.SELF_DEPENDENCY,
                            message=f"Claim {claim_number} references itself; edge discarded.",
                            claim_number=claim_number,
                        )
                    )
                    continue
                if reference not in known:
                    warnings.append(
                        ParseWarning(
                            code=WarningCode.UNRESOLVED_DEPENDENCY_REFERENCE,
                            message=(
                                f"Claim {claim_number} references claim {reference}, "
                                "which is not present in this document."
                            ),
                            claim_number=claim_number,
                        )
                    )
                    continue
                resolved.append(reference)

            claims.append(
                ParsedClaim(
                    claim_number=claim_number,
                    claim_type=classify(detected_count=len(detected), resolved=resolved),
                    spans=spans,
                    text=text,
                    dependencies=tuple(sorted(set(resolved))),
                )
            )

        return tuple(sorted(claims, key=lambda claim: claim.claim_number))

    def _detected_references(
        self, claim_number: int, text: str, warnings: list[ParseWarning]
    ) -> list[int]:
        """Every claim number referenced with a dependency particle, in order."""
        references: list[int] = []
        for clause in _DEPENDENCY_CLAUSE.finditer(text):
            references.extend(self._expand_run(claim_number, clause.group("run"), warnings))

        seen: set[int] = set()
        ordered: list[int] = []
        for reference in references:
            if reference not in seen:
                seen.add(reference)
                ordered.append(reference)
        return ordered

    def _expand_run(self, claim_number: int, run: str, warnings: list[ParseWarning]) -> list[int]:
        """Read one reference run, expanding ``제1항 내지 제3항`` into 1, 2, 3."""
        numbers: list[int] = []
        pending_range = False

        for token in _RUN_TOKEN.finditer(run):
            raw = token.group("a") or token.group("b")
            if raw is None:
                pending_range = token.group("conn") == "내지"
                continue

            value = _to_int(raw)
            if value < 1:
                warnings.append(
                    ParseWarning(
                        code=WarningCode.MALFORMED_CLAIM_NUMBER,
                        message=f"Claim {claim_number} references a non-positive claim number.",
                        claim_number=claim_number,
                    )
                )
                pending_range = False
                continue

            if pending_range and numbers:
                start = numbers[-1]
                if value < start:
                    warnings.append(
                        ParseWarning(
                            code=WarningCode.MALFORMED_DEPENDENCY_RANGE,
                            message=(
                                f"Claim {claim_number} declares the range 제{start}항 내지 "
                                f"제{value}항, which runs backwards; range discarded."
                            ),
                            claim_number=claim_number,
                        )
                    )
                else:
                    numbers.extend(range(start + 1, value + 1))
            else:
                numbers.append(value)
            pending_range = False

        if pending_range:
            warnings.append(
                ParseWarning(
                    code=WarningCode.MALFORMED_DEPENDENCY_RANGE,
                    message=(
                        f"Claim {claim_number} has an incomplete 내지 range; range discarded."
                    ),
                    claim_number=claim_number,
                )
            )
        return numbers

    # -- graph checks -------------------------------------------------------

    def _detect_cycles(self, claims: tuple[ParsedClaim, ...], warnings: list[ParseWarning]) -> None:
        """Report dependency cycles. Real claims cannot contain one."""
        edges = {claim.claim_number: set(claim.dependencies) for claim in claims}
        visiting: set[int] = set()
        done: set[int] = set()
        reported: set[frozenset[int]] = set()

        def walk(node: int, path: list[int]) -> None:
            if node in done:
                return
            if node in visiting:
                cycle = path[path.index(node) :]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    rendered = " → ".join(str(number) for number in [*cycle, node])
                    warnings.append(
                        ParseWarning(
                            code=WarningCode.DEPENDENCY_CYCLE,
                            message=f"Dependency cycle detected: {rendered}.",
                            claim_number=node,
                        )
                    )
                return
            visiting.add(node)
            path.append(node)
            for neighbour in sorted(edges.get(node, ())):
                walk(neighbour, path)
            path.pop()
            visiting.discard(node)
            done.add(node)

        for claim in claims:
            walk(claim.claim_number, [])


def classify(*, detected_count: int, resolved: Sequence[int]) -> ClaimType:
    """Classify a claim from its explicit references only.

    No reference means independent. References that cannot be resolved mean
    ``unknown`` rather than a guess: the parser can see that the claim points
    somewhere, and refuses to say where.
    """
    if detected_count == 0:
        return ClaimType.INDEPENDENT
    unique = set(resolved)
    if not unique:
        return ClaimType.UNKNOWN
    if len(unique) == 1:
        return ClaimType.DEPENDENT
    return ClaimType.MULTIPLE_DEPENDENT


def reconstruct_text(spans: Iterable[ClaimTextSpan], page_text: dict[int, str]) -> str:
    """Rebuild claim text from ordered spans.

    This is the definition of a claim's text, not an approximation of it: spans
    are resolved against persisted page text and joined with
    :data:`PAGE_SPAN_SEPARATOR`.
    """
    ordered = sorted(spans, key=lambda span: span.sequence_number)
    parts: list[str] = []
    for span in ordered:
        text = page_text.get(span.page_number)
        if text is None:
            raise ClaimParserError(
                "span_out_of_bounds", f"Claim span references missing page {span.page_number}."
            )
        parts.append(span.resolve(text))
    return PAGE_SPAN_SEPARATOR.join(parts)


def validate_spans(claims: Sequence[ParsedClaim], pages: Sequence[SourcePage]) -> None:
    """Assert the structural invariants that provenance depends on.

    A violation means the extraction logic is wrong, so this raises instead of
    warning: persisting a span that does not address the text it claims to would
    corrupt every citation built on it later.
    """
    lengths = {page.page_number: len(page.text) for page in pages}
    occupied: dict[int, list[tuple[int, int, int]]] = {}

    for claim in claims:
        if not claim.spans:
            raise ClaimParserError(
                "empty_claim_spans", f"Claim {claim.claim_number} has no source spans."
            )
        for span in claim.spans:
            limit = lengths.get(span.page_number)
            if limit is None or span.end_char > limit:
                raise ClaimParserError(
                    WarningCode.SPAN_OUT_OF_BOUNDS.value,
                    (f"Claim {claim.claim_number} has a span outside page {span.page_number}."),
                )
            occupied.setdefault(span.page_number, []).append(
                (span.start_char, span.end_char, claim.claim_number)
            )

    for page_number, intervals in occupied.items():
        intervals.sort()
        for (_, previous_end, previous_claim), (start, _, current_claim) in zip(
            intervals, intervals[1:], strict=False
        ):
            if start < previous_end:
                raise ClaimParserError(
                    WarningCode.OVERLAPPING_CLAIM_SPANS.value,
                    (
                        f"Claims {previous_claim} and {current_claim} have overlapping "
                        f"spans on page {page_number}."
                    ),
                )
