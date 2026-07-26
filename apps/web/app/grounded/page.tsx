import Link from "next/link";
import { GroundedAnswerPanel } from "@/components/GroundedAnswerPanel";
import { listDocuments } from "@/lib/documents";

export const dynamic = "force-dynamic";

export default async function GroundedPage({
  searchParams,
}: {
  searchParams: Promise<{ document?: string }>;
}) {
  const { document } = await searchParams;

  // The document filter is a select rather than a free-text id, so the list is
  // needed to render the form. An unreachable API leaves the filter empty
  // rather than failing the whole page: an unscoped question still works.
  const documents = await listDocuments(100)
    .then((response) => response.items)
    .catch(() => []);

  return (
    <>
      <main>
        <p className="eyebrow">
          <Link href="/">ClaimTrace</Link> · Grounded answers
        </p>
        <h1 className="document-title">Evidence-grounded answers</h1>
        <p className="tagline">
          A question is answered only from claims retrieved out of your indexed
          documents. Every statement carries the evidence it was checked against,
          and every citation opens the exact page and character range it came
          from.
        </p>

        <GroundedAnswerPanel documents={documents} initialDocumentId={document ?? ""} />
      </main>
      <footer>
        MVP portfolio project. A resolvable citation shows that a statement points
        at retrieved source text; it is not a proof that the cited text entails
        the statement, and answers should be read against their sources.
        ClaimTrace does not provide legal advice and does not determine
        infringement, validity, novelty, inventive step, or patentability.
      </footer>
    </>
  );
}
