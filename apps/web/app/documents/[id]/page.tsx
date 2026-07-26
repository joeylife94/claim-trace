import Link from "next/link";
import { notFound } from "next/navigation";
import { PageViewer } from "@/components/PageViewer";
import {
  formatBytes,
  formatTimestamp,
  getDocument,
  getDocumentPages,
} from "@/lib/documents";

export const dynamic = "force-dynamic";

export default async function DocumentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const document = await getDocument(id);

  if (document === null) {
    notFound();
  }

  // A failed document has no pages; asking for them anyway would be a wasted call.
  const pages =
    document.status === "completed" ? (await getDocumentPages(id)).items : [];

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

        {pages.length > 0 && <PageViewer pages={pages} />}
      </main>
      <footer>
        MVP portfolio project. Extracted text is shown as stored, without
        interpretation. ClaimTrace does not provide legal advice.
      </footer>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
