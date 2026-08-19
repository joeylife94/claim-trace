"use server";

import type { ClaimComparisonState } from "@/lib/action-state";
import { COMPARISON_TOP_K_CHOICES, compareClaims } from "@/lib/comparison";
import { RETRIEVAL_MODES, type RetrievalMode } from "@/lib/search";

export async function compareClaimsAction(
  _previous: ClaimComparisonState,
  formData: FormData,
): Promise<ClaimComparisonState> {
  const targetDocumentId = String(formData.get("targetDocumentId") ?? "");
  const referenceDocumentId = String(formData.get("referenceDocumentId") ?? "");
  const targetClaimNumber = readPositiveInteger(formData.get("targetClaimNumber"), 1);
  const mode = readMode(formData.get("mode"));
  const topK = readTopK(formData.get("topK"));

  const echo = {
    targetDocumentId,
    targetClaimNumber,
    referenceDocumentId,
    mode,
    topK,
  };

  if (!targetDocumentId || !referenceDocumentId) {
    return {
      status: "error",
      message: "Choose both a target document and a reference document.",
      response: null,
      ...echo,
    };
  }

  if (targetDocumentId === referenceDocumentId) {
    return {
      status: "error",
      message: "Target and reference documents must be different.",
      response: null,
      ...echo,
    };
  }

  const outcome = await compareClaims({
    target_document_id: targetDocumentId,
    target_claim_number: targetClaimNumber,
    reference_document_id: referenceDocumentId,
    mode,
    top_k: topK,
  });

  if (!outcome.ok) {
    return {
      status: "error",
      message: outcome.detail,
      response: null,
      ...echo,
    };
  }

  const response = outcome.response;
  const message = response.no_correspondence_found
    ? "No corresponding claim was retrieved."
    : `${response.match_count} corresponding claim(s) retrieved.`;

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
  return (COMPARISON_TOP_K_CHOICES as readonly number[]).includes(candidate) ? candidate : 5;
}

function readPositiveInteger(value: FormDataEntryValue | null, fallback: number): number {
  const candidate = Number(value);
  return Number.isInteger(candidate) && candidate > 0 ? candidate : fallback;
}
