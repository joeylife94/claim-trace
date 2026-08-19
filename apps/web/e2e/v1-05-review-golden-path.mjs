import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.V1_05_WEB_URL ?? "http://127.0.0.1:3000";
const targetFilename = "synthetic-sensor-collector.pdf";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

try {
  await page.goto(`${baseUrl}/documents`, { waitUntil: "networkidle" });
  await page.getByRole("link", { name: targetFilename, exact: true }).click();
  await page.waitForLoadState("networkidle");
  await page.getByRole("heading", { name: targetFilename, exact: true }).waitFor();

  await page.getByRole("button", { name: "Decompose & review" }).first().click();
  await page.waitForURL(/\/reviews\/[0-9a-f-]+$/);
  await page.getByRole("heading", { name: "Review claim elements", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Reviewed elements and evidence" }).waitFor();
  await page.getByText("No human review has been recorded for this exact run yet.").waitFor();

  const evidenceLinks = page.getByTitle("Open this exact reviewed span in the original document");
  const evidenceCount = await evidenceLinks.count();
  assert.ok(evidenceCount >= 1, `expected at least one reviewed source link, found ${evidenceCount}`);
  const sourceHref = await evidenceLinks.first().getAttribute("href");
  assert.ok(sourceHref?.startsWith("/documents/"), `invalid reviewed source href: ${sourceHref}`);
  assert.match(sourceHref ?? "", /\?page=\d+&start=\d+&end=\d+$/);

  await page.getByRole("button", { name: "Accept decomposition" }).click();
  await page.waitForURL(/review_saved=accepted/);
  await page.getByText("Review saved: Accepted", { exact: true }).waitFor();
  await page.getByRole("heading", { name: "Review history", exact: true }).waitFor();
  await page.getByText("Accepted", { exact: true }).last().waitFor();

  await page.goto(new URL(sourceHref, baseUrl).toString(), { waitUntil: "networkidle" });
  await page.locator("mark.span-highlight").waitFor();

  console.log("V1-05 human review browser golden path: PASS");
} finally {
  await browser.close();
}
