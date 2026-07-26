"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { uploadDocumentAction } from "@/app/documents/actions";
import { INITIAL_UPLOAD_STATE, type UploadState } from "@/lib/action-state";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? "Uploading…" : "Upload"}
    </button>
  );
}

export function UploadForm({ maxBytes }: { maxBytes: number }) {
  const [state, formAction] = useActionState<UploadState, FormData>(
    uploadDocumentAction,
    INITIAL_UPLOAD_STATE,
  );

  return (
    <section className="panel" aria-labelledby="upload-heading">
      <div className="panel-header">
        <h2 id="upload-heading">Upload a document</h2>
      </div>

      <form action={formAction} className="upload-form">
        <input
          type="file"
          name="file"
          accept="application/pdf,.pdf"
          required
          aria-describedby="upload-hint"
        />
        <SubmitButton />
      </form>

      <p id="upload-hint" className="meta">
        Text-based PDFs only, up to {Math.round(maxBytes / (1024 * 1024))} MB. Scanned or
        image-only PDFs are rejected: this phase does not perform OCR.
      </p>

      {state.status !== "idle" && (
        <p className="notice" data-tone={state.status} role="status">
          {state.message}
          {state.documentId && (
            <>
              {" "}
              <Link href={`/documents/${state.documentId}`}>View document</Link>
            </>
          )}
        </p>
      )}
    </section>
  );
}
