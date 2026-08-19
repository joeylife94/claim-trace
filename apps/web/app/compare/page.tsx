import Link from "next/link";
import { ComparisonPanel, type ComparisonDocument } from "@/components/ComparisonPanel";
import { getClaims } from "@/lib/claims";
import { listDocuments } from "@/lib/documents";

export const dynamic = "force-dynamic";

export default async function ComparePage() {
  const documents = await listDocuments(100)
    .then((response) => response.items.filter((document) => document.status === "completed"))
    .catch(() => []);

  const comparisonDocuments: ComparisonDocument[] = await Promise.all(
    documents.map(async (document) => ({
      document,
      claims: await getClaims(document.id)
        .then((claimSet) => (claimSet?.result.status === "completed" ? claimSet.claims : []))
        .catch(() => []),
    })),
  );

  return (
    <>
      <main>
        <p className="eyebrow">
          <Link href="/">ClaimTrace</Link> · Compare
        </p>
        <h1 className="document-title">Claim comparison</h1>
        <p className="tagline">
          Compare one stored claim against claims retrieved only from one selected reference
          document. Results show textual correspondence and exact source locations, not a legal
          conclusion.
        </p>

        <ComparisonPanel documents={comparisonDocuments} />
      </main>
      <footer>
        ClaimTrace does not determine infringement, validity, novelty, equivalence, inventive
        step, or patentability. Read every comparison against the linked source text.
      </footer>
    </>
  );
}
