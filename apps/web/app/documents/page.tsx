import Link from "next/link";
import { RetryDocumentForm } from "@/components/RetryDocumentForm";
import { UploadForm } from "@/components/UploadForm";
import {
  formatBytes,
  formatTimestamp,
  listDocuments,
  type DocumentRecord,
} from "@/lib/documents";

export const dynamic = "force-dynamic";

const UPLOAD_MAX_BYTES = Number(process.env.NEXT_PUBLIC_UPLOAD_MAX_BYTES ?? 20 * 1024 * 1024);

export default async function DocumentsPage() {
  const documents = await listDocuments().catch(() => null);

  return (
    <>
      <main>
        <p className="eyebrow">
          <Link href="/">ClaimTrace</Link> · Documents
        </p>
        <h1>Documents</h1>
        <p className="tagline">
          Upload a text-based patent PDF. Text is extracted page by page and kept with
          its page coordinates, so later analysis can cite it.
        </p>

        <UploadForm maxBytes={UPLOAD_MAX_BYTES} />

        <section className="panel" aria-labelledby="documents-heading">
          <div className="panel-header">
            <h2 id="documents-heading">Ingested documents</h2>
            {documents && <span className="status-value">{documents.total} total</span>}
          </div>

          {documents === null ? (
            <p className="meta">The API is unreachable, so no documents can be listed.</p>
          ) : documents.items.length === 0 ? (
            <p className="meta">No documents yet. Upload a PDF to get started.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">File</th>
                    <th scope="col">Status</th>
                    <th scope="col">Pages</th>
                    <th scope="col">Characters</th>
                    <th scope="col">Size</th>
                    <th scope="col">Uploaded</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.items.map((document) => (
                    <DocumentRow key={document.id} document={document} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
      <footer>
        MVP portfolio project. ClaimTrace does not provide legal advice and does not
        determine patent infringement, validity, or patentability.
      </footer>
    </>
  );
}

function DocumentRow({ document }: { document: DocumentRecord }) {
  const failed = document.status === "failed";
  return (
    <tr>
      <td>
        <Link href={`/documents/${document.id}`}>{document.original_filename}</Link>
        {failed && document.error_message && (
          <span className="row-note">{document.error_message}</span>
        )}
        {failed && <RetryDocumentForm documentId={document.id} />}
      </td>
      <td>
        <span className="badge" data-status={document.status}>
          {document.status}
        </span>
      </td>
      <td className="numeric">{document.page_count ?? "—"}</td>
      <td className="numeric">
        {document.extracted_character_count?.toLocaleString() ?? "—"}
      </td>
      <td className="numeric">{formatBytes(document.size_bytes)}</td>
      <td>{formatTimestamp(document.created_at)}</td>
    </tr>
  );
}
