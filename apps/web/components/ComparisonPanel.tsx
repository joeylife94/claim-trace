"use client";

import Link from "next/link";
import { useActionState, useMemo, useState } from "react";
import { useFormStatus } from "react-dom";
import { compareClaimsAction } from "@/app/compare/actions";
import {
  INITIAL_COMPARISON_STATE,
  type ClaimComparisonState,
} from "@/lib/action-state";
import { claimTypeLabel, dependencyLabel, type Claim } from "@/lib/claims";
import {
  COMPARISON_TOP_K_CHOICES,
  noCorrespondenceLabel,
  type ComparisonClaim,
  type ComparisonMatch,
} from "@/lib/comparison";
import type { DocumentRecord } from "@/lib/documents";
import {
  RETRIEVAL_MODES,
  formatRank,
  formatScore,
  modeLabel,
  spanHref,
} from "@/lib/search";

export type ComparisonDocument = {
  document: DocumentRecord;
  claims: Claim[];
};

function CompareButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? "Comparing…" : "Compare claims"}
    </button>
  );
}

export function ComparisonPanel({
  documents,
  initialTargetDocumentId = "",
}: {
  documents: ComparisonDocument[];
  initialTargetDocumentId?: string;
}) {
  const contextualTarget = documents.find(
    (entry) =>
      entry.document.id === initialTargetDocumentId && entry.claims.length > 0,
  )?.document.id;
  const initialTarget =
    contextualTarget ?? documents.find((entry) => entry.claims.length > 0)?.document.id ?? "";
  const initialReference =
    documents.find((entry) => entry.document.id !== initialTarget)?.document.id ?? "";
  const [targetDocumentId, setTargetDocumentId] = useState(initialTarget);

  const initialState: ClaimComparisonState = {
    ...INITIAL_COMPARISON_STATE,
    targetDocumentId: initialTarget,
    referenceDocumentId: initialReference,
  };
  const [state, formAction] = useActionState(compareClaimsAction, initialState);

  const targetClaims = useMemo(
    () => documents.find((entry) => entry.document.id === targetDocumentId)?.claims ?? [],
    [documents, targetDocumentId],
  );

  const documentName = (id: string) =>
    documents.find((entry) => entry.document.id === id)?.document.original_filename ?? id;

  if (documents.length < 2) {
    return (
      <section className="panel">
        <p className="notice" data-tone="warn">
          Comparison needs at least two completed documents. Upload, parse, and index another
          text-based patent PDF first.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className="panel" aria-labelledby="compare-heading">
        <div className="panel-header">
          <h2 id="compare-heading">Compare one claim</h2>
        </div>

        <form action={formAction} className="search-form">
          <div className="search-controls">
            <label className="search-field">
              <span>Target document</span>
              <select
                name="targetDocumentId"
                value={targetDocumentId}
                onChange={(event) => setTargetDocumentId(event.target.value)}
                required
              >
                {documents.map(({ document }) => (
                  <option key={document.id} value={document.id}>
                    {document.original_filename}
                  </option>
                ))}
              </select>
            </label>

            <label className="search-field">
              <span>Target claim</span>
              <select
                key={targetDocumentId}
                name="targetClaimNumber"
                defaultValue={targetClaims[0]?.claim_number ?? 1}
                required
              >
                {targetClaims.length === 0 ? (
                  <option value="">No parsed claims</option>
                ) : (
                  targetClaims.map((claim) => (
                    <option key={claim.claim_number} value={claim.claim_number}>
                      Claim {claim.claim_number} · {claimTypeLabel(claim.claim_type)}
                    </option>
                  ))
                )}
              </select>
            </label>

            <label className="search-field">
              <span>Reference document</span>
              <select
                name="referenceDocumentId"
                defaultValue={state.referenceDocumentId || initialReference}
                required
              >
                {documents.map(({ document }) => (
                  <option key={document.id} value={document.id} disabled={document.id === targetDocumentId}>
                    {document.original_filename}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="search-controls">
            <label className="search-field">
              <span>Mode</span>
              <select name="mode" defaultValue={state.mode}>
                {RETRIEVAL_MODES.map((mode) => (
                  <option key={mode} value={mode}>
                    {mode}
                  </option>
                ))}
              </select>
            </label>

            <label className="search-field">
              <span>Matches</span>
              <select name="topK" defaultValue={String(state.topK)}>
                {COMPARISON_TOP_K_CHOICES.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            </label>

            <CompareButton />
          </div>
        </form>

        {state.status !== "idle" && (
          <p
            className="notice"
            data-tone={state.status === "error" ? "error" : state.response?.no_correspondence_found ? "warn" : "success"}
            role="status"
          >
            {state.message}
          </p>
        )}
      </section>

      {state.response && (
        <ComparisonResults response={state.response} documentName={documentName} />
      )}
    </>
  );
}

function ComparisonResults({
  response,
  documentName,
}: {
  response: NonNullable<ClaimComparisonState["response"]>;
  documentName: (id: string) => string;
}) {
  return (
    <section className="panel" aria-labelledby="comparison-results-heading">
      <div className="panel-header">
        <h2 id="comparison-results-heading">Comparison result</h2>
        <span className="status-value">
          {modeLabel(response.mode, response.profile.rrf_k)} · {response.match_count} match
          {response.match_count === 1 ? "" : "es"}
        </span>
      </div>

      <div className="claim-list">
        <ComparisonClaimCard
          heading="Target claim"
          claim={response.target}
          documentName={documentName(response.target.document_id)}
        />

        {response.no_correspondence_found ? (
          <div className="claim">
            <h3>Reference document</h3>
            <p className="notice" data-tone="warn">
              {noCorrespondenceLabel(response.no_correspondence_reason)}
            </p>
          </div>
        ) : (
          response.matches.map((match) => (
            <ComparisonMatchCard
              key={`${match.document_id}-${match.claim_number}`}
              match={match}
              documentName={documentName(match.document_id)}
            />
          ))
        )}
      </div>
    </section>
  );
}

function ComparisonClaimCard({
  heading,
  claim,
  documentName,
}: {
  heading: string;
  claim: ComparisonClaim;
  documentName: string;
}) {
  return (
    <div className="claim">
      <div className="claim-header">
        <h3>
          {heading} · Claim {claim.claim_number}
        </h3>
        <span className="badge" data-claim-type={claim.claim_type}>
          {claimTypeLabel(claim.claim_type)}
        </span>
        <span className="meta">{documentName}</span>
      </div>
      <p className="claim-dependencies">{dependencyLabel(claim.depends_on) ?? "No explicit dependency"}</p>
      <p className="claim-text">{claim.text}</p>
      <SourceLinks claim={claim} />
    </div>
  );
}

function ComparisonMatchCard({
  match,
  documentName,
}: {
  match: ComparisonMatch;
  documentName: string;
}) {
  return (
    <div className="claim">
      <div className="claim-header">
        <h3>
          Reference match #{match.fused_rank} · Claim {match.claim_number}
        </h3>
        <span className="badge" data-claim-type={match.claim_type}>
          {claimTypeLabel(match.claim_type)}
        </span>
        <span className="meta">{documentName}</span>
      </div>
      <p className="claim-dependencies">{dependencyLabel(match.depends_on) ?? "No explicit dependency"}</p>
      <p className="claim-text">{match.text}</p>
      <dl className="rank-facts">
        <RankFact label="Dense" rank={formatRank(match.dense_rank)} score={formatScore(match.dense_score)} />
        <RankFact label="Lexical" rank={formatRank(match.lexical_rank)} score={formatScore(match.lexical_score)} />
        <RankFact label="Fused" rank={formatRank(match.fused_rank)} score={match.fused_score.toFixed(5)} />
      </dl>
      <SourceLinks claim={match} />
    </div>
  );
}

function SourceLinks({ claim }: { claim: ComparisonClaim }) {
  return (
    <div className="claim-spans">
      {claim.source_spans.map((span) => (
        <Link
          key={`${span.page_number}-${span.start_char}-${span.end_char}`}
          href={spanHref(span)}
          title="Open this exact source span in the document"
        >
          {`p${span.page_number}:${span.start_char}-${span.end_char}`}
        </Link>
      ))}
    </div>
  );
}

function RankFact({ label, rank, score }: { label: string; rank: string; score: string }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>
        {rank} <span className="meta">{score}</span>
      </dd>
    </div>
  );
}
