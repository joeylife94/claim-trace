"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { retryDocumentAction } from "@/app/documents/actions";
import {
  INITIAL_RETRY_DOCUMENT_STATE,
  type RetryDocumentState,
} from "@/lib/action-state";

function RetryButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? "Retrying…" : "Retry ingestion"}
    </button>
  );
}

export function RetryDocumentForm({ documentId }: { documentId: string }) {
  const action = retryDocumentAction.bind(null, documentId);
  const [state, formAction] = useActionState<RetryDocumentState, void>(
    action,
    INITIAL_RETRY_DOCUMENT_STATE,
  );

  return (
    <div>
      <form action={formAction}>
        <RetryButton />
      </form>
      {state.status !== "idle" && (
        <p className="row-note" role="status" data-tone={state.status}>
          {state.message}
        </p>
      )}
    </div>
  );
}
