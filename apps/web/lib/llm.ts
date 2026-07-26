/**
 * Local LLM provider diagnostics client.
 *
 * Requests are made by the Next.js server runtime, matching the rest of the app.
 * That is not incidental here: a diagnostic prompt is typed by an operator and
 * sent to a model, and keeping the call server-side means it never crosses the
 * browser boundary and the API needs no public exposure.
 */

import { API_BASE_URL } from "@/lib/api";

/** Mirrors the API's bounds. The server enforces them; these keep the UI honest. */
export const MAX_PROMPT_LENGTH = 8000;
export const MAX_SYSTEM_LENGTH = 2000;

export type StructuredOutputMode =
  | "native_json_schema"
  | "native_json_object"
  | "prompt_constrained_json"
  | "unsupported";

export type ProviderCapabilities = {
  supports_text_generation: boolean;
  supports_structured_output: boolean;
  structured_output_mode: StructuredOutputMode;
  /** Whether the *server* enforces the schema, or the prompt merely asks for it. */
  structured_output_is_native: boolean;
  supports_seed: boolean;
  supports_usage_metadata: boolean;
  supports_model_listing: boolean;
  supports_streaming: boolean;
};

export type TimeoutConfig = {
  connect_seconds: number;
  read_seconds: number;
  max_seconds: number;
};

/**
 * Four independent booleans rather than one status string.
 *
 * `available === true` with `model_available === false` is a real and common
 * state - the server is up but the model was never pulled - and it has a
 * completely different fix from an unreachable server. Collapsing them would
 * throw away the only information an operator actually needs.
 */
export type LLMStatus = {
  provider: string;
  model: string;
  model_version: string | null;
  /** Already stripped of any userinfo by the API. Null for the fake provider. */
  base_url: string | null;
  transport: string;
  configured: boolean;
  available: boolean;
  model_available: boolean;
  detail: string;
  error_code: string | null;
  health_check_duration_seconds: number;
  capabilities: ProviderCapabilities;
  timeouts: TimeoutConfig;
  retry_max_attempts: number;
  max_prompt_characters: number;
  max_output_tokens: number;
  diagnostics_enabled: boolean;
};

/**
 * Every count is nullable, and that is information rather than an inconvenience:
 * `null` means the provider did not report it. Render the absence; never coerce
 * it to zero, which would read as a measurement.
 */
export type TokenUsage = {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
};

export type GenerationMetadata = {
  provider: string;
  model: string;
  model_version: string | null;
  finish_reason: string;
  usage: TokenUsage;
  duration_seconds: number;
  attempts: number;
  structured_output_mode: StructuredOutputMode | null;
  warnings: string[];
};

export type GenerateResponse = {
  text: string;
  metadata: GenerationMetadata;
};

/** The one built-in smoke-test schema. Deliberately trivial and non-legal. */
export type SmokeTestResult = {
  title: string;
  keywords: string[];
  confidence: number;
};

export type StructuredResponse = {
  result: SmokeTestResult;
  metadata: GenerationMetadata;
};

export type GenerateOutcome =
  | { ok: true; response: GenerateResponse }
  | { ok: false; detail: string; errorCode: string };

export type StructuredOutcome =
  | { ok: true; response: StructuredResponse }
  | { ok: false; detail: string; errorCode: string };

/**
 * Fetch provider status. Never throws: an unreachable API is a state the page
 * renders, exactly as an unreachable model server is.
 */
export async function getLLMStatus(): Promise<LLMStatus | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/llm/status`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as LLMStatus;
  } catch {
    return null;
  }
}

type DiagnosticRequest = {
  prompt: string;
  system?: string;
  temperature?: number;
  max_output_tokens?: number;
};

async function post<T>(
  path: string,
  body: DiagnosticRequest,
): Promise<{ ok: true; response: T } | { ok: false; detail: string; errorCode: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return {
      ok: false,
      detail: "Could not reach the API. Check that the backend is running.",
      errorCode: "api_unreachable",
    };
  }

  const payload: unknown = await response.json().catch(() => null);

  if (response.ok) {
    return { ok: true, response: payload as T };
  }

  // 422 from FastAPI's own validation has a different shape from the
  // application's { detail, error_code } envelope, so both are handled.
  const error = (payload ?? {}) as { detail?: unknown; error_code?: string };
  return {
    ok: false,
    detail:
      typeof error.detail === "string"
        ? error.detail
        : "The request was rejected. Check the prompt length and options.",
    errorCode: error.error_code ?? String(response.status),
  };
}

export const generateText = (body: DiagnosticRequest) =>
  post<GenerateResponse>("/api/v1/llm/diagnostics/generate", body);

export const generateStructured = (body: DiagnosticRequest) =>
  post<StructuredResponse>("/api/v1/llm/diagnostics/structured", body);

/** "not reported" and "zero" are different facts; only one is a measurement. */
export function formatTokens(count: number | null): string {
  return count === null ? "—" : String(count);
}

export function formatDuration(seconds: number): string {
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(2)} s`;
}

/** How the reader should read a structured result: enforced, or merely asked for. */
export function structuredModeLabel(mode: StructuredOutputMode | null): string {
  switch (mode) {
    case "native_json_schema":
      return "native JSON Schema (enforced by the server)";
    case "native_json_object":
      return "native JSON object (valid JSON guaranteed, schema not enforced)";
    case "prompt_constrained_json":
      return "prompt-constrained (requested in the prompt, validated on arrival)";
    case "unsupported":
      return "unsupported";
    default:
      return "plain text";
  }
}

export function providerStateLabel(status: LLMStatus): {
  tone: "ok" | "warn" | "error";
  label: string;
} {
  if (!status.available) {
    return { tone: "error", label: "unreachable" };
  }
  if (!status.model_available) {
    return { tone: "warn", label: "model missing" };
  }
  return { tone: "ok", label: "ready" };
}
