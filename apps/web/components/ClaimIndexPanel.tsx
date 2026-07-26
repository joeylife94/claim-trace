"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { indexClaimsAction } from "@/app/documents/[id]/actions";
import { INITIAL_INDEX_STATE, type IndexClaimsState } from "@/lib/action-state";
import type { ClaimIndexRun } from "@/lib/search";

function IndexButton({ hasRun }: { hasRun: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? "Indexing…" : hasRun ? "Re-index claims" : "Index claims"}
    </button>
  );
}

/**
 * Retrieval index status for one document.
 *
 * The embedding model and vector dimension are shown rather than hidden because
 * they decide what a search can find: an index built by one model is not
 * searchable by another, and a reader comparing two result sets needs to know
 * which profile produced each.
 */
export function ClaimIndexPanel({
  documentId,
  canIndex,
  indexRun,
}: {
  documentId: string;
  /** False until claim parsing has completed - there is nothing to index before then. */
  canIndex: boolean;
  indexRun: ClaimIndexRun | null;
}) {
  const [state, formAction] = useActionState<IndexClaimsState, FormData>(
    indexClaimsAction,
    INITIAL_INDEX_STATE,
  );

  return (
    <section className="panel" aria-labelledby="index-heading">
      <div className="panel-header">
        <h2 id="index-heading">Retrieval index</h2>
        {indexRun && (
          <span className="badge" data-index-status={indexRun.status}>
            {indexRun.status}
          </span>
        )}
      </div>

      {canIndex ? (
        <form action={formAction} className="upload-form">
          <input type="hidden" name="documentId" value={documentId} />
          <IndexButton hasRun={indexRun !== null} />
          <span className="meta">
            Embeds this document&rsquo;s claims so they can be found by meaning as well
            as by wording. The first run loads the model and may take a while.
          </span>
        </form>
      ) : (
        <p className="meta">
          Claim indexing needs a completed claim parse. Parse the claims first.
        </p>
      )}

      {state.status !== "idle" && (
        <p
          className="notice"
          data-tone={state.status === "error" ? "error" : "success"}
          role="status"
        >
          {state.message}
        </p>
      )}

      {indexRun === null ? (
        <p className="meta">This document&rsquo;s claims have not been indexed yet.</p>
      ) : (
        <>
          {indexRun.status === "failed" && (
            <p className="notice" data-tone="error">
              <strong>{indexRun.error_code}</strong> — {indexRun.error_message}
            </p>
          )}

          {indexRun.status === "processing" && (
            <p className="notice" data-tone="warn">
              A previous indexing run did not finish. Re-index to try again.
            </p>
          )}

          <dl className="facts">
            <Fact label="Indexed claims" value={indexRun.indexed_claim_count.toLocaleString()} />
            <Fact label="Model" value={indexRun.embedding_model} />
            <Fact label="Provider" value={indexRun.embedding_provider} />
            <Fact
              label="Vector"
              value={`${indexRun.embedding_dimension}d ${
                indexRun.vectors_normalized ? "normalised" : "raw"
              }`}
            />
            <Fact label="Lexical" value={indexRun.lexical_strategy} />
            <Fact label="Normalisation" value={indexRun.normalization_version} />
          </dl>

          {indexRun.status === "completed" && (
            <p className="meta">
              <Link href={`/search?document=${documentId}`}>
                Search this document&rsquo;s claims →
              </Link>
            </p>
          )}
        </>
      )}
    </section>
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
