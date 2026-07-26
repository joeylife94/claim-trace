"use server";

import { revalidatePath } from "next/cache";
import type { ParseClaimsState } from "@/lib/action-state";
import { parseClaims } from "@/lib/claims";

/**
 * Run claim structural parsing for one document.
 *
 * Errors from the API are surfaced verbatim: they are written for end users and
 * describe a document problem, not an internal one.
 *
 * This module exports only async functions - a `"use server"` file may not
 * export anything else, so the state type and its initial value live in
 * `lib/action-state`.
 */
export async function parseClaimsAction(
  _previous: ParseClaimsState,
  formData: FormData,
): Promise<ParseClaimsState> {
  const documentId = formData.get("documentId");
  if (typeof documentId !== "string" || documentId.length === 0) {
    return { status: "error", message: "Missing document id." };
  }

  const outcome = await parseClaims(documentId);

  if (!outcome.ok) {
    return { status: "error", message: outcome.detail };
  }

  revalidatePath(`/documents/${documentId}`);

  const { result } = outcome.claimSet;
  if (result.status === "no_claims_found") {
    return {
      status: "parsed",
      message: "No claims were found in this document.",
    };
  }

  return outcome.alreadyParsed
    ? {
        status: "already_parsed",
        message: `Already parsed by ${result.parser_name} ${result.parser_version}.`,
      }
    : {
        status: "parsed",
        message: `Found ${result.claim_count} claim(s).`,
      };
}
