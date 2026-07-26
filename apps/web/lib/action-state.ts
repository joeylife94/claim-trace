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
