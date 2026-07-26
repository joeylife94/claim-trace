"""Synthetic Korean claim text and PDFs for tests.

Every fixture is generated at runtime. No third-party or copyrighted patent
document is committed to this repository, and no test depends on one.
"""

from __future__ import annotations

import uuid

import pymupdf

from claimtrace_api.parsing.claims.base import SourcePage

#: A small claim set covering the four classifications this phase recognises.
KOREAN_CLAIM_SET = """【청구범위】
【청구항 1】
하우징과, 상기 하우징의 내부에 배치되는 체결구를 포함하는 위젯 장치.
【청구항 2】
제1항에 있어서, 상기 체결구는 나사산을 갖는 샤프트를 포함하는 위젯 장치.
【청구항 3】
제1항 또는 제2항에 있어서, 상기 하우징은 금속 재질인 위젯 장치.
【청구항 4】
제1항 내지 제3항 중 어느 한 항에 있어서, 동작 온도가 100도인 위젯 장치.
"""

NON_PATENT_TEXT = """회사 내부 회람문
본 문서는 특허 문서가 아니며 청구 구조를 포함하지 않습니다.
2026년 1분기 실적은 전년 대비 12퍼센트 증가하였습니다.
자세한 내용은 3페이지의 표를 참고하십시오.
"""


def pages(*texts: str, document_id: uuid.UUID | None = None) -> list[SourcePage]:
    """Build ordered SourcePage records from raw page strings."""
    identifier = document_id or uuid.uuid4()
    return [
        SourcePage(document_id=identifier, page_number=index + 1, text=text)
        for index, text in enumerate(texts)
    ]


def build_korean_claims_pdf(page_texts: tuple[str, ...] = (KOREAN_CLAIM_SET,)) -> bytes:
    """A digital PDF whose text layer contains Korean claims.

    A CJK-capable font is embedded so the extracted text round-trips; without one
    PyMuPDF would write the Hangul as unmapped glyphs.
    """
    document = pymupdf.open()
    try:
        for body in page_texts:
            page = document.new_page()
            writer = pymupdf.TextWriter(page.rect)
            font = pymupdf.Font("cjk")
            y = 72.0
            for line in body.splitlines():
                if line.strip():
                    writer.append((72, y), line, font=font, fontsize=10)
                y += 14
            writer.write_text(page)
        return document.tobytes()
    finally:
        document.close()
