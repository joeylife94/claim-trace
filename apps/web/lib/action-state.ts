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

export type RetryDocumentState = {
  status: "idle" | "success" | "error";
  message: string;
};

export const INITIAL_RETRY_DOCUMENT_STATE: RetryDocumentState = {
  status: "idle",
  message: "",
};

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

export type ClaimComparisonState = {
  status: "idle" | "results" | "error";
  message: string;
  response: import("@/lib/comparison").ClaimComparisonResponse | null;
  targetDocumentId: string;
  targetClaimNumber: number;
  referenceDocumentId: string;
  mode: import("@/lib/search").RetrievalMode;
  topK: number;
};

export const INITIAL_COMPARISON_STATE: ClaimComparisonState = {
  status: "idle",
  message: "",
  response: null,
  targetDocumentId: "",
  targetClaimNumber: 1,
  referenceDocumentId: "",
  mode: "hybrid",
  topK: 5,
};

export type LLMGenerateState = {
  status: "idle" | "generated" | "error";
  message: string;
  /** Present only on `status: "generated"`; null while idle or after an error. */
  response: import("@/lib/llm").GenerateResponse | null;
  /** Echoed back so the operator keeps what they typed. */
  prompt: string;
  system: string;
};

export const INITIAL_LLM_GENERATE_STATE: LLMGenerateState = {
  status: "idle",
  message: "",
  response: null,
  prompt: "",
  system: "",
};

export type LLMStructuredState = {
  status: "idle" | "generated" | "error";
  message: string;
  response: import("@/lib/llm").StructuredResponse | null;
  prompt: string;
};

export const INITIAL_LLM_STRUCTURED_STATE: LLMStructuredState = {
  status: "idle",
  message: "",
  response: null,
  prompt: "",
};

export type GroundedAnswerState = {
  status: "idle" | "answered" | "error";
  message: string;
  /** Present only on `status: "answered"`; null while idle or after an error. */
  answer: import("@/lib/grounded").GroundedAnswer | null;
  /** Echoed back so the user keeps what they asked after a submission. */
  question: string;
  mode: import("@/lib/search").RetrievalMode;
  documentId: string;
  topK: number;
};

export const INITIAL_GROUNDED_STATE: GroundedAnswerState = {
  status: "idle",
  message: "",
  answer: null,
  question: "",
  mode: "hybrid",
  documentId: "",
  topK: 6,
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
