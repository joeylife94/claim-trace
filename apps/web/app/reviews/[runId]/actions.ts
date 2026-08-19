"use server";

import { redirect } from "next/navigation";
import { addElementReview, type ReviewStatus } from "@/lib/claim-elements";

const REVIEW_STATUSES: ReviewStatus[] = ["accepted", "needs_correction"];

export async function submitElementReviewAction(
  runId: string,
  formData: FormData,
): Promise<void> {
  const candidate = String(formData.get("status") ?? "");
  if (!REVIEW_STATUSES.includes(candidate as ReviewStatus)) {
    redirect(`/reviews/${runId}?review_error=Choose+a+valid+review+state.`);
  }

  const outcome = await addElementReview(runId, candidate as ReviewStatus);
  if (!outcome.ok) {
    const parameters = new URLSearchParams({ review_error: outcome.detail });
    redirect(`/reviews/${runId}?${parameters.toString()}`);
  }

  redirect(`/reviews/${runId}?review_saved=${candidate}`);
}
