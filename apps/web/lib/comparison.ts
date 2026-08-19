/**
 * Bounded two-document claim comparison client.
 *
 * Requests are executed by the Next.js server runtime and mirror the API's
 * closed V1-02 contract. This module does not infer legal similarity; it only
 * renders textual retrieval correspondence and canonical source provenance.
 */

import { API_BASE_URL } from "@/lib/api";
import type { ClaimType } from "@/lib/claims";
import type { SourceLocator } from "@/lib/documents";
import type { RetrievalMode, RetrievalProfile } from "@/lib/search";

export const COMPARISON_TOP_K_CHOICES = [3, 5, 10, 20] as const;

export type ComparisonClaim = {
  document_id: string;
  claim_number: number;
  claim_type: ClaimType;
  text: string;
  depends_on: number[];
  source_spans: SourceLocator[];
};

export type ComparisonMatch = ComparisonClaim & {
  dense_rank: number | null;
  dense_score: number | null;
  lexical_rank: number | null;
  lexical_score: number | null;
  fused_rank: number;
  fused_score: number;
};

export type NoCorrespondenceReason = "reference_not_indexed" | "no_matches";

export type ClaimComparisonResponse = {
  target: ComparisonClaim;
  reference_document_id: string;
  mode: RetrievalMode;
  profile: RetrievalProfile;
  searched_index_run_count: number;
  no_correspondence_found: boolean;
  no_correspondence_reason: NoCorrespondenceReason | null;
  match_count: number;
  matches: ComparisonMatch[];
};

export type ClaimComparisonRequest = {
  target_document_id: string;
  target_claim_number: number;
  reference_document_id: string;
  mode: RetrievalMode;
  top_k: number;
};

export type ComparisonOutcome =
  | { ok: true; response: ClaimComparisonResponse }
  | { ok: false; detail: string; errorCode: string };

export async function compareClaims(
  request: ClaimComparisonRequest,
): Promise<ComparisonOutcome> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/compare/claims`, {
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
    return { ok: true, response: payload as ClaimComparisonResponse };
  }

  const error = (payload ?? {}) as { detail?: string; error_code?: string };
  return {
    ok: false,
    detail: error.detail ?? "The claim comparison could not be completed.",
    errorCode: error.error_code ?? String(response.status),
  };
}

export function noCorrespondenceLabel(reason: NoCorrespondenceReason | null): string {
  switch (reason) {
    case "reference_not_indexed":
      return "The reference document has not been indexed yet.";
    case "no_matches":
      return "No corresponding claim was retrieved from the reference document.";
    default:
      return "No corresponding claim was found.";
  }
}
