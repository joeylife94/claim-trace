"use server";

import type { LLMGenerateState, LLMStructuredState } from "@/lib/action-state";
import {
  MAX_PROMPT_LENGTH,
  MAX_SYSTEM_LENGTH,
  generateStructured,
  generateText,
} from "@/lib/llm";

/**
 * Run one plain-text diagnostic generation.
 *
 * The bounds checked here mirror the API's, which is the real enforcement point:
 * these exist so an over-long prompt produces an immediate, specific message
 * rather than a round trip that comes back as a generic 422.
 *
 * This module exports only async functions - a `"use server"` file may not
 * export anything else, so the state types and their initial values live in
 * `lib/action-state`.
 */
export async function generateTextAction(
  _previous: LLMGenerateState,
  formData: FormData,
): Promise<LLMGenerateState> {
  const prompt = String(formData.get("prompt") ?? "");
  const system = String(formData.get("system") ?? "");
  const echo = { prompt, system };

  if (prompt.trim().length === 0) {
    return { status: "error", message: "Enter a prompt.", response: null, ...echo };
  }
  if (prompt.length > MAX_PROMPT_LENGTH) {
    return {
      status: "error",
      message: `Prompts are limited to ${MAX_PROMPT_LENGTH} characters.`,
      response: null,
      ...echo,
    };
  }
  if (system.length > MAX_SYSTEM_LENGTH) {
    return {
      status: "error",
      message: `System instructions are limited to ${MAX_SYSTEM_LENGTH} characters.`,
      response: null,
      ...echo,
    };
  }

  const outcome = await generateText({
    prompt,
    system: system.trim() ? system : undefined,
    // Fixed at greedy decoding: a diagnostic exists to be reproducible, and the
    // model is not being asked to be creative.
    temperature: 0,
  });

  if (!outcome.ok) {
    return {
      status: "error",
      message: `${outcome.detail} (${outcome.errorCode})`,
      response: null,
      ...echo,
    };
  }

  return {
    status: "generated",
    message: `Generated in ${outcome.response.metadata.duration_seconds.toFixed(2)}s.`,
    response: outcome.response,
    ...echo,
  };
}

/**
 * Run the fixed structured-output smoke test.
 *
 * The schema is not selectable and is not sent from here: the API validates
 * against one built-in model. This action proves schema-constrained decoding
 * works end to end, and nothing more.
 */
export async function generateStructuredAction(
  _previous: LLMStructuredState,
  formData: FormData,
): Promise<LLMStructuredState> {
  const prompt = String(formData.get("prompt") ?? "");

  if (prompt.trim().length === 0) {
    return { status: "error", message: "Enter a prompt.", response: null, prompt };
  }
  if (prompt.length > MAX_PROMPT_LENGTH) {
    return {
      status: "error",
      message: `Prompts are limited to ${MAX_PROMPT_LENGTH} characters.`,
      response: null,
      prompt,
    };
  }

  const outcome = await generateStructured({ prompt, temperature: 0 });

  if (!outcome.ok) {
    return {
      status: "error",
      message: `${outcome.detail} (${outcome.errorCode})`,
      response: null,
      prompt,
    };
  }

  return {
    status: "generated",
    message: "The response was parsed and validated against the built-in schema.",
    response: outcome.response,
    prompt,
  };
}
