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

        <section className="panel" aria-labelledby="search-heading">
          <div className="panel-header">
            <h2 id="search-heading">Claim search</h2>
          </div>
          <p className="meta">
            Hybrid retrieval over indexed claims - vector similarity and Korean
            lexical matching, fused by rank. Every result links back to the exact
            page and character range it came from.
          </p>
          <div className="actions">
            <Link href="/search">Search claims →</Link>
          </div>
        </section>

        <section className="panel" aria-labelledby="grounded-heading">
          <div className="panel-header">
            <h2 id="grounded-heading">Grounded answers</h2>
          </div>
          <p className="meta">
            Ask a question and get an answer built only from retrieved claim
            text. Every statement cites evidence the server issued, and every
            citation resolves to the exact page and character range it came from.
          </p>
          <div className="actions">
            <Link href="/grounded">Ask a question →</Link>
          </div>
        </section>

        <section className="panel" aria-labelledby="llm-heading">
          <div className="panel-header">
            <h2 id="llm-heading">Local LLM</h2>
          </div>
          <p className="meta">
            Status, capabilities, and diagnostics for the configured local model
            provider - the boundary grounded answering generates through.
          </p>
          <div className="actions">
            <Link href="/llm">Provider diagnostics →</Link>
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
