"""Resolving canonical locators against the stored page text.

The quote attached to a citation is read out of ``document_pages.text`` here,
using the same half-open ``[start_char, end_char)`` coordinate the rest of the
system uses. It is never taken from a model, never reconstructed from claim
text, and never approximated.

That distinction is the difference between a citation and a quotation that
merely looks like one. A model asked to reproduce the text it cited will
paraphrase it, normalise its spacing, or quietly fix what it reads as a typo -
and the result is a quote that no longer appears in the document it claims to
come from. Reading the substring at the stored offsets makes the quote a
*consequence* of the locator rather than a second, independently fallible
assertion about it.

A locator that does not resolve is an error rather than a blank quote. It means
the stored spans and the stored page text disagree, which is a database
integrity problem the operator needs to hear about, not something to paper over
with an empty string in a response body.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import DocumentPage
from claimtrace_api.schemas.locators import SourceLocator


@dataclass(frozen=True, slots=True)
class ResolvedSpan:
    """One canonical locator together with the text it addresses."""

    locator: SourceLocator
    quote: str


class SourceResolver:
    """Reads locator-addressed substrings out of stored page text."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, locators: Iterable[SourceLocator]) -> list[ResolvedSpan]:
        """Resolve every locator, preserving the order given.

        Pages are fetched in one statement rather than one per locator: a claim
        that crosses a page break has several spans, and a grounded answer has
        several claims, so the naive version is a request-count multiplier on
        the hot path of the only endpoint that calls it.

        Raises:
            AppError: a referenced page is missing, or a span runs past the end
                of its page's stored text.
        """
        ordered = list(locators)
        if not ordered:
            return []

        keys = {(locator.document_id, locator.page_number) for locator in ordered}
        rows = (
            (
                await self._session.execute(
                    select(DocumentPage).where(
                        tuple_(DocumentPage.document_id, DocumentPage.page_number).in_(list(keys))
                    )
                )
            )
            .scalars()
            .all()
        )
        pages = {(page.document_id, page.page_number): page.text for page in rows}

        return [self._resolve_one(locator, pages) for locator in ordered]

    @staticmethod
    def _resolve_one(
        locator: SourceLocator, pages: dict[tuple[uuid.UUID, int], str]
    ) -> ResolvedSpan:
        text = pages.get((locator.document_id, locator.page_number))
        if text is None:
            raise AppError(
                ErrorCode.GROUNDED_CITATION_RESOLUTION_FAILED,
                "A cited source span refers to a page that is no longer stored.",
            )
        try:
            quote = locator.resolve(text)
        except ValueError as error:
            # SourceLocator.resolve refuses to truncate, which is the behaviour
            # that makes this reachable at all. A silently clipped quote would
            # be the exact failure this coordinate system exists to prevent.
            raise AppError(
                ErrorCode.GROUNDED_CITATION_RESOLUTION_FAILED,
                "A cited source span does not fit the stored page text.",
            ) from error
        return ResolvedSpan(locator=locator, quote=quote)
