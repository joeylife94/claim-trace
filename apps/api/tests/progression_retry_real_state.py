"""Seed and verify the real failed-ingestion retry progression fixture."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import uuid

from sqlalchemy import func, select

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.db.models import Document, DocumentPage, DocumentStatus
from claimtrace_api.db.session import create_engine, create_session_factory
from claimtrace_api.storage.local import LocalFileStorage, build_storage_key
from tests.pdf_factory import build_text_pdf

DOCUMENT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
FILENAME = "progression-real-retry.pdf"
PAGE_TEXT = (
    "ClaimTrace deterministic retry integration source page one with recoverable evidence.",
    "ClaimTrace deterministic retry integration source page two with persisted evidence.",
)


def _fixture() -> tuple[bytes, str, str]:
    pdf = build_text_pdf(PAGE_TEXT)
    digest = hashlib.sha256(pdf).hexdigest()
    return pdf, digest, build_storage_key(digest)


async def seed() -> None:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    pdf, digest, storage_key = _fixture()
    storage = LocalFileStorage(settings.storage_root)

    try:
        storage.write(storage_key, pdf)
        async with session_factory() as session:
            existing = await session.get(Document, DOCUMENT_ID)
            if existing is not None:
                await session.delete(existing)
                await session.flush()

            document = Document(
                id=DOCUMENT_ID,
                original_filename=FILENAME,
                content_type="application/pdf",
                size_bytes=len(pdf),
                sha256=digest,
                storage_key=storage_key,
                status=DocumentStatus.FAILED,
                error_code=ErrorCode.STORAGE_FAILURE.value,
                error_message="Persisted source is ready for deterministic operator recovery.",
            )
            session.add(document)
            await session.commit()

            count = await session.scalar(select(func.count()).select_from(Document))
            assert count == 1, f"expected one seeded document, found {count}"

        print(f"Seeded real retry fixture {DOCUMENT_ID} as FAILED.")
    finally:
        await engine.dispose()


async def verify() -> None:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    storage = LocalFileStorage(settings.storage_root)

    try:
        async with session_factory() as session:
            document = await session.get(Document, DOCUMENT_ID)
            assert document is not None, "seeded document disappeared"
            assert document.status is DocumentStatus.COMPLETED
            assert document.storage_key == build_storage_key(document.sha256)
            assert document.error_code is None
            assert document.error_message is None
            assert document.page_count == 2

            count = await session.scalar(select(func.count()).select_from(Document))
            assert count == 1, f"retry created a replacement/duplicate row: count={count}"
            page_count = await session.scalar(
                select(func.count())
                .select_from(DocumentPage)
                .where(DocumentPage.document_id == DOCUMENT_ID)
            )
            assert page_count == 2, f"expected two persisted source pages, found {page_count}"

            stored_pdf = storage.read(document.storage_key)
            assert hashlib.sha256(stored_pdf).hexdigest() == document.sha256

        print("Verified same-row real retry completion with persisted original and no duplicate row.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "verify"))
    args = parser.parse_args()
    asyncio.run(seed() if args.action == "seed" else verify())


if __name__ == "__main__":
    main()
