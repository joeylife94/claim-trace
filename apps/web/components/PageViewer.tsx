"use client";

import type { DocumentPage } from "@/lib/documents";

export type PageHighlight = {
  page_number: number;
  start_char: number;
  end_char: number;
};

/**
 * Browse extracted text one page at a time.
 *
 * Page selection is controlled by the parent so that opening a claim's source
 * span can drive it. The locator shown beside each page is the coordinate a
 * citation refines, so it is surfaced rather than hidden.
 */
export function PageViewer({
  pages,
  selectedPage,
  onSelectPage,
  highlight = null,
}: {
  pages: DocumentPage[];
  selectedPage: number;
  onSelectPage: (pageNumber: number) => void;
  highlight?: PageHighlight | null;
}) {
  const page = pages.find((candidate) => candidate.page_number === selectedPage) ?? pages[0];
  if (!page) return null;

  const activeHighlight =
    highlight && highlight.page_number === page.page_number ? highlight : null;

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
            onClick={() => onSelectPage(candidate.page_number)}
            aria-current={candidate.page_number === page.page_number}
            data-active={candidate.page_number === page.page_number}
          >
            {candidate.page_number}
          </button>
        ))}
      </nav>

      <p className="meta">
        Page {page.page_number} · {page.character_count.toLocaleString()} characters ·{" "}
        {activeHighlight ? (
          <>
            showing{" "}
            <code>
              {`p${activeHighlight.page_number}:${activeHighlight.start_char}-${activeHighlight.end_char}`}
            </code>
          </>
        ) : (
          <>
            locator{" "}
            <code>{`p${page.locator.page_number}:${page.locator.start_char}-${page.locator.end_char}`}</code>
          </>
        )}
      </p>

      <pre className="page-text">
        {page.text ? (
          <HighlightedText text={page.text} highlight={activeHighlight} />
        ) : (
          "(this page contains no text)"
        )}
      </pre>
    </section>
  );
}

function HighlightedText({
  text,
  highlight,
}: {
  text: string;
  highlight: PageHighlight | null;
}) {
  // Offsets are half-open [start, end) into exactly this stored page text, so
  // slicing here is the same operation the API's locator describes.
  if (
    !highlight ||
    highlight.start_char >= highlight.end_char ||
    highlight.end_char > text.length
  ) {
    return <>{text}</>;
  }

  return (
    <>
      {text.slice(0, highlight.start_char)}
      <mark
        className="span-highlight"
        ref={(node) => node?.scrollIntoView({ block: "center" })}
      >
        {text.slice(highlight.start_char, highlight.end_char)}
      </mark>
      {text.slice(highlight.end_char)}
    </>
  );
}
