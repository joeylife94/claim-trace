/**
 * Form state shared between server actions and the client components that call
 * them.
 *
 * These live outside the `"use server"` modules on purpose: such a module may
 * only export async functions. Exporting a constant from one makes Next.js throw
 * `A "use server" file can only export async functions` at runtime, which breaks
 * the whole page rather than just the action.
 */

export type UploadState = {
  status: "idle" | "success" | "duplicate" | "error";
  message: string;
  documentId?: string;
};

export const INITIAL_UPLOAD_STATE: UploadState = { status: "idle", message: "" };

export type ParseClaimsState = {
  status: "idle" | "parsed" | "already_parsed" | "error";
  message: string;
};

export const INITIAL_PARSE_STATE: ParseClaimsState = { status: "idle", message: "" };

export type IndexClaimsState = {
  status: "idle" | "indexed" | "already_indexed" | "error";
  message: string;
};

export const INITIAL_INDEX_STATE: IndexClaimsState = { status: "idle", message: "" };

export type SearchClaimsState = {
  status: "idle" | "results" | "error";
  message: string;
  /**
   * Present only on `status: "results"`. Typed as the search response so the
   * results component needs no cast; `null` while idle or after an error.
   */
  response: import("@/lib/search").ClaimSearchResponse | null;
  /** Echoed back so the form keeps what the user typed after a submission. */
  query: string;
  mode: import("@/lib/search").RetrievalMode;
  documentId: string;
  topK: number;
};

export const INITIAL_SEARCH_STATE: SearchClaimsState = {
  status: "idle",
  message: "",
  response: null,
  query: "",
  mode: "hybrid",
  documentId: "",
  topK: 10,
};
