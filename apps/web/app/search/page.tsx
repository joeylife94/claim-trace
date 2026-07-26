import Link from "next/link";
import { SearchPanel } from "@/components/SearchPanel";
import { listDocuments } from "@/lib/documents";

export const dynamic = "force-dynamic";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ document?: string }>;
}) {
  const { document } = await searchParams;

  // The document filter is a select rather than a free-text id, so the list is
  // needed to render the form. An unreachable API leaves the filter empty rather
  // than failing the whole page: an unscoped search still works.
  const documents = await listDocuments(100)
    .then((response) => response.items)
    .catch(() => []);

  return (
    <>
      <main>
        <p className="eyebrow">
          <Link href="/">ClaimTrace</Link> · Search
        </p>
        <h1 className="document-title">Claim search</h1>
        <p className="tagline">
          Hybrid retrieval over indexed claims. Every result carries the page and
          character range it came from, so it can be checked against the document.
        </p>

        <SearchPanel documents={documents} initialDocumentId={document ?? ""} />
      </main>
      <footer>
        MVP portfolio project. Results are textual matches against stored claim
        text, ranked by similarity - not an assessment of relevance in law.
        ClaimTrace does not provide legal advice and does not determine
        infringement, validity, novelty, or patentability.
      </footer>
    </>
  );
}
