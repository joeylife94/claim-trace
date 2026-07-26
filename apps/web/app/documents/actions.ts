"use server";

import { revalidatePath } from "next/cache";
import { uploadDocument } from "@/lib/documents";

export type UploadState = {
  status: "idle" | "success" | "duplicate" | "error";
  message: string;
  documentId?: string;
};

export const INITIAL_UPLOAD_STATE: UploadState = { status: "idle", message: "" };

/**
 * Handle the upload form.
 *
 * Runs on the server, so the PDF goes browser -> Next.js -> API without the
 * backend being exposed to the browser. Validation errors from the API are
 * surfaced verbatim: they are written for end users and carry no internals.
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
