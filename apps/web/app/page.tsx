import Link from "next/link";
import { SystemStatusPanel } from "@/components/SystemStatusPanel";
import { loadSystemStatus } from "@/lib/api";

// Status must reflect the API at request time, never a build-time snapshot.
export const dynamic = "force-dynamic";

export default async function Home() {
  const status = await loadSystemStatus();

  return (
    <>
      <main>
        <p className="eyebrow">On-premise · Retrieval-augmented</p>
        <h1>ClaimTrace</h1>
        <p className="tagline">Evidence-Grounded Patent Claim Analysis</p>
        <SystemStatusPanel status={status} />

        <section className="panel" aria-labelledby="documents-heading">
          <div className="panel-header">
            <h2 id="documents-heading">Documents</h2>
          </div>
          <p className="meta">
            Upload a text-based patent PDF and review the extracted text page by page.
          </p>
          <div className="actions">
            <Link href="/documents">Go to documents →</Link>
          </div>
        </section>
      </main>
      <footer>
        MVP portfolio project. ClaimTrace does not provide legal advice and does not
        determine patent infringement, validity, or patentability.
      </footer>
    </>
  );
}
