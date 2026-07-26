"""Source locators - the coordinate system for evidence citation.

Why the page, and why character offsets into *stored* page text:

* A page number is what a human reader can verify against the original PDF, and
  it survives re-chunking, re-embedding, and changes of retrieval strategy. A
  chunk index would not: chunk 7 means nothing after the chunker changes.
* The offsets index ``document_pages.text`` as persisted, not a parser buffer.
  The stored string is immutable for the life of the row, so a locator recorded
  today resolves to the same characters later. If a document is ever re-parsed
  with a different parser, that produces new page rows - and old locators are
  invalidated deliberately rather than silently pointing at shifted text.
* Anything narrower (a claim element, a chunk, a sentence) can be expressed as a
  span on a page, so later phases refine this coordinate instead of replacing it.

This phase defines and validates the locator. Chunking, which will produce them
in bulk, is Phase 3.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator


class SourceLocator(BaseModel):
    """A half-open character span ``[start_char, end_char)`` on one page."""

    document_id: uuid.UUID
    page_number: int = Field(ge=1, description="1-based page number within the document.")
    start_char: int = Field(ge=0, description="Inclusive start offset into the stored page text.")
    end_char: int = Field(ge=0, description="Exclusive end offset into the stored page text.")

    @model_validator(mode="after")
    def _check_span(self) -> SourceLocator:
        if self.end_char < self.start_char:
            raise ValueError("end_char must not be smaller than start_char")
        return self

    @property
    def length(self) -> int:
        return self.end_char - self.start_char

    def is_within(self, page_character_count: int) -> bool:
        """Whether this span fits inside a page of the given length."""
        return self.end_char <= page_character_count

    def resolve(self, page_text: str) -> str:
        """Return the referenced substring.

        Raises:
            ValueError: the span runs past the end of ``page_text``. Silently
                truncating would turn a stale citation into a plausible-looking
                quote, which is the failure mode this whole model exists to stop.
        """
        if not self.is_within(len(page_text)):
            raise ValueError("source locator span exceeds the page text length")
        return page_text[self.start_char : self.end_char]
