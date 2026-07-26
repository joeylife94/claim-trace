/**
 * Evidence-grounded answering client.
 *
 * Requests are made by the Next.js server runtime, matching the rest of the app:
 * the API needs no browser exposure, and a question about unpublished patent
 * work never leaves the server it was typed into.
 *
 * Note what this module does *not* export: anything that would let a caller
 * choose a model, a provider, a temperature, or a prompt. The API rejects those
 * fields outright, and offering them here would only produce a 422.
 */

import { API_BASE_URL } from "@/lib/api";
import type { ClaimType } from "@/lib/claims";
import type { SourceLocator } from "@/lib/documents";
import type { RetrievalMode, RetrievalProfile } from "@/lib/search";

/** Mirrors the API's bounds. The server enforces them; these keep the UI honest. */
export const MAX_QUESTION_LENGTH = 512;
export const GROUNDED_TOP_K_CHOICES = [3, 5, 6, 10] as const;

export type InsufficientReason =
  | "no_retrieved_evidence"
  | "evidence_not_specific_enough"
  | "conflicting_evidence"
  | "question_outside_available_documents";

/** One canonical span, with the text the server read at those exact offsets. */
export type GroundedSourceSpan = {
  locator: SourceLocator;
  /**
   * Resolved from stored page text by the server, never reproduced by the
   * model. Render it as text.
   */
  quote: string;
};

export type GroundedEvidence = {
  /** Issued for this request only. Meaningless in any other. */
  evidence_id: string;
  document_id: string;
  document_name: string;
  claim_number: number;
  claim_type: ClaimType;
  depends_on: number[];
  source_spans: GroundedSourceSpan[];
  crosses_pages: boolean;
  fused_rank: number;
  fused_score: number;
  /** Null means the dense channel did not retrieve this claim. Never render 0. */
  dense_rank: number | null;
  dense_score: number | null;
  lexical_rank: number | null;
  lexical_score: number | null;
};

export type GroundedStatement = {
  text: string;
  /** Never empty, and every entry appears in `evidence`. */
  evidence_ids: string[];
};

export type GroundedRetrieval = {
  mode: RetrievalMode;
  profile: RetrievalProfile;
  searched_index_run_count: number;
  retrieved_candidate_count: number;
  included_evidence_count: number;
  omitted_evidence_count: number;
};

/**
 * Token counts, each independently nullable.
 *
 * "Not reported" and "zero" are different facts. A UI that renders a fabricated
 * 0 as a measurement is worse than one that renders a dash.
 */
export type GroundedUsage = {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
};

export type GroundedGenerationMetadata = {
  provider: string;
  model: string;
  model_version: string | null;
  finish_reason: string;
  usage: GroundedUsage;
  duration_seconds: number;
  attempts: number;
  structured_output_mode: string | null;
  warnings: string[];
};

export type GroundedAnswer = {
  /** Composed by the server from validated statements. Plain text, never HTML. */
  answer: string;
  statements: GroundedStatement[];
  evidence: GroundedEvidence[];
  /** True is a normal result, not an error. */
  insufficient_evidence: boolean;
  insufficient_reason: InsufficientReason | null;
  retrieval: GroundedRetrieval;
  /** Null when retrieval returned nothing and no provider was contacted. */
  generation: GroundedGenerationMetadata | null;
  warnings: string[];
};

export type GroundedAnswerRequest = {
  query: string;
  document_ids?: string[];
  mode?: RetrievalMode;
  top_k?: number;
};

export type GroundedOutcome =
  | { ok: true; answer: GroundedAnswer }
  | { ok: false; detail: string; errorCode: string };

/**
 * Ask a grounded question.
 *
 * Rejections are returned rather than thrown: an unreachable model server and a
 * fabricated citation are both expected outcomes the page has to render, not
 * crashes.
 */
export async function askGrounded(
  request: GroundedAnswerRequest,
): Promise<GroundedOutcome> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/grounded/answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
    });
  } catch {
    return {
      ok: false,
      detail: "Could not reach the API. Check that the backend is running.",
      errorCode: "api_unreachable",
    };
  }

  const payload: unknown = await response.json().catch(() => null);

  if (response.ok) {
    return { ok: true, answer: payload as GroundedAnswer };
  }

  const error = (payload ?? {}) as { detail?: string; error_code?: string };
  return {
    ok: false,
    detail: error.detail ?? "The question could not be answered.",
    errorCode: error.error_code ?? String(response.status),
  };
}

/** Operator-facing wording for the closed set of limitation reasons. */
export function insufficientReasonLabel(reason: InsufficientReason | null): string {
  switch (reason) {
    case "no_retrieved_evidence":
      return "Nothing retrieved";
    case "evidence_not_specific_enough":
      return "Evidence not specific enough";
    case "conflicting_evidence":
      return "Conflicting evidence";
    case "question_outside_available_documents":
      return "Outside the indexed documents";
    default:
      return "Insufficient evidence";
  }
}

/**
 * Look one evidence entry up by the id a statement cited.
 *
 * Returns undefined rather than throwing. The API guarantees every cited id is
 * present, but a UI that crashes when a guarantee is broken is worse at telling
 * you the guarantee was broken.
 */
export function findEvidence(
  evidence: GroundedEvidence[],
  evidenceId: string,
): GroundedEvidence | undefined {
  return evidence.find((entry) => entry.evidence_id === evidenceId);
}

/** "3 of 7 retrieved claims were used as evidence" — what the reader is looking at. */
export function evidenceSummary(retrieval: GroundedRetrieval): string {
  const parts = [
    `${retrieval.included_evidence_count} of ${retrieval.retrieved_candidate_count} retrieved claim(s) given to the model`,
  ];
  if (retrieval.omitted_evidence_count > 0) {
    parts.push(`${retrieval.omitted_evidence_count} omitted for context budget`);
  }
  return parts.join(" · ");
}
