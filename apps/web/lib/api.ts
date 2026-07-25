/**
 * Thin client for the ClaimTrace API.
 *
 * Status is fetched by the server component that renders the landing page, so the
 * base URL resolves to the API address reachable from the web runtime
 * (`http://api:8000` inside Docker). `NEXT_PUBLIC_API_BASE_URL` is the fallback and
 * the value any future browser-side call would use.
 */

const stripTrailingSlash = (url: string) => url.replace(/\/$/, "");

export const API_BASE_URL = stripTrailingSlash(
  process.env.API_INTERNAL_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000",
);

export type HealthResponse = {
  status: string;
};

export type DependencyStatus = "ok" | "unavailable";

export type ReadinessResponse = {
  status: string;
  dependencies: Record<string, DependencyStatus>;
};

export type SystemInfoResponse = {
  name: string;
  version: string;
  environment: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly statusCode?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Fetch JSON from the API.
 *
 * `/ready` answers 503 with a valid body when a dependency is down, so callers can
 * opt into reading non-2xx payloads via `acceptStatuses`.
 */
export async function fetchJson<T>(
  path: string,
  options: { acceptStatuses?: number[] } = {},
): Promise<T> {
  const { acceptStatuses = [] } = options;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(`Could not reach the API at ${API_BASE_URL}`);
  }

  if (!response.ok && !acceptStatuses.includes(response.status)) {
    throw new ApiError(`Request to ${path} failed`, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(`Malformed response from ${path}`, response.status);
  }
}

export const getHealth = () => fetchJson<HealthResponse>("/health");

export const getReadiness = () =>
  fetchJson<ReadinessResponse>("/ready", { acceptStatuses: [503] });

export const getSystemInfo = () => fetchJson<SystemInfoResponse>("/api/v1/system/info");

export type ProbeState = "ok" | "error";

export type Probe = {
  state: ProbeState;
  detail: string;
};

export type SystemStatus = {
  api: Probe;
  postgres: Probe;
  info: SystemInfoResponse | null;
  checkedAt: string;
};

/**
 * Query every operational endpoint once. Never throws: an unreachable API is a
 * state the page has to render, not an error page.
 */
export async function loadSystemStatus(): Promise<SystemStatus> {
  const [health, readiness, info] = await Promise.allSettled([
    getHealth(),
    getReadiness(),
    getSystemInfo(),
  ]);

  const postgresStatus =
    readiness.status === "fulfilled"
      ? (readiness.value.dependencies.postgres ?? "unavailable")
      : null;

  return {
    api:
      health.status === "fulfilled"
        ? { state: "ok", detail: health.value.status }
        : { state: "error", detail: "unreachable" },
    postgres:
      postgresStatus === null
        ? { state: "error", detail: "unknown" }
        : { state: postgresStatus === "ok" ? "ok" : "error", detail: postgresStatus },
    info: info.status === "fulfilled" ? info.value : null,
    // Rendered on the server, so a fixed locale and timezone keep it deterministic.
    checkedAt: `${new Date().toLocaleTimeString("en-GB", { timeZone: "UTC" })} UTC`,
  };
}
