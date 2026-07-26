"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { parseClaimsAction } from "@/app/documents/[id]/actions";
import type { PageHighlight } from "@/components/PageViewer";
import { INITIAL_PARSE_STATE, type ParseClaimsState } from "@/lib/action-state";
import {
  claimTypeLabel,
  dependencyLabel,
  type Claim,
  type ClaimSet,
  type ClaimSpan,
} from "@/lib/claims";

function ParseButton({ hasResult }: { hasResult: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? "Parsing…" : hasResult ? "Re-run parse" : "Parse claims"}
    </button>
  );
}

/**
 * Claim structure for one document.
 *
 * Every outcome is shown explicitly, including "no claims found" and a failed
 * parse: a silent empty list would be indistinguishable from a document that
 * genuinely has no claims.
 */
export function ClaimsPanel({
  documentId,
  documentCompleted,
  claimSet,
  onOpenSpan,
  activeSpan,
}: {
  documentId: string;
  documentCompleted: boolean;
  claimSet: ClaimSet | null;
  onOpenSpan: (span: ClaimSpan) => void;
  // Compared by coordinates only, so a highlight seeded from a search-result
  // deep link marks the matching span exactly as a clicked one does.
  activeSpan: PageHighlight | null;
}) {
  const [state, formAction] = useActionState<ParseClaimsState, FormData>(
    parseClaimsAction,
    INITIAL_PARSE_STATE,
  );
  const result = claimSet?.result ?? null;

  return (
    <section className="panel" aria-labelledby="claims-heading">
      <div className="panel-header">
        <h2 id="claims-heading">Claim structure</h2>
        {result && (
          <span className="badge" data-claim-status={result.status}>
            {result.status.replace(/_/g, " ")}
          </span>
        )}
      </div>

      {documentCompleted ? (
        <form action={formAction} className="upload-form">
          <input type="hidden" name="documentId" value={documentId} />
          <ParseButton hasResult={result !== null} />
          {result && (
            <span className="meta">
              {result.parser_name} {result.parser_version}
            </span>
          )}
        </form>
      ) : (
        <p className="meta">
          Claim parsing needs a document whose ingestion has completed.
        </p>
      )}

      {state.status !== "idle" && (
        <p className="notice" data-tone={state.status === "error" ? "error" : "success"} role="status">
          {state.message}
        </p>
      )}

      {claimSet === null ? (
        <p className="meta">This document has not been parsed for claims yet.</p>
      ) : (
        <ClaimSetBody claimSet={claimSet} onOpenSpan={onOpenSpan} activeSpan={activeSpan} />
      )}
    </section>
  );
}

function ClaimSetBody({
  claimSet,
  onOpenSpan,
  activeSpan,
}: {
  claimSet: ClaimSet;
  onOpenSpan: (span: ClaimSpan) => void;
  // Compared by coordinates only, so a highlight seeded from a search-result
  // deep link marks the matching span exactly as a clicked one does.
  activeSpan: PageHighlight | null;
}) {
  const { result, claims } = claimSet;

  return (
    <>
      {result.status === "no_claims_found" && (
        <p className="notice" data-tone="warn">
          No claim headings were found. The document was read successfully, so this
          means it does not contain a recognised claim set.
        </p>
      )}

      {result.status === "failed" && (
        <p className="notice" data-tone="error">
          <strong>{result.error_code}</strong> — {result.error_message}
        </p>
      )}

      {result.status === "processing" && (
        <p className="notice" data-tone="warn">
          A previous parse did not finish. Re-run it to try again.
        </p>
      )}

      {result.warnings.length > 0 && (
        <details className="warnings">
          <summary>
            {result.warning_count} parse warning{result.warning_count === 1 ? "" : "s"}
          </summary>
          <ul>
            {result.warnings.map((warning, index) => (
              <li key={`${warning.code}-${index}`}>
                <code>{warning.code}</code>
                {warning.claim_number !== null && <> · Claim {warning.claim_number}</>} —{" "}
                {warning.message}
              </li>
            ))}
          </ul>
        </details>
      )}

      {claims.length > 0 && (
        <ol className="claim-list">
          {claims.map((claim) => (
            <ClaimItem
              key={claim.claim_number}
              claim={claim}
              onOpenSpan={onOpenSpan}
              activeSpan={activeSpan}
            />
          ))}
        </ol>
      )}
    </>
  );
}

function ClaimItem({
  claim,
  onOpenSpan,
  activeSpan,
}: {
  claim: Claim;
  onOpenSpan: (span: ClaimSpan) => void;
  // Compared by coordinates only, so a highlight seeded from a search-result
  // deep link marks the matching span exactly as a clicked one does.
  activeSpan: PageHighlight | null;
}) {
  const dependencies = dependencyLabel(claim.depends_on);

  return (
    <li className="claim">
      <div className="claim-header">
        <h3>Claim {claim.claim_number}</h3>
        <span className="badge" data-claim-type={claim.claim_type}>
          {claimTypeLabel(claim.claim_type)}
        </span>
        {claim.crosses_pages && (
          <span className="badge" title="This claim's source crosses a page break">
            spans {claim.spans.length} pages
          </span>
        )}
      </div>

      <p className="claim-dependencies">{dependencies ?? "No explicit dependency"}</p>
      <p className="claim-text">{claim.text}</p>

      <div className="claim-spans">
        {claim.spans.map((span) => {
          const isActive =
            activeSpan !== null &&
            activeSpan.page_number === span.page_number &&
            activeSpan.start_char === span.start_char &&
            activeSpan.end_char === span.end_char;
          return (
            <button
              key={span.sequence_number}
              type="button"
              onClick={() => onOpenSpan(span)}
              data-active={isActive}
              title="Open this span in the page text"
            >
              {`p${span.page_number}:${span.start_char}-${span.end_char}`}
            </button>
          );
        })}
      </div>
    </li>
  );
}
