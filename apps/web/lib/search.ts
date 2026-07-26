/**
 * Claim indexing and hybrid retrieval client.
 *
 * Requests are made by the Next.js server runtime, matching the rest of the app:
 * the API needs no browser exposure, and a patent search query never leaves the
 * server it was typed into.
 */

import { API_BASE_URL } from "@/lib/api";
import type { ClaimType } from "@/lib/claims";
import type { SourceLocator } from "@/lib/documents";

export type ClaimIndexStatus = "processing" | "completed" | "failed";

export type RetrievalMode = "hybrid" | "dense" | "lexical";

export const RETRIEVAL_MODES: RetrievalMode[] = ["hybrid", "dense", "lexical"];

/** Mirrors the API's bounds. The server enforces them; these keep the UI honest. */
export const MAX_QUERY_LENGTH = 512;
export const TOP_K_CHOICES = [5, 10, 20, 50] as const;

export type ClaimIndexRun = {
  id: string;
  claim_parse_result_id: string;
  status: ClaimIndexStatus;
  embedding_provider: string;
  embedding_model: string;
  embedding_model_version: string;
  embedding_dimension: number;
  vectors_normalized: boolean;
  normalization_version: string;
  lexical_strategy: string;
  lexical_strategy_version: string;
  indexed_claim_count: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RetrievalProfile = {
  embedding_provider: string;
  embedding_model: string;
  embedding_model_version: string;
  embedding_dimension: number;
  vectors_normalized: boolean;
  normalization_version: string;
  lexical_strategy: string;
  lexical_strategy_version: string;
  rrf_k: number;
};

/**
 * One retrieved claim.
 *
 * Every ranking field except the fused pair is nullable, and that is
 * information rather than an inconvenience: `dense_rank === null` means the
 * dense channel did not retrieve this claim. Render the absence; never coerce
 * it to zero.
 */
export type ClaimSearchResult = {
  document_id: string;
  document_filename: string;
  claim_number: number;
  claim_type: ClaimType;
  text: string;
  depends_on: number[];
  source_spans: SourceLocator[];
  dense_rank: number | null;
  dense_score: number | null;
  lexical_rank: number | null;
  lexical_score: number | null;
  fused_rank: number;
  fused_score: number;
};

export type ClaimSearchResponse = {
  mode: RetrievalMode;
  profile: RetrievalProfile;
  searched_index_run_count: number;
  dense_candidate_count: number;
  lexical_candidate_count: number;
  result_count: number;
  results: ClaimSearchResult[];
};

export type ClaimSearchRequest = {
  query: string;
  mode: RetrievalMode;
  document_ids?: string[];
  top_k?: number;
};

export type IndexOutcome =
  | { ok: true; run: ClaimIndexRun; alreadyIndexed: boolean }
  | { ok: false; detail: string; errorCode: string };

export type SearchOutcome =
  | { ok: true; response: ClaimSearchResponse }
  | { ok: false; detail: string; errorCode: string };

/** Fetch the current index run. A document that has not been indexed yields null. */
export async function getClaimIndex(documentId: string): Promise<ClaimIndexRun | null> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/documents/${documentId}/claims/index`,
    { headers: { Accept: "application/json" }, cache: "no-store" },
  );
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error("Could not load the claim index status");
  }
  return (await response.json()) as ClaimIndexRun;
}

/**
 * Index a document's claims. Rejections are returned rather than thrown: a
 * missing model or an unparsed document is an expected outcome the page renders.
 */
export async function indexClaims(documentId: string): Promise<IndexOutcome> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/api/v1/documents/${documentId}/claims/index`,
      { method: "POST", headers: { Accept: "application/json" }, cache: "no-store" },
    );
  } catch {
    return {
      ok: false,
      detail: "Could not reach the API. Check that the backend is running.",
      errorCode: "api_unreachable",
    };
  }

  const payload: unknown = await response.json().catch(() => null);

  if (response.ok) {
    return {
      ok: true,
      run: payload as ClaimIndexRun,
      // 200 rather than 201 means this retrieval profile had already been built.
      alreadyIndexed: response.status === 200,
    };
  }

  const error = (payload ?? {}) as { detail?: string; error_code?: string };
  return {
    ok: false,
    detail: error.detail ?? "Claim indexing could not be completed.",
    errorCode: error.error_code ?? String(response.status),
  };
}

/** Run a claim search. */
export async function searchClaims(request: ClaimSearchRequest): Promise<SearchOutcome> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/search/claims`, {
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
    return { ok: true, response: payload as ClaimSearchResponse };
  }

  const error = (payload ?? {}) as { detail?: string; error_code?: string };
  return {
    ok: false,
    detail: error.detail ?? "The search could not be completed.",
    errorCode: error.error_code ?? String(response.status),
  };
}

/** "hybrid (dense + lexical, RRF k=60)" — what the reader is actually looking at. */
export function modeLabel(mode: RetrievalMode, rrfK: number): string {
  switch (mode) {
    case "dense":
      return "dense only (vector similarity)";
    case "lexical":
      return "lexical only (full-text + trigram)";
    default:
      return `hybrid (dense + lexical, RRF k=${rrfK})`;
  }
}

/**
 * A score rendered for a channel that did not retrieve the claim must not read
 * as a low score, so absence is shown as an em dash rather than as 0.000.
 */
export function formatScore(score: number | null): string {
  return score === null ? "—" : score.toFixed(3);
}

export function formatRank(rank: number | null): string {
  return rank === null ? "—" : `#${rank}`;
}

/** The deep link into the existing page viewer, with the exact range to highlight. */
export function spanHref(span: SourceLocator): string {
  const parameters = new URLSearchParams({
    page: String(span.page_number),
    start: String(span.start_char),
    end: String(span.end_char),
  });
  return `/documents/${span.document_id}?${parameters.toString()}`;
}
