"use server";

import { redirect } from "next/navigation";
import { decomposeClaimElements } from "@/lib/claim-elements";

export async function decomposeAndReviewAction(formData: FormData): Promise<void> {
  const documentId = String(formData.get("documentId") ?? "");
  const claimNumber = Number(formData.get("claimNumber"));

  if (!documentId || !Number.isInteger(claimNumber) || claimNumber < 1) {
    return;
  }

  const outcome = await decomposeClaimElements(documentId, claimNumber);
  if (!outcome.ok) {
    const parameters = new URLSearchParams({
      review_error: outcome.detail,
    });
    redirect(`/documents/${documentId}?${parameters.toString()}`);
  }

  redirect(`/reviews/${outcome.value.id}`);
}
