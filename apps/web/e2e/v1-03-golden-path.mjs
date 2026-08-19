import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.V1_03_WEB_URL ?? "http://127.0.0.1:3000";
const targetFilename = "synthetic-sensor-collector.pdf";
const referenceFilename = "synthetic-battery-thermal.pdf";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

try {
  await page.goto(`${baseUrl}/documents`, { waitUntil: "networkidle" });
  await page.getByRole("link", { name: targetFilename, exact: true }).click();
  await page.waitForLoadState("networkidle");
  await page.getByRole("heading", { name: targetFilename, exact: true }).waitFor();

  await page.getByRole("link", { name: /Compare against another document/ }).click();
  await page.waitForURL(/\/compare\?target=/);
  await page.waitForLoadState("networkidle");

  const targetSelect = page.getByLabel("Target document");
  const referenceSelect = page.getByLabel("Reference document");
  const claimSelect = page.getByLabel("Target claim");

  const selectedTarget = await targetSelect.locator("option:checked").textContent();
  assert.equal(selectedTarget?.trim(), targetFilename, "contextual target was not preselected");

  const selectedReference = await referenceSelect.locator("option:checked").textContent();
  assert.equal(
    selectedReference?.trim(),
    referenceFilename,
    "second indexed document was not selected as reference",
  );

  const selectedClaim = await claimSelect.locator("option:checked").textContent();
  assert.match(selectedClaim ?? "", /^Claim 1\b/, "target claim did not default to Claim 1");

  await page.getByRole("button", { name: "Compare claims" }).click();
  await page.getByRole("heading", { name: "Comparison result" }).waitFor();
  await page.getByRole("heading", { name: /Target claim · Claim 1/ }).waitFor();

  const sourceLinks = page.getByTitle("Open this exact source span in the document");
  const count = await sourceLinks.count();
  assert.ok(count >= 2, `expected target and reference source links, found ${count}`);

  const targetHref = await sourceLinks.nth(0).getAttribute("href");
  const referenceHref = await sourceLinks.nth(1).getAttribute("href");
  assert.ok(targetHref?.startsWith("/documents/"), `invalid target source href: ${targetHref}`);
  assert.ok(
    referenceHref?.startsWith("/documents/"),
    `invalid reference source href: ${referenceHref}`,
  );
  assert.notEqual(
    targetHref?.split("?")[0],
    referenceHref?.split("?")[0],
    "target and reference source links must point to distinct documents",
  );

  for (const href of [targetHref, referenceHref]) {
    await page.goto(new URL(href, baseUrl).toString(), { waitUntil: "networkidle" });
    assert.match(page.url(), /\?page=\d+&start=\d+&end=\d+$/);
    await page.locator("mark.span-highlight").waitFor();
  }

  console.log("V1-03 browser golden path: PASS");
} finally {
  await browser.close();
}
