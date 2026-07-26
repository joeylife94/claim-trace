/**
 * Claim structural parsing client.
 *
 * Requests are made by the Next.js server runtime, matching the rest of the app:
 * the API needs no browser exposure.
 */

import { API_BASE_URL } from "@/lib/api";
import type { SourceLocator } from "@/lib/documents";

export type ClaimParseStatus = "processing" | "completed" | "no_claims_found" | "failed";

export type ClaimType = "independent" | "dependent" | "multiple_dependent" | "unknown";

export type ParseWarning = {
  code: string;
  message: string;
  claim_number: number | null;
};

export type ClaimSpan = {
  sequence_number: number;
  page_number: number;
  start_char: number;
  end_char: number;
  locator: SourceLocator;
};

export type Claim = {
  claim_number: number;
  claim_type: ClaimType;
  text: string;
  depends_on: number[];
  spans: ClaimSpan[];
  crosses_pages: boolean;
};

export type ClaimParseResult = {
  id: string;
  document_id: string;
  status: ClaimParseStatus;
  parser_name: string;
  parser_version: string;
  claim_count: number;
  warning_count: number;
  warnings: ParseWarning[];
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ClaimSet = {
  result: ClaimParseResult;
  claims: Claim[];
};

export type ParseOutcome =
  | { ok: true; claimSet: ClaimSet; alreadyParsed: boolean }
  | { ok: false; detail: string; errorCode: string };

const CLAIM_TYPE_LABELS: Record<ClaimType, string> = {
  independent: "Independent",
  dependent: "Dependent",
  multiple_dependent: "Multiple dependent",
  unknown: "Unknown",
};

export function claimTypeLabel(type: ClaimType): string {
  return CLAIM_TYPE_LABELS[type] ?? type;
}

/** "depends on Claims 1 and 2", or null for an independent claim. */
export function dependencyLabel(depends_on: number[]): string | null {
  if (depends_on.length === 0) return null;
  const noun = depends_on.length === 1 ? "Claim" : "Claims";
  const numbers =
    depends_on.length === 1
      ? String(depends_on[0])
      : `${depends_on.slice(0, -1).join(", ")} and ${depends_on[depends_on.length - 1]}`;
  return `Depends on ${noun} ${numbers}`;
}

/** Fetch the current claim set. A document that has not been parsed yields null. */
export async function getClaims(documentId: string): Promise<ClaimSet | null> {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/claims`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error("Could not load claims");
  }
  return (await response.json()) as ClaimSet;
}

/**
 * Run claim parsing. Rejections are returned rather than thrown: an unparseable
 * document is an expected outcome the page has to render.
 */
export async function parseClaims(documentId: string): Promise<ParseOutcome> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/claims/parse`, {
      method: "POST",
      headers: { Accept: "application/json" },
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
    return {
      ok: true,
      claimSet: payload as ClaimSet,
      // 200 rather than 201 means this parser version had already run.
      alreadyParsed: response.status === 200,
    };
  }

  const error = (payload ?? {}) as { detail?: string; error_code?: string };
  return {
    ok: false,
    detail: error.detail ?? "Claim parsing could not be completed.",
    errorCode: error.error_code ?? String(response.status),
  };
}
