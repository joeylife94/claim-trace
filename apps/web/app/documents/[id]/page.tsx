import Link from "next/link";
import { notFound } from "next/navigation";
import { ClaimIndexPanel } from "@/components/ClaimIndexPanel";
import { ClaimWorkspace } from "@/components/ClaimWorkspace";
import type { PageHighlight } from "@/components/PageViewer";
import { getClaims } from "@/lib/claims";
import {
  formatBytes,
  formatTimestamp,
  getDocument,
  getDocumentPages,
} from "@/lib/documents";
import { getClaimIndex } from "@/lib/search";

export const dynamic = "force-dynamic";

export default async function DocumentDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  /** `?page=&start=&end=` — a source span opened from a search result. */
  searchParams: Promise<{ page?: string; start?: string; end?: string }>;
}) {
  const { id } = await params;
  const document = await getDocument(id);

  if (document === null) {
    notFound();
  }

  // A failed document has no pages; asking for them anyway would be a wasted call.
  const completed = document.status === "completed";
  const [pages, claimSet, indexRun] = completed
    ? await Promise.all([
        getDocumentPages(id).then((response) => response.items),
        getClaims(id).catch(() => null),
        getClaimIndex(id).catch(() => null),
      ])
    : [[], null, null];

  const highlight = parseHighlight(await searchParams);

  return (
    <>
      <main>
        <p className="eyebrow">
          <Link href="/documents">Documents</Link> · Detail
        </p>
        <h1 className="document-title">{document.original_filename}</h1>

        <section className="panel" aria-labelledby="ingestion-heading">
          <div className="panel-header">
            <h2 id="ingestion-heading">Ingestion</h2>
            <span className="badge" data-status={document.status}>
              {document.status}
            </span>
          </div>

          <dl className="facts">
            <Fact label="Pages" value={document.page_count?.toString() ?? "—"} />
            <Fact
              label="Characters"
              value={document.extracted_character_count?.toLocaleString() ?? "—"}
            />
            <Fact label="Size" value={formatBytes(document.size_bytes)} />
            <Fact label="Uploaded" value={formatTimestamp(document.created_at)} />
            <Fact
              label="Parser"
              value={
                document.parser_name
                  ? `${document.parser_name} ${document.parser_version ?? ""}`.trim()
                  : "—"
              }
            />
            <Fact label="SHA-256" value={`${document.sha256.slice(0, 16)}…`} />
          </dl>

          {document.status === "failed" && (
            <p className="notice" data-tone="error">
              <strong>{document.error_code}</strong> — {document.error_message}
            </p>
          )}
        </section>

        <ClaimIndexPanel
          documentId={id}
          canIndex={claimSet?.result.status === "completed"}
          indexRun={indexRun}
        />

        <ClaimWorkspace
          documentId={id}
          documentCompleted={completed}
          pages={pages}
          claimSet={claimSet}
          initialHighlight={highlight}
        />
      </main>
      <footer>
        MVP portfolio project. Extracted text and claim structure are shown as
        stored, without interpretation. ClaimTrace does not provide legal advice and
        does not determine infringement, validity, or patentability.
      </footer>
    </>
  );
}

/**
 * Read a source span out of the query string.
 *
 * Every field must be a valid number and the range must be non-empty, matching
 * the half-open `[start_char, end_char)` semantics the API uses. A malformed
 * link renders the page with no highlight rather than an approximate one: a
 * highlight over the wrong characters would be a false citation.
 */
function parseHighlight(query: {
  page?: string;
  start?: string;
  end?: string;
}): PageHighlight | null {
  const page = Number(query.page);
  const start = Number(query.start);
  const end = Number(query.end);

  const valid =
    Number.isInteger(page) &&
    page >= 1 &&
    Number.isInteger(start) &&
    start >= 0 &&
    Number.isInteger(end) &&
    end > start;

  return valid ? { page_number: page, start_char: start, end_char: end } : null;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
