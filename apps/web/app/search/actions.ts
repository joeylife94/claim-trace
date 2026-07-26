"use server";

import type { SearchClaimsState } from "@/lib/action-state";
import {
  MAX_QUERY_LENGTH,
  RETRIEVAL_MODES,
  TOP_K_CHOICES,
  searchClaims,
  type RetrievalMode,
} from "@/lib/search";

/**
 * Run a claim search.
 *
 * The bounds checked here mirror the API's, which is the real enforcement point:
 * these exist so a mistyped query produces an immediate, specific message rather
 * than a round trip that comes back as a generic 422.
 *
 * This module exports only async functions - a `"use server"` file may not
 * export anything else, so the state type and its initial value live in
 * `lib/action-state`.
 */
export async function searchClaimsAction(
  _previous: SearchClaimsState,
  formData: FormData,
): Promise<SearchClaimsState> {
  const query = String(formData.get("query") ?? "");
  const documentId = String(formData.get("documentId") ?? "");
  const mode = readMode(formData.get("mode"));
  const topK = readTopK(formData.get("topK"));

  const echo = { query, mode, documentId, topK };

  if (query.trim().length === 0) {
    return { status: "error", message: "Enter a search query.", response: null, ...echo };
  }
  if (query.length > MAX_QUERY_LENGTH) {
    return {
      status: "error",
      message: `Queries are limited to ${MAX_QUERY_LENGTH} characters.`,
      response: null,
      ...echo,
    };
  }

  const outcome = await searchClaims({
    query,
    mode,
    top_k: topK,
    document_ids: documentId ? [documentId] : undefined,
  });

  if (!outcome.ok) {
    return { status: "error", message: outcome.detail, response: null, ...echo };
  }

  const { response } = outcome;

  // Nothing indexed and nothing matched are different situations, and the second
  // one is not fixed by indexing anything.
  const message =
    response.searched_index_run_count === 0
      ? "No claims have been indexed for the current retrieval profile yet."
      : `${response.result_count} result(s).`;

  return { status: "results", message, response, ...echo };
}

function readMode(value: FormDataEntryValue | null): RetrievalMode {
  const candidate = String(value ?? "");
  return (RETRIEVAL_MODES as string[]).includes(candidate)
    ? (candidate as RetrievalMode)
    : "hybrid";
}

function readTopK(value: FormDataEntryValue | null): number {
  const candidate = Number(value);
  return (TOP_K_CHOICES as readonly number[]).includes(candidate) ? candidate : 10;
}
