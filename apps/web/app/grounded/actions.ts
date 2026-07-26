"use server";

import type { GroundedAnswerState } from "@/lib/action-state";
import {
  GROUNDED_TOP_K_CHOICES,
  MAX_QUESTION_LENGTH,
  askGrounded,
} from "@/lib/grounded";
import { RETRIEVAL_MODES, type RetrievalMode } from "@/lib/search";

/**
 * Ask one grounded question.
 *
 * The bounds checked here mirror the API's, which is the real enforcement point:
 * these exist so a mistyped question produces an immediate, specific message
 * rather than a round trip that comes back as a generic 422.
 *
 * This module exports only async functions - a `"use server"` file may not
 * export anything else, so the state type and its initial value live in
 * `lib/action-state`.
 */
export async function askGroundedAction(
  _previous: GroundedAnswerState,
  formData: FormData,
): Promise<GroundedAnswerState> {
  const question = String(formData.get("question") ?? "");
  const documentId = String(formData.get("documentId") ?? "");
  const mode = readMode(formData.get("mode"));
  const topK = readTopK(formData.get("topK"));

  const echo = { question, mode, documentId, topK };

  if (question.trim().length === 0) {
    return { status: "error", message: "Enter a question.", answer: null, ...echo };
  }
  if (question.length > MAX_QUESTION_LENGTH) {
    return {
      status: "error",
      message: `Questions are limited to ${MAX_QUESTION_LENGTH} characters.`,
      answer: null,
      ...echo,
    };
  }

  const outcome = await askGrounded({
    query: question,
    mode,
    top_k: topK,
    document_ids: documentId ? [documentId] : undefined,
  });

  if (!outcome.ok) {
    return { status: "error", message: outcome.detail, answer: null, ...echo };
  }

  const { answer } = outcome;

  // Insufficient evidence is a successful answer, so it is reported as one.
  // Rendering it as an error would train a reader to dismiss the most honest
  // thing this system says.
  const message = answer.insufficient_evidence
    ? "The retrieved claims do not answer this question."
    : `${answer.statements.length} supported statement(s), ${answer.evidence.length} cited claim(s).`;

  return { status: "answered", message, answer, ...echo };
}

function readMode(value: FormDataEntryValue | null): RetrievalMode {
  const candidate = String(value ?? "");
  return (RETRIEVAL_MODES as string[]).includes(candidate)
    ? (candidate as RetrievalMode)
    : "hybrid";
}

function readTopK(value: FormDataEntryValue | null): number {
  const candidate = Number(value);
  return (GROUNDED_TOP_K_CHOICES as readonly number[]).includes(candidate) ? candidate : 6;
}
