import { API_BASE_URL, type Probe, type SystemStatus } from "@/lib/api";
import { RefreshButton } from "@/components/RefreshButton";

/**
 * Renders the operational state reported by the API. Every value is fetched from
 * the backend by the page's server component; nothing here is hardcoded.
 */
export function SystemStatusPanel({ status }: { status: SystemStatus }) {
  return (
    <section className="panel" aria-labelledby="system-status-heading">
      <div className="panel-header">
        <h2 id="system-status-heading">System status</h2>
        <span className="status-value">checked {status.checkedAt}</span>
      </div>

      <ul className="status-list">
        <StatusRow label="API health" probe={status.api} />
        <StatusRow label="PostgreSQL readiness" probe={status.postgres} />
      </ul>

      <p className="meta">
        {status.info
          ? `${status.info.name} v${status.info.version} · ${status.info.environment}`
          : "Application information unavailable"}
        {" · "}
        <code>{API_BASE_URL}</code>
      </p>

      <div className="actions">
        <RefreshButton />
      </div>
    </section>
  );
}

function StatusRow({ label, probe }: { label: string; probe: Probe }) {
  return (
    <li className="status-row">
      <span className="status-label">{label}</span>
      <span className="status-value">
        <span className="dot" data-state={probe.state} aria-hidden="true" />
        {probe.detail}
      </span>
    </li>
  );
}
