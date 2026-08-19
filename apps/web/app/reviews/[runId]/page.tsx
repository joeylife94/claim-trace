import Link from "next/link";
import { getElementReviews, type ReviewStatus } from "@/lib/claim-elements";
import { spanHref } from "@/lib/search";
import { submitElementReviewAction } from "./actions";

export const dynamic = "force-dynamic";

const REVIEW_LABELS: Record<ReviewStatus, string> = {
  accepted: "Accepted",
  needs_correction: "Needs correction",
};

export default async function ElementReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ review_error?: string; review_saved?: string }>;
}) {
  const { runId } = await params;
  const query = await searchParams;
  const outcome = await getElementReviews(runId);

  if (!outcome.ok) {
    return (
      <main>
        <p className="eyebrow">
          <Link href="/documents">ClaimTrace</Link> · Human review
        </p>
        <h1>Review unavailable</h1>
        <section className="panel">
          <p className="notice" data-tone="error">
            {outcome.detail}
          </p>
        </section>
      </main>
    );
  }

  const snapshot = outcome.value;
  const submitReview = submitElementReviewAction.bind(null, runId);

  return (
    <main>
      <p className="eyebrow">
        <Link href={`/documents/${snapshot.document_id}`}>Document</Link> · Human review
      </p>
      <h1>Review claim elements</h1>
      <p className="tagline">
        Review one exact machine decomposition. Your judgement is appended separately;
        it does not edit the machine-produced elements or their source spans.
      </p>

      {query.review_error && (
        <p className="notice" data-tone="error" role="status">
          {query.review_error}
        </p>
      )}
      {query.review_saved && (
        <p className="notice" data-tone="success" role="status">
          Review saved: {REVIEW_LABELS[query.review_saved as ReviewStatus] ?? query.review_saved}
        </p>
      )}

      <section className="panel" aria-labelledby="run-heading">
        <div className="panel-header">
          <h2 id="run-heading">Exact decomposition run</h2>
          <span className="status-value">{snapshot.parser_name}</span>
        </div>
        <dl className="facts">
          <Fact label="Run" value={snapshot.run_id} />
          <Fact label="Parser version" value={snapshot.parser_version} />
          <Fact label="Elements" value={String(snapshot.elements.length)} />
          <Fact label="Reviews" value={String(snapshot.reviews.length)} />
        </dl>
      </section>

      <section className="panel" aria-labelledby="elements-heading">
        <div className="panel-header">
          <h2 id="elements-heading">Reviewed elements and evidence</h2>
        </div>
        {snapshot.elements.length === 0 ? (
          <p className="meta">This decomposition run contains no elements to review.</p>
        ) : (
          <ol className="claim-list">
            {snapshot.elements.map((element) => (
              <li className="claim" key={element.id}>
                <div className="claim-header">
                  <h3>Element {element.sequence_number + 1}</h3>
                </div>
                <p className="claim-text">{element.text}</p>
                <div className="claim-spans">
                  {element.spans.map((span) => (
                    <Link
                      key={`${span.page_number}-${span.start_char}-${span.end_char}`}
                      href={spanHref(span.locator)}
                      title="Open this exact reviewed span in the original document"
                    >
                      {`p${span.page_number}:${span.start_char}-${span.end_char}`}
                    </Link>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="panel" aria-labelledby="review-heading">
        <div className="panel-header">
          <h2 id="review-heading">Append review judgement</h2>
        </div>
        <form action={submitReview} className="search-controls">
          <button type="submit" name="status" value="accepted">
            Accept decomposition
          </button>
          <button type="submit" name="status" value="needs_correction">
            Mark needs correction
          </button>
        </form>
        <p className="meta">
          A new review entry is appended each time. Previous review history is preserved.
        </p>
      </section>

      <section className="panel" aria-labelledby="history-heading">
        <div className="panel-header">
          <h2 id="history-heading">Review history</h2>
          <span className="status-value">{snapshot.reviews.length} entries</span>
        </div>
        {snapshot.reviews.length === 0 ? (
          <p className="meta">No human review has been recorded for this exact run yet.</p>
        ) : (
          <ol className="claim-list">
            {snapshot.reviews.map((review) => (
              <li className="claim" key={review.id}>
                <div className="claim-header">
                  <strong>{REVIEW_LABELS[review.status]}</strong>
                  <span className="meta">{new Date(review.created_at).toISOString()}</span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </main>
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
