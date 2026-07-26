import Link from "next/link";
import { LLMDiagnosticsPanel } from "@/components/LLMDiagnosticsPanel";
import { getLLMStatus, providerStateLabel, type LLMStatus } from "@/lib/llm";

export const dynamic = "force-dynamic";

export default async function LLMPage() {
  // Never throws: an unreachable API is a state this page renders, exactly as an
  // unreachable model server is.
  const status = await getLLMStatus();

  return (
    <>
      <main>
        <p className="eyebrow">
          <Link href="/">ClaimTrace</Link> · LLM
        </p>
        <h1 className="document-title">Local LLM provider</h1>
        <p className="tagline">
          Configuration, reachability, and capabilities of the configured local
          model provider, with development diagnostics for plain and
          schema-constrained generation. This is infrastructure, not analysis: the
          model is not connected to claim retrieval.
        </p>

        {status === null ? (
          <section className="panel">
            <p className="notice" data-tone="error" role="status">
              Could not reach the API. Check that the backend is running.
            </p>
          </section>
        ) : (
          <>
            <StatusPanel status={status} />
            <LLMDiagnosticsPanel status={status} />
          </>
        )}
      </main>
      <footer>
        MVP portfolio project. Generated text is model output, not a legal
        opinion, and the small model used to validate this provider boundary is
        not fit for patent analysis. ClaimTrace does not provide legal advice and
        does not determine infringement, validity, novelty, or patentability.
      </footer>
    </>
  );
}

function StatusPanel({ status }: { status: LLMStatus }) {
  const state = providerStateLabel(status);

  return (
    <section className="panel" aria-labelledby="status-heading">
      <div className="panel-header">
        <h2 id="status-heading">Provider</h2>
        <span className="badge" data-tone={state.tone}>
          {state.label}
        </span>
      </div>

      <p className="notice" data-tone={state.tone === "ok" ? "success" : "error"} role="status">
        {status.detail}
      </p>

      <dl className="rank-facts">
        <Fact label="Provider" value={status.provider} />
        <Fact label="Model" value={status.model} />
        <Fact label="Model version" value={status.model_version ?? "—"} />
        {/* Reported by the API with any userinfo already removed. */}
        <Fact label="Base URL" value={status.base_url ?? "in-process"} />
        <Fact label="Transport" value={status.transport} />
        <Fact label="Reachable" value={yesNo(status.available)} />
        <Fact label="Model available" value={yesNo(status.model_available)} />
        <Fact label="Error code" value={status.error_code ?? "—"} />
      </dl>

      <div className="panel-header">
        <h3>Capabilities</h3>
      </div>
      <dl className="rank-facts">
        <Fact label="Text generation" value={yesNo(status.capabilities.supports_text_generation)} />
        <Fact label="Structured output" value={status.capabilities.structured_output_mode} />
        {/*
          "Supported" and "enforced by the server" are different claims. A
          prompt-constrained mode supports structured output and guarantees
          nothing, so the distinction is shown rather than flattened.
        */}
        <Fact
          label="Schema enforced"
          value={yesNo(status.capabilities.structured_output_is_native)}
        />
        <Fact label="Seed" value={yesNo(status.capabilities.supports_seed)} />
        <Fact label="Usage metadata" value={yesNo(status.capabilities.supports_usage_metadata)} />
        <Fact label="Model listing" value={yesNo(status.capabilities.supports_model_listing)} />
        <Fact label="Streaming" value={yesNo(status.capabilities.supports_streaming)} />
      </dl>

      <div className="panel-header">
        <h3>Limits</h3>
      </div>
      <dl className="rank-facts">
        <Fact label="Connect timeout" value={`${status.timeouts.connect_seconds}s`} />
        <Fact label="Read timeout" value={`${status.timeouts.read_seconds}s`} />
        <Fact label="Max timeout" value={`${status.timeouts.max_seconds}s`} />
        <Fact label="Max attempts" value={String(status.retry_max_attempts)} />
        <Fact label="Max prompt" value={`${status.max_prompt_characters} chars`} />
        <Fact label="Max output" value={`${status.max_output_tokens} tokens`} />
        <Fact label="Diagnostics" value={status.diagnostics_enabled ? "enabled" : "disabled"} />
        <Fact
          label="Health check"
          value={`${(status.health_check_duration_seconds * 1000).toFixed(0)} ms`}
        />
      </dl>
    </section>
  );
}

function yesNo(value: boolean): string {
  return value ? "yes" : "no";
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
