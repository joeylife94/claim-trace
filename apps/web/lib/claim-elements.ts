import { API_BASE_URL } from "@/lib/api";
import type { SourceLocator } from "@/lib/documents";

export type ReviewStatus = "accepted" | "needs_correction";

export type ClaimElementSpan = {
  sequence_number: number;
  page_number: number;
  start_char: number;
  end_char: number;
  locator: SourceLocator;
};

export type ClaimElement = {
  id: string;
  sequence_number: number;
  text: string;
  spans: ClaimElementSpan[];
};

export type ElementDecompositionResponse = {
  id: string;
  claim_id: string;
  parser_name: string;
  parser_version: string;
  element_count: number;
  warning_count: number;
  warnings: { code: string; message: string }[];
  elements: ClaimElement[];
  created_at: string;
};

export type ElementReview = {
  id: string;
  status: ReviewStatus;
  created_at: string;
};

export type ElementReviewSnapshot = {
  run_id: string;
  claim_id: string;
  document_id: string;
  parser_name: string;
  parser_version: string;
  elements: ClaimElement[];
  reviews: ElementReview[];
};

export type ElementActionOutcome<T> =
  | { ok: true; value: T }
  | { ok: false; detail: string; errorCode: string };

async function requestJson<T>(
  path: string,
  init: RequestInit,
): Promise<ElementActionOutcome<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
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
    return { ok: true, value: payload as T };
  }

  const error = (payload ?? {}) as { detail?: string; error_code?: string };
  return {
    ok: false,
    detail:
      typeof error.detail === "string"
        ? error.detail
        : "The claim element request could not be completed.",
    errorCode: error.error_code ?? String(response.status),
  };
}

export function decomposeClaimElements(
  documentId: string,
  claimNumber: number,
): Promise<ElementActionOutcome<ElementDecompositionResponse>> {
  return requestJson(
    `/api/v1/documents/${documentId}/claims/${claimNumber}/elements/decompose`,
    { method: "POST" },
  );
}

export function getElementReviews(
  runId: string,
): Promise<ElementActionOutcome<ElementReviewSnapshot>> {
  return requestJson(`/api/v1/element-decomposition-runs/${runId}/reviews`, {
    method: "GET",
  });
}

export function addElementReview(
  runId: string,
  status: ReviewStatus,
): Promise<ElementActionOutcome<ElementReviewSnapshot>> {
  return requestJson(`/api/v1/element-decomposition-runs/${runId}/reviews`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}
