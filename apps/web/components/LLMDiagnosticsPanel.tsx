"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { generateStructuredAction, generateTextAction } from "@/app/llm/actions";
import {
  INITIAL_LLM_GENERATE_STATE,
  INITIAL_LLM_STRUCTURED_STATE,
  type LLMGenerateState,
  type LLMStructuredState,
} from "@/lib/action-state";
import {
  MAX_PROMPT_LENGTH,
  MAX_SYSTEM_LENGTH,
  formatDuration,
  formatTokens,
  structuredModeLabel,
  type GenerationMetadata,
  type LLMStatus,
} from "@/lib/llm";

function SubmitButton({ idle, busy }: { idle: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? busy : idle}
    </button>
  );
}

/**
 * Plain and structured generation against the configured provider.
 *
 * This is not a chat interface, and the shape reflects that: two independent
 * one-shot forms, no history, no message list, and no streaming. Each one exists
 * to answer a single operational question - does the provider generate text, and
 * does it honour a schema.
 */
export function LLMDiagnosticsPanel({ status }: { status: LLMStatus }) {
  if (!status.diagnostics_enabled) {
    return (
      <section className="panel" aria-labelledby="diagnostics-heading">
        <div className="panel-header">
          <h2 id="diagnostics-heading">Diagnostics</h2>
          <span className="badge">disabled</span>
        </div>
        <p className="meta">
          The diagnostic generation endpoints are turned off for this deployment.
          They default to on in development and off everywhere else; set{" "}
          <code>LLM_DIAGNOSTICS_ENABLED=true</code> to enable them. Provider status
          above is still reported.
        </p>
      </section>
    );
  }

  return (
    <>
      <PlainGenerationPanel status={status} />
      <StructuredGenerationPanel status={status} />
    </>
  );
}

function PlainGenerationPanel({ status }: { status: LLMStatus }) {
  const [state, formAction] = useActionState<LLMGenerateState, FormData>(
    generateTextAction,
    INITIAL_LLM_GENERATE_STATE,
  );

  return (
    <section className="panel" aria-labelledby="generate-heading">
      <div className="panel-header">
        <h2 id="generate-heading">Plain generation</h2>
        <span className="meta">
          {status.model} · temperature 0 · max {status.max_output_tokens} tokens
        </span>
      </div>

      <form action={formAction} className="search-form">
        <label className="search-field">
          <span>Prompt</span>
          <textarea
            name="prompt"
            rows={3}
            defaultValue={state.prompt}
            maxLength={MAX_PROMPT_LENGTH}
            placeholder="특허 청구항이란 무엇인지 한 문장으로 설명하세요."
            required
          />
        </label>

        <label className="search-field">
          <span>System instruction (optional)</span>
          <input
            type="text"
            name="system"
            defaultValue={state.system}
            maxLength={MAX_SYSTEM_LENGTH}
            placeholder="간결하게 답하세요."
            autoComplete="off"
          />
        </label>

        <div className="search-controls">
          <SubmitButton idle="Generate" busy="Generating…" />
        </div>
      </form>

      {state.status !== "idle" && (
        <p
          className="notice"
          data-tone={state.status === "error" ? "error" : "success"}
          role="status"
        >
          {state.message}
        </p>
      )}

      {state.response && (
        <>
          <p className="claim-text">{state.response.text}</p>
          <MetadataFacts metadata={state.response.metadata} />
        </>
      )}
    </section>
  );
}

function StructuredGenerationPanel({ status }: { status: LLMStatus }) {
  const [state, formAction] = useActionState<LLMStructuredState, FormData>(
    generateStructuredAction,
    INITIAL_LLM_STRUCTURED_STATE,
  );

  return (
    <section className="panel" aria-labelledby="structured-heading">
      <div className="panel-header">
        <h2 id="structured-heading">Structured output smoke test</h2>
        <span className="badge">
          {status.capabilities.structured_output_is_native ? "server-enforced" : "validated only"}
        </span>
      </div>

      <p className="meta">
        Generates JSON against one fixed, built-in schema —{" "}
        <code>{"{ title, keywords[], confidence }"}</code> — then parses and validates
        it. The schema is not caller-supplied. It proves the plumbing works; it is
        not an analysis.
      </p>

      <form action={formAction} className="search-form">
        <label className="search-field">
          <span>Text to summarise</span>
          <textarea
            name="prompt"
            rows={3}
            defaultValue={state.prompt}
            maxLength={MAX_PROMPT_LENGTH}
            placeholder="센서 데이터를 수집하여 무선으로 전송하는 통신 장치."
            required
          />
        </label>

        <div className="search-controls">
          <SubmitButton idle="Run smoke test" busy="Running…" />
        </div>
      </form>

      {state.status !== "idle" && (
        <p
          className="notice"
          data-tone={state.status === "error" ? "error" : "success"}
          role="status"
        >
          {state.message}
        </p>
      )}

      {state.response && (
        <>
          <dl className="rank-facts">
            <Fact label="title" value={state.response.result.title} />
            <Fact
              label="keywords"
              value={
                state.response.result.keywords.length > 0
                  ? state.response.result.keywords.join(", ")
                  : "—"
              }
            />
            <Fact label="confidence" value={state.response.result.confidence.toFixed(2)} />
          </dl>
          <MetadataFacts metadata={state.response.metadata} />
        </>
      )}
    </section>
  );
}

/**
 * How the answer was produced.
 *
 * Warnings are rendered rather than swallowed: a prompt-only JSON fallback
 * produces a correct-looking result that the server never enforced, and the
 * reader has to be able to tell that apart from a guaranteed one.
 */
function MetadataFacts({ metadata }: { metadata: GenerationMetadata }) {
  return (
    <>
      <dl className="rank-facts">
        <Fact label="Model" value={metadata.model} />
        <Fact label="Duration" value={formatDuration(metadata.duration_seconds)} />
        <Fact label="Finish" value={metadata.finish_reason} />
        <Fact label="Input tokens" value={formatTokens(metadata.usage.input_tokens)} />
        <Fact label="Output tokens" value={formatTokens(metadata.usage.output_tokens)} />
        <Fact label="Total tokens" value={formatTokens(metadata.usage.total_tokens)} />
        <Fact label="Attempts" value={String(metadata.attempts)} />
        <Fact label="Mode" value={structuredModeLabel(metadata.structured_output_mode)} />
      </dl>

      {metadata.warnings.length > 0 && (
        <ul className="claim-dependencies">
          {metadata.warnings.map((warning) => (
            <li key={warning}>
              <span className="notice" data-tone="error" role="status">
                {warning}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
