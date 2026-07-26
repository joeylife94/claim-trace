"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { searchClaimsAction } from "@/app/search/actions";
import { INITIAL_SEARCH_STATE, type SearchClaimsState } from "@/lib/action-state";
import { claimTypeLabel, dependencyLabel } from "@/lib/claims";
import type { DocumentRecord } from "@/lib/documents";
import {
  MAX_QUERY_LENGTH,
  RETRIEVAL_MODES,
  TOP_K_CHOICES,
  formatRank,
  formatScore,
  modeLabel,
  spanHref,
  type ClaimSearchResponse,
  type ClaimSearchResult,
} from "@/lib/search";

function SearchButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? "Searching…" : "Search"}
    </button>
  );
}

/**
 * Claim search over the indexed corpus.
 *
 * Ranking metadata is shown per channel rather than reduced to one number,
 * because "why did this come back?" is the question a reviewer actually asks -
 * and the answer differs between a claim both channels agreed on and one only
 * the vector index found.
 */
export function SearchPanel({
  documents,
  initialDocumentId,
}: {
  documents: DocumentRecord[];
  initialDocumentId: string;
}) {
  const [state, formAction] = useActionState<SearchClaimsState, FormData>(searchClaimsAction, {
    ...INITIAL_SEARCH_STATE,
    documentId: initialDocumentId,
  });

  return (
    <>
      <section className="panel" aria-labelledby="search-heading">
        <div className="panel-header">
          <h2 id="search-heading">Search claims</h2>
        </div>

        <form action={formAction} className="search-form">
          <label className="search-field">
            <span>Query</span>
            <input
              type="text"
              name="query"
              defaultValue={state.query}
              maxLength={MAX_QUERY_LENGTH}
              placeholder="센서 데이터를 수집하는 통신 장치"
              autoComplete="off"
              required
            />
          </label>

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
              <span>Document</span>
              <select name="documentId" defaultValue={state.documentId}>
                <option value="">All documents</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.original_filename}
                  </option>
                ))}
              </select>
            </label>

            <label className="search-field">
              <span>Results</span>
              <select name="topK" defaultValue={String(state.topK)}>
                {TOP_K_CHOICES.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            </label>

            <SearchButton />
          </div>
        </form>

        {state.status !== "idle" && (
          <p
            className="notice"
            data-tone={state.status === "error" ? "error" : "success"}
            role="status"
          >
            {state.message}
          </p>
        )}

        {state.response && <ProfileSummary response={state.response} />}
      </section>

      {state.response && state.response.results.length > 0 && (
        <section className="panel" aria-labelledby="results-heading">
          <div className="panel-header">
            <h2 id="results-heading">Results</h2>
            <span className="status-value">
              {state.response.result_count} claim
              {state.response.result_count === 1 ? "" : "s"}
            </span>
          </div>

          <ol className="claim-list">
            {state.response.results.map((result) => (
              <ResultItem
                key={`${result.document_id}-${result.claim_number}`}
                result={result}
              />
            ))}
          </ol>
        </section>
      )}

      {state.status === "results" &&
        state.response &&
        state.response.results.length === 0 &&
        state.response.searched_index_run_count > 0 && (
          <section className="panel">
            <p className="meta">
              Nothing matched. Lexical search finds wording; dense search finds
              meaning. Try `hybrid`, or different terminology.
            </p>
          </section>
        )}
    </>
  );
}

function ProfileSummary({ response }: { response: ClaimSearchResponse }) {
  const { profile } = response;
  return (
    <p className="meta">
      {modeLabel(response.mode, profile.rrf_k)} · {profile.embedding_model} ·{" "}
      {profile.embedding_dimension}d · {profile.lexical_strategy} ·{" "}
      {response.searched_index_run_count} indexed document
      {response.searched_index_run_count === 1 ? "" : "s"} · {response.dense_candidate_count} dense
      / {response.lexical_candidate_count} lexical candidates
    </p>
  );
}

function ResultItem({ result }: { result: ClaimSearchResult }) {
  const dependencies = dependencyLabel(result.depends_on);

  return (
    <li className="claim">
      <div className="claim-header">
        <h3>
          #{result.fused_rank} · Claim {result.claim_number}
        </h3>
        <span className="badge" data-claim-type={result.claim_type}>
          {claimTypeLabel(result.claim_type)}
        </span>
        <span className="meta">{result.document_filename}</span>
      </div>

      <p className="claim-dependencies">{dependencies ?? "No explicit dependency"}</p>
      <p className="claim-text">{result.text}</p>

      {/*
        A channel that did not retrieve this claim shows an em dash, not 0.000:
        "not retrieved" and "retrieved with a low score" are different facts.
      */}
      <dl className="rank-facts">
        <RankFact
          label="Dense"
          rank={formatRank(result.dense_rank)}
          score={formatScore(result.dense_score)}
        />
        <RankFact
          label="Lexical"
          rank={formatRank(result.lexical_rank)}
          score={formatScore(result.lexical_score)}
        />
        <RankFact
          label="Fused"
          rank={formatRank(result.fused_rank)}
          score={result.fused_score.toFixed(5)}
        />
      </dl>

      <div className="claim-spans">
        {result.source_spans.map((span) => (
          <Link
            key={`${span.page_number}-${span.start_char}-${span.end_char}`}
            href={spanHref(span)}
            title="Open this span in the document's page text"
          >
            {`p${span.page_number}:${span.start_char}-${span.end_char}`}
          </Link>
        ))}
      </div>
    </li>
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
