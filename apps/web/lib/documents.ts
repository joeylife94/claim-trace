/**
 * Document ingestion client.
 *
 * Requests are made by the Next.js server runtime, not the browser, so the API
 * needs no public exposure and the upload never crosses an extra origin.
 */

import { API_BASE_URL } from "@/lib/api";

export type DocumentStatus = "uploaded" | "processing" | "completed" | "failed";

export type DocumentRecord = {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  page_count: number | null;
  extracted_character_count: number | null;
  parser_name: string | null;
  parser_version: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentListResponse = {
  items: DocumentRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type SourceLocator = {
  document_id: string;
  page_number: number;
  start_char: number;
  end_char: number;
};

export type DocumentPage = {
  id: string;
  document_id: string;
  page_number: number;
  text: string;
  character_count: number;
  text_sha256: string;
  created_at: string;
  locator: SourceLocator;
};

export type DocumentPageListResponse = {
  document_id: string;
  items: DocumentPage[];
  total: number;
  limit: number;
  offset: number;
};

/** Error envelope returned by the ingestion endpoints. */
export type IngestionErrorBody = {
  detail: string;
  error_code: string;
  document?: DocumentRecord | null;
};

export type UploadOutcome =
  | { ok: true; document: DocumentRecord; duplicate: boolean }
  | { ok: false; detail: string; errorCode: string; document: DocumentRecord | null };

export type RetryOutcome =
  | { ok: true; document: DocumentRecord }
  | { ok: false; detail: string; errorCode: string; document: DocumentRecord | null };

/** Upload one PDF. Rejections are returned, not thrown: they are expected outcomes. */
export async function uploadDocument(file: File): Promise<UploadOutcome> {
  const body = new FormData();
  body.append("file", file, file.name);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
      method: "POST",
      body,
      cache: "no-store",
    });
  } catch {
    return {
      ok: false,
      detail: "Could not reach the API. Check that the backend is running.",
      errorCode: "api_unreachable",
      document: null,
    };
  }

  const payload: unknown = await response.json().catch(() => null);

  if (response.ok) {
    return {
      ok: true,
      document: payload as DocumentRecord,
      // 200 rather than 201 means the digest already existed.
      duplicate: response.status === 200,
    };
  }

  const error = (payload ?? {}) as Partial<IngestionErrorBody>;
  return {
    ok: false,
    detail: error.detail ?? "The upload could not be processed.",
    errorCode: error.error_code ?? String(response.status),
    document: error.document ?? null,
  };
}

/** Retry one terminal failed ingestion using the backend's persisted original. */
export async function retryDocument(id: string): Promise<RetryOutcome> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/documents/${id}/retry`, {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    return {
      ok: false,
      detail: "Could not reach the API. Check that the backend is running.",
      errorCode: "api_unreachable",
      document: null,
    };
  }

  const payload: unknown = await response.json().catch(() => null);
  if (response.ok) {
    return { ok: true, document: payload as DocumentRecord };
  }

  const error = (payload ?? {}) as Partial<IngestionErrorBody>;
  return {
    ok: false,
    detail: error.detail ?? "The document could not be retried.",
    errorCode: error.error_code ?? String(response.status),
    document: error.document ?? null,
  };
}

export async function listDocuments(limit = 20): Promise<DocumentListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents?limit=${limit}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Could not load documents");
  }
  return (await response.json()) as DocumentListResponse;
}

export async function getDocument(id: string): Promise<DocumentRecord | null> {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${id}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error("Could not load the document");
  }
  return (await response.json()) as DocumentRecord;
}

export async function getDocumentPages(id: string): Promise<DocumentPageListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${id}/pages?limit=200`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Could not load the document pages");
  }
  return (await response.json()) as DocumentPageListResponse;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTimestamp(iso: string): string {
  return `${new Date(iso).toISOString().slice(0, 19).replace("T", " ")} UTC`;
}
