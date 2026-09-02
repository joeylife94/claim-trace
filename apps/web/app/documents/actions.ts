"use server";

import { revalidatePath } from "next/cache";
import type { RetryDocumentState, UploadState } from "@/lib/action-state";
import { retryDocument, uploadDocument } from "@/lib/documents";

/**
 * Handle the upload form.
 *
 * Runs on the server, so the PDF goes browser -> Next.js -> API without the
 * backend being exposed to the browser. Validation errors from the API are
 * surfaced verbatim: they are written for end users and carry no internals.
 *
 * This module exports only async functions - a `"use server"` file may not
 * export anything else, so the state type and its initial value live in
 * `lib/action-state`.
 */
export async function uploadDocumentAction(
  _previous: UploadState,
  formData: FormData,
): Promise<UploadState> {
  const file = formData.get("file");

  if (!(file instanceof File) || file.size === 0) {
    return { status: "error", message: "Choose a PDF file to upload." };
  }

  const outcome = await uploadDocument(file);

  if (!outcome.ok) {
    return {
      status: "error",
      message: outcome.detail,
      documentId: outcome.document?.id,
    };
  }

  revalidatePath("/documents");

  return outcome.duplicate
    ? {
        status: "duplicate",
        message: `This file was already ingested as “${outcome.document.original_filename}”.`,
        documentId: outcome.document.id,
      }
    : {
        status: "success",
        message: `Ingested ${outcome.document.page_count ?? 0} page(s).`,
        documentId: outcome.document.id,
      };
}

/** Retry one existing failed document through the accepted P8 API contract. */
export async function retryDocumentAction(
  documentId: string,
  _previous: RetryDocumentState,
): Promise<RetryDocumentState> {
  const outcome = await retryDocument(documentId);

  if (!outcome.ok) {
    return { status: "error", message: outcome.detail };
  }

  revalidatePath("/documents");
  revalidatePath(`/documents/${documentId}`);
  return {
    status: "success",
    message: `Retry completed: ${outcome.document.page_count ?? 0} page(s) available.`,
  };
}
