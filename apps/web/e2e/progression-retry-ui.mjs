import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const webUrl = "http://127.0.0.1:13010";
const apiPort = 18010;
const failedId = "11111111-1111-4111-8111-111111111111";
const completedId = "22222222-2222-4222-8222-222222222222";

const baseDocument = {
  content_type: "application/pdf",
  size_bytes: 1024,
  sha256: "a".repeat(64),
  page_count: null,
  extracted_character_count: null,
  parser_name: null,
  parser_version: null,
  created_at: "2026-09-02T00:00:00Z",
  updated_at: "2026-09-02T00:00:00Z",
};

let retryAttempts = 0;
let failedDocument = {
  ...baseDocument,
  id: failedId,
  original_filename: "recoverable-failure.pdf",
  status: "failed",
  error_code: "storage_failure",
  error_message: "Stored source could not be read. Operator recovery is required.",
};
const completedDocument = {
  ...baseDocument,
  id: completedId,
  original_filename: "already-complete.pdf",
  status: "completed",
  page_count: 2,
  extracted_character_count: 240,
  parser_name: "pymupdf",
  parser_version: "fixture",
  error_code: null,
  error_message: null,
};

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

const apiServer = http.createServer((request, response) => {
  if (request.method === "GET" && request.url?.startsWith("/api/v1/documents?")) {
    return sendJson(response, 200, {
      items: [failedDocument, completedDocument],
      total: 2,
      limit: 20,
      offset: 0,
    });
  }

  if (request.method === "POST" && request.url === `/api/v1/documents/${failedId}/retry`) {
    retryAttempts += 1;
    if (retryAttempts === 1) {
      return sendJson(response, 503, {
        detail: "Persisted source is temporarily unavailable.",
        error_code: "storage_failure",
        document: failedDocument,
      });
    }

    failedDocument = {
      ...failedDocument,
      status: "completed",
      page_count: 3,
      extracted_character_count: 360,
      parser_name: "pymupdf",
      parser_version: "fixture",
      error_code: null,
      error_message: null,
      updated_at: "2026-09-02T00:01:00Z",
    };
    return sendJson(response, 200, failedDocument);
  }

  return sendJson(response, 404, {
    detail: "Not found in deterministic retry UI fixture.",
    error_code: "not_found",
  });
});

await new Promise((resolve, reject) => {
  apiServer.once("error", reject);
  apiServer.listen(apiPort, "127.0.0.1", resolve);
});

const web = spawn("npm", ["run", "dev", "--", "--hostname", "127.0.0.1", "--port", "13010"], {
  cwd: new URL("..", import.meta.url),
  env: {
    ...process.env,
    API_BASE_URL: `http://127.0.0.1:${apiPort}`,
    NEXT_TELEMETRY_DISABLED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
});

let webLogs = "";
web.stdout.on("data", (chunk) => {
  webLogs += chunk.toString();
});
web.stderr.on("data", (chunk) => {
  webLogs += chunk.toString();
});

async function waitForWeb() {
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${webUrl}/documents`);
      if (response.ok) return;
    } catch {
      // Server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Next.js did not become ready.\n${webLogs}`);
}

let browser;
try {
  await waitForWeb();
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(`${webUrl}/documents`, { waitUntil: "networkidle" });

  const failedRow = page.getByRole("row").filter({ hasText: "recoverable-failure.pdf" });
  const completedRow = page.getByRole("row").filter({ hasText: "already-complete.pdf" });

  await failedRow.getByRole("button", { name: "Retry ingestion" }).waitFor();
  assert.equal(await completedRow.getByRole("button", { name: "Retry ingestion" }).count(), 0);
  assert.match(await failedRow.textContent(), /Operator recovery is required/);

  // First execution proves client-safe failure feedback and continued retryability.
  await failedRow.getByRole("button", { name: "Retry ingestion" }).click();
  await failedRow.getByRole("status").waitFor();
  assert.equal(
    (await failedRow.getByRole("status").textContent())?.trim(),
    "Persisted source is temporarily unavailable.",
  );
  await failedRow.getByRole("button", { name: "Retry ingestion" }).waitFor();
  assert.equal(retryAttempts, 1);

  // Second execution proves the same document refreshes to completed and loses failure UI.
  await failedRow.getByRole("button", { name: "Retry ingestion" }).click();
  await page.getByRole("row").filter({ hasText: "recoverable-failure.pdf" }).getByText("completed", { exact: true }).waitFor();
  const refreshedRow = page.getByRole("row").filter({ hasText: "recoverable-failure.pdf" });
  assert.equal(await refreshedRow.getByRole("button", { name: "Retry ingestion" }).count(), 0);
  assert.doesNotMatch(await refreshedRow.textContent(), /Operator recovery is required/);
  assert.equal(retryAttempts, 2);

  console.log("Deterministic failed-ingestion retry UI verification passed.");
} finally {
  if (browser) await browser.close();
  web.kill("SIGTERM");
  await new Promise((resolve) => apiServer.close(resolve));
}
