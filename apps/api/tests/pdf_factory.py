"""Synthetic PDF builders for tests.

Every fixture is generated at runtime. No third-party or copyrighted patent
document is committed to this repository, and no test depends on one.
"""

from __future__ import annotations

import pymupdf

DEFAULT_PAGES = (
    "A claim recites a widget comprising a housing and a fastener disposed therein.",
    "The widget of claim 1, wherein the fastener comprises a threaded shaft.",
)


def build_text_pdf(pages: tuple[str, ...] = DEFAULT_PAGES, *, title: str | None = None) -> bytes:
    """A digital PDF with a real text layer, one paragraph per page."""
    document = pymupdf.open()
    try:
        for body in pages:
            page = document.new_page()
            page.insert_text((72, 96), body, fontsize=11)
        if title:
            document.set_metadata({"title": title})
        return document.tobytes()
    finally:
        document.close()


def build_pdf_without_text() -> bytes:
    """A valid PDF whose pages carry only vector graphics - the scanned-PDF stand-in."""
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.draw_rect(pymupdf.Rect(72, 72, 300, 300), color=(0, 0, 0), width=2)
        return document.tobytes()
    finally:
        document.close()


def build_encrypted_pdf(password: str = "correct horse battery staple") -> bytes:
    """A password-protected PDF, deterministic and generated on the fly."""
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 96), "Protected content that must not be readable.", fontsize=11)
        return document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw=password,
            user_pw=password,
            permissions=pymupdf.PDF_PERM_ACCESSIBILITY,
        )
    finally:
        document.close()


def build_malformed_pdf() -> bytes:
    """Correct PDF signature, unreadable body.

    Passes the magic-byte check and is rejected by the parser, which is the
    "corrupted upload" path the API contract promises to handle.
    """
    return b"%PDF-1.7\n" + bytes(range(256)) * 4


def build_truncated_pdf() -> bytes:
    """A damaged PDF that PyMuPDF repairs into a zero-page document.

    Worth its own fixture: the file opens successfully, so the parser has to
    notice the empty page set rather than trusting the open call.
    """
    return b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EO"


def build_non_pdf_bytes() -> bytes:
    """A PNG header - what "rename a screenshot to .pdf" actually uploads."""
    return b"\x89PNG\r\n\x1a\n" + b"not a pdf at all" * 8
