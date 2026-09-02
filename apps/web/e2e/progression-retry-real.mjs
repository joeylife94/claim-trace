import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const webUrl = "http://127.0.0.1:13011";
const apiUrl = process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8000";
const filename = "progression-real-retry.pdf";

const web = spawn(
  process.execPath,
  ["node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1", "--port", "13011"],
  {
    cwd: new URL("..", import.meta.url),
    env: {
      ...process.env,
      API_INTERNAL_BASE_URL: apiUrl,
      NEXT_TELEMETRY_DISABLED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);

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
      // Next.js is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Next.js did not become ready.\n${webLogs}`);
}

let browser;
try {
  const before = await fetch(`${apiUrl}/api/v1/documents?limit=20&offset=0`);
  assert.equal(before.status, 200);
  const beforeBody = await before.json();
  const seeded = beforeBody.items.find((item) => item.original_filename === filename);
  assert.ok(seeded, "real API did not expose the seeded failed document");
  assert.equal(seeded.status, "failed");
  assert.equal(beforeBody.total, 1);

  await waitForWeb();
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(`${webUrl}/documents`, { waitUntil: "networkidle" });

  const failedRow = page.getByRole("row").filter({ hasText: filename });
  await failedRow.getByText("failed", { exact: true }).waitFor();
  await failedRow.getByRole("button", { name: "Retry ingestion" }).waitFor();
  assert.match(await failedRow.textContent(), /deterministic operator recovery/i);

  await failedRow.getByRole("button", { name: "Retry ingestion" }).click();
  await page
    .getByRole("row")
    .filter({ hasText: filename })
    .getByText("completed", { exact: true })
    .waitFor();

  const refreshedRow = page.getByRole("row").filter({ hasText: filename });
  assert.equal(await refreshedRow.getByRole("button", { name: "Retry ingestion" }).count(), 0);
  assert.doesNotMatch(await refreshedRow.textContent(), /deterministic operator recovery/i);

  const after = await fetch(`${apiUrl}/api/v1/documents?limit=20&offset=0`);
  assert.equal(after.status, 200);
  const afterBody = await after.json();
  const recovered = afterBody.items.find((item) => item.original_filename === filename);
  assert.ok(recovered, "recovered document disappeared from real API listing");
  assert.equal(recovered.id, seeded.id);
  assert.equal(recovered.sha256, seeded.sha256);
  assert.equal(recovered.status, "completed");
  assert.equal(recovered.error_code, null);
  assert.equal(recovered.error_message, null);
  assert.equal(afterBody.total, 1);

  console.log("Real web/API/PostgreSQL failed-ingestion retry integration verification passed.");
} finally {
  if (browser) await browser.close();
  web.kill("SIGTERM");
}
