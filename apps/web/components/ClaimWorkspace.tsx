"use client";

import { useState } from "react";
import { ClaimsPanel } from "@/components/ClaimsPanel";
import { PageViewer, type PageHighlight } from "@/components/PageViewer";
import type { ClaimSet, ClaimSpan } from "@/lib/claims";
import type { DocumentPage } from "@/lib/documents";

/**
 * Owns the one piece of shared state between the claim list and the page text:
 * which source span is being looked at. Selecting a span moves the viewer to
 * that page and highlights the exact [start_char, end_char) range.
 */
export function ClaimWorkspace({
  documentId,
  documentCompleted,
  pages,
  claimSet,
  initialHighlight = null,
}: {
  documentId: string;
  documentCompleted: boolean;
  pages: DocumentPage[];
  claimSet: ClaimSet | null;
  /**
   * A span arriving from outside the page - a search result's source link. It
   * seeds the viewer so the deep link lands on the right page with the right
   * range already highlighted, and is then owned by the same state as a span
   * clicked in the claim list.
   */
  initialHighlight?: PageHighlight | null;
}) {
  const [activeSpan, setActiveSpan] = useState<PageHighlight | null>(initialHighlight);
  const [selectedPage, setSelectedPage] = useState(
    initialHighlight?.page_number ?? pages[0]?.page_number ?? 1,
  );

  const openSpan = (span: ClaimSpan) => {
    setActiveSpan(span);
    setSelectedPage(span.page_number);
  };

  const selectPage = (pageNumber: number) => {
    setSelectedPage(pageNumber);
    // Leaving a stale highlight on a page it does not belong to would be a lie
    // about where the claim text is.
    if (activeSpan && activeSpan.page_number !== pageNumber) {
      setActiveSpan(null);
    }
  };

  return (
    <>
      <ClaimsPanel
        documentId={documentId}
        documentCompleted={documentCompleted}
        claimSet={claimSet}
        onOpenSpan={openSpan}
        activeSpan={activeSpan}
      />

      {pages.length > 0 && (
        <PageViewer
          pages={pages}
          selectedPage={selectedPage}
          onSelectPage={selectPage}
          highlight={activeSpan}
        />
      )}
    </>
  );
}
