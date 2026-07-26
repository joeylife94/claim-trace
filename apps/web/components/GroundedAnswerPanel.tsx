"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { askGroundedAction } from "@/app/grounded/actions";
import { INITIAL_GROUNDED_STATE, type GroundedAnswerState } from "@/lib/action-state";
import { claimTypeLabel, dependencyLabel } from "@/lib/claims";
import type { DocumentRecord } from "@/lib/documents";
import {
  GROUNDED_TOP_K_CHOICES,
  MAX_QUESTION_LENGTH,
  evidenceSummary,
  findEvidence,
  insufficientReasonLabel,
  type GroundedAnswer,
  type GroundedEvidence,
  type GroundedStatement,
} from "@/lib/grounded";
import { RETRIEVAL_MODES, formatRank, formatScore, modeLabel, spanHref } from "@/lib/search";

function AskButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? "Answering…" : "Ask"}
    </button>
  );
}

/**
 * Ask a question and read the answer with its sources.
 *
 * Not a chat: there is no history, no follow-up, and no memory. One question
 * produces one answer, and the answer is a list of statements each of which
 * carries the evidence it was validated against.
 *
 * The answer is rendered as plain text in ordinary elements. It is never passed
 * to `dangerouslySetInnerHTML` and never through a Markdown renderer, because
 * model output is untrusted text and there is nothing here it needs to format.
 */
export function GroundedAnswerPanel({
  documents,
  initialDocumentId,
}: {
  documents: DocumentRecord[];
  initialDocumentId: string;
}) {
  const [state, formAction] = useActionState<GroundedAnswerState, FormData>(
    askGroundedAction,
    { ...INITIAL_GROUNDED_STATE, documentId: initialDocumentId },
  );

  return (
    <>
      <section className="panel" aria-labelledby="ask-heading">
        <div className="panel-header">
          <h2 id="ask-heading">Ask a question</h2>
        </div>

        <form action={formAction} className="search-form">
          <label className="search-field">
            <span>Question</span>
            <input
              type="text"
              name="question"
              defaultValue={state.question}
              maxLength={MAX_QUESTION_LENGTH}
              placeholder="통신부는 어떤 모듈을 포함하는가?"
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
              <span>Evidence</span>
              <select name="topK" defaultValue={String(state.topK)}>
                {GROUNDED_TOP_K_CHOICES.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            </label>

            <AskButton />
          </div>
        </form>

        {state.status !== "idle" && (
          <p
            className="notice"
            data-tone={
              state.status === "error"
                ? "error"
                : state.answer?.insufficient_evidence
                  ? "warn"
                  : "success"
            }
            role="status"
          >
            {state.message}
          </p>
        )}
      </section>

      {state.answer && <AnswerPanels answer={state.answer} />}
    </>
  );
}

function AnswerPanels({ answer }: { answer: GroundedAnswer }) {
  return (
    <>
      <section className="panel" aria-labelledby="answer-heading">
        <div className="panel-header">
          <h2 id="answer-heading">Answer</h2>
          {answer.insufficient_evidence && (
            <span className="badge" data-tone="warn">
              {insufficientReasonLabel(answer.insufficient_reason)}
            </span>
          )}
        </div>

        {answer.insufficient_evidence && (
          <p className="grounded-limitation">{limitationSentence(answer)}</p>
        )}

        {answer.statements.length > 0 ? (
          <ol className="grounded-statements">
            {answer.statements.map((statement, index) => (
              <StatementItem
                key={`${index}-${statement.evidence_ids.join(",")}`}
                statement={statement}
                evidence={answer.evidence}
              />
            ))}
          </ol>
        ) : (
          !answer.insufficient_evidence && (
            <p className="meta">No supported statement was returned.</p>
          )
        )}

        {answer.warnings.length > 0 && (
          <ul className="grounded-warnings">
            {answer.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}

        <RunSummary answer={answer} />
      </section>

      {answer.evidence.length > 0 && (
        <section className="panel" aria-labelledby="evidence-heading">
          <div className="panel-header">
            <h2 id="evidence-heading">Cited evidence</h2>
            <span className="status-value">
              {answer.evidence.length} claim
              {answer.evidence.length === 1 ? "" : "s"}
            </span>
          </div>
          <ol className="claim-list">
            {answer.evidence.map((evidence) => (
              <EvidenceItem key={evidence.evidence_id} evidence={evidence} />
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

/**
 * The server's limitation sentence, which leads a partial or refused answer.
 *
 * Taken from `answer.answer`, which the server composed - the first line is the
 * fixed sentence for the reported reason, and any validated statements follow
 * it. Only that first line belongs here; the statements are rendered
 * individually below with their citations attached.
 */
function limitationSentence(answer: GroundedAnswer): string {
  return answer.answer.split("\n")[0] ?? "";
}

function StatementItem({
  statement,
  evidence,
}: {
  statement: GroundedStatement;
  evidence: GroundedEvidence[];
}) {
  return (
    <li className="grounded-statement">
      <p className="grounded-statement-text">{statement.text}</p>
      <div className="evidence-badges">
        {statement.evidence_ids.map((evidenceId) => {
          const entry = findEvidence(evidence, evidenceId);
          return (
            <a
              key={evidenceId}
              className="evidence-badge"
              href={`#${evidenceId}`}
              title={
                entry
                  ? `${entry.document_name} · claim ${entry.claim_number}`
                  : "Cited evidence"
              }
            >
              {evidenceId}
              {entry && <span className="meta"> claim {entry.claim_number}</span>}
            </a>
          );
        })}
      </div>
    </li>
  );
}

function EvidenceItem({ evidence }: { evidence: GroundedEvidence }) {
  const dependencies = dependencyLabel(evidence.depends_on);

  return (
    <li className="claim" id={evidence.evidence_id}>
      <div className="claim-header">
        <h3>
          {evidence.evidence_id} · Claim {evidence.claim_number}
        </h3>
        <span className="badge" data-claim-type={evidence.claim_type}>
          {claimTypeLabel(evidence.claim_type)}
        </span>
        <span className="meta">{evidence.document_name}</span>
      </div>

      <p className="claim-dependencies">{dependencies ?? "No explicit dependency"}</p>

      {/*
        The quote is the stored page text at the locator beside it, read by the
        server. Rendered as text, and never as the model's reproduction of it.
      */}
      {evidence.source_spans.map((span) => (
        <blockquote
          key={`${span.locator.page_number}-${span.locator.start_char}`}
          className="evidence-quote"
        >
          {span.quote}
        </blockquote>
      ))}

      <dl className="rank-facts">
        <RankFact
          label="Dense"
          rank={formatRank(evidence.dense_rank)}
          score={formatScore(evidence.dense_score)}
        />
        <RankFact
          label="Lexical"
          rank={formatRank(evidence.lexical_rank)}
          score={formatScore(evidence.lexical_score)}
        />
        <RankFact
          label="Fused"
          rank={formatRank(evidence.fused_rank)}
          score={evidence.fused_score.toFixed(5)}
        />
      </dl>

      <div className="claim-spans">
        {evidence.source_spans.map((span) => (
          <Link
            key={`${span.locator.page_number}-${span.locator.start_char}-${span.locator.end_char}`}
            href={spanHref(span.locator)}
            title="Open this span in the document's page text"
          >
            {`p${span.locator.page_number}:${span.locator.start_char}-${span.locator.end_char}`}
          </Link>
        ))}
        {evidence.crosses_pages && <span className="meta">crosses a page break</span>}
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

/** Retrieval and provider facts, kept discreet: context for the answer above. */
function RunSummary({ answer }: { answer: GroundedAnswer }) {
  const { retrieval, generation } = answer;
  return (
    <p className="meta grounded-run-summary">
      {modeLabel(retrieval.mode, retrieval.profile.rrf_k)} · {evidenceSummary(retrieval)}
      {generation ? (
        <>
          {" · "}
          {generation.provider}/{generation.model} · {generation.duration_seconds.toFixed(1)}s
          {" · "}
          {/* Null and zero are different facts, so absence shows as a dash. */}
          {generation.usage.total_tokens === null
            ? "— tokens"
            : `${generation.usage.total_tokens} tokens`}
          {generation.attempts > 1 && ` · ${generation.attempts} attempts`}
        </>
      ) : (
        " · no model was contacted"
      )}
    </p>
  );
}
