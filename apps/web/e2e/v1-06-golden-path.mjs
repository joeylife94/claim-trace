import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.V1_06_WEB_URL ?? "http://127.0.0.1:13000";
const targetFilename = "synthetic-sensor-collector.pdf";
const referenceFilename = "synthetic-battery-thermal.pdf";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

async function assertExactSource(href, label) {
  assert.ok(href?.startsWith("/documents/"), `${label} source href is invalid: ${href}`);
  assert.match(href ?? "", /\?page=\d+&start=\d+&end=\d+$/);
  await page.goto(new URL(href, baseUrl).toString(), { waitUntil: "networkidle" });
  await page.locator("mark.span-highlight").waitFor();
}

try {
  // Ingest/parse/index are executed by the committed deterministic seed before
  // this browser procedure starts. Confirm both indexed demo documents exist.
  await page.goto(`${baseUrl}/documents`, { waitUntil: "networkidle" });
  const targetLink = page.getByRole("link", { name: targetFilename, exact: true });
  const referenceLink = page.getByRole("link", { name: referenceFilename, exact: true });
  await targetLink.waitFor();
  await referenceLink.waitFor();

  const targetHref = await targetLink.getAttribute("href");
  const referenceHref = await referenceLink.getAttribute("href");
  assert.match(targetHref ?? "", /^\/documents\/[0-9a-f-]+$/);
  assert.match(referenceHref ?? "", /^\/documents\/[0-9a-f-]+$/);
  const targetDocumentId = targetHref.split("/").at(-1);

  // Retrieve: document-scoped hybrid claim search with exact source navigation.
  await page.goto(`${baseUrl}/search?document=${targetDocumentId}`, { waitUntil: "networkidle" });
  await page.getByLabel("Query").fill("센서 데이터를 수집하는 통신 장치");
  await page.getByLabel("Mode").selectOption("hybrid");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("heading", { name: "Results", exact: true }).waitFor();
  const searchSource = page.getByTitle("Open this span in the document's page text").first();
  await searchSource.waitFor();
  const searchSourceHref = await searchSource.getAttribute("href");
  await assertExactSource(searchSourceHref, "search");

  // Ask: grounded answer must expose persisted evidence, or an explicit
  // insufficient-evidence limitation if the deterministic provider refuses.
  await page.goto(`${baseUrl}/grounded?document=${targetDocumentId}`, { waitUntil: "networkidle" });
  await page.getByRole("textbox", { name: "Question" }).fill("통신부는 어떤 모듈을 포함하는가?");
  await page.getByLabel("Mode").selectOption("hybrid");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await page.getByRole("heading", { name: "Answer", exact: true }).waitFor();

  const groundedSources = page.getByTitle("Open this span in the document's page text");
  if ((await groundedSources.count()) > 0) {
    const groundedHref = await groundedSources.first().getAttribute("href");
    await assertExactSource(groundedHref, "grounded answer");
  } else {
    await page.locator(".grounded-limitation").waitFor();
  }

  // Compare: target/reference scope and both exact source links.
  await page.goto(`${baseUrl}/compare?target=${targetDocumentId}`, { waitUntil: "networkidle" });
  const targetSelect = page.getByLabel("Target document");
  const referenceSelect = page.getByLabel("Reference document");
  const claimSelect = page.getByLabel("Target claim");

  assert.equal((await targetSelect.locator("option:checked").textContent())?.trim(), targetFilename);
  assert.equal(
    (await referenceSelect.locator("option:checked").textContent())?.trim(),
    referenceFilename,
  );
  assert.match((await claimSelect.locator("option:checked").textContent()) ?? "", /^Claim 1\b/);

  await page.getByRole("button", { name: "Compare claims" }).click();
  await page.getByRole("heading", { name: "Comparison result" }).waitFor();
  const compareSources = page.getByTitle("Open this exact source span in the document");
  const compareCount = await compareSources.count();
  assert.ok(compareCount >= 2, `expected target/reference comparison sources, found ${compareCount}`);
  const compareTargetHref = await compareSources.nth(0).getAttribute("href");
  const compareReferenceHref = await compareSources.nth(1).getAttribute("href");
  assert.notEqual(compareTargetHref?.split("?")[0], compareReferenceHref?.split("?")[0]);
  await assertExactSource(compareTargetHref, "comparison target");
  await assertExactSource(compareReferenceHref, "comparison reference");

  // Decompose/review: machine output stays separate from append-only human review.
  await page.goto(new URL(targetHref, baseUrl).toString(), { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Decompose & review" }).first().click();
  await page.waitForURL(/\/reviews\/[0-9a-f-]+$/);
  await page.getByRole("heading", { name: "Reviewed elements and evidence" }).waitFor();
  await page.getByText("No human review has been recorded for this exact run yet.").waitFor();

  const reviewedSources = page.getByTitle("Open this exact reviewed span in the original document");
  assert.ok((await reviewedSources.count()) >= 1, "expected at least one reviewed source link");
  const reviewedSourceHref = await reviewedSources.first().getAttribute("href");

  await page.getByRole("button", { name: "Accept decomposition" }).click();
  await page.waitForURL(/review_saved=accepted/);
  await page.getByText("Review saved: Accepted", { exact: true }).waitFor();
  await page.getByRole("heading", { name: "Review history", exact: true }).waitFor();
  await page.getByText("Accepted", { exact: true }).last().waitFor();

  // Final source verification closes the frozen workflow.
  await assertExactSource(reviewedSourceHref, "human review");

  console.log("V1-06 whole-product golden path: PASS");
} finally {
  await browser.close();
}
