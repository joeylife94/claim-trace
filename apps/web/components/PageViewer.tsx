"use client";

import { useState } from "react";
import type { DocumentPage } from "@/lib/documents";

/**
 * Browse extracted text one page at a time.
 *
 * The locator shown beside each page is the coordinate a future citation would
 * refine, so it is surfaced rather than hidden as an implementation detail.
 */
export function PageViewer({ pages }: { pages: DocumentPage[] }) {
  const [selected, setSelected] = useState(pages[0]?.page_number ?? 1);
  const page = pages.find((candidate) => candidate.page_number === selected) ?? pages[0];

  return (
    <section className="panel" aria-labelledby="pages-heading">
      <div className="panel-header">
        <h2 id="pages-heading">Extracted text</h2>
        <span className="status-value">
          {pages.length} page{pages.length === 1 ? "" : "s"}
        </span>
      </div>

      <nav className="page-tabs" aria-label="Pages">
        {pages.map((candidate) => (
          <button
            key={candidate.id}
            type="button"
            onClick={() => setSelected(candidate.page_number)}
            aria-current={candidate.page_number === page.page_number}
            data-active={candidate.page_number === page.page_number}
          >
            {candidate.page_number}
          </button>
        ))}
      </nav>

      <p className="meta">
        Page {page.page_number} · {page.character_count.toLocaleString()} characters ·
        locator <code>{`p${page.locator.page_number}:${page.locator.start_char}-${page.locator.end_char}`}</code>
      </p>

      <pre className="page-text">{page.text || "(this page contains no text)"}</pre>
    </section>
  );
}
