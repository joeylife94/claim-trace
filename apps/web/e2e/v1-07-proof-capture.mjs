import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.V1_07_WEB_URL ?? "http://127.0.0.1:13000";
const outputRoot = process.env.V1_07_PROOF_DIR ?? "docs/proof";
const screenshotsDir = path.join(outputRoot, "screenshots");
const demoDir = path.join(outputRoot, "demo");
const targetFilename = "synthetic-sensor-collector.pdf";
const referenceFilename = "synthetic-battery-thermal.pdf";

await fs.mkdir(screenshotsDir, { recursive: true });
await fs.mkdir(demoDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: demoDir, size: { width: 1280, height: 720 } },
});
const page = await context.newPage();

async function shot(name) {
  await page.screenshot({
    path: path.join(screenshotsDir, name),
    fullPage: true,
  });
}

async function assertExactSource(href, label, expectedDocumentHref = null) {
  assert.ok(href?.startsWith("/documents/"), `${label} source href is invalid: ${href}`);
  assert.match(href ?? "", /\?page=\d+&start=\d+&end=\d+$/);
  if (expectedDocumentHref !== null) {
    assert.equal(href?.split("?")[0], expectedDocumentHref, `${label} escaped document scope`);
  }
  await page.goto(new URL(href, baseUrl).toString(), { waitUntil: "networkidle" });
  await page.locator("mark.span-highlight").waitFor();
}

let video = null;
try {
  await page.goto(`${baseUrl}/documents`, { waitUntil: "networkidle" });
  const targetLink = page.getByRole("link", { name: targetFilename, exact: true });
  const referenceLink = page.getByRole("link", { name: referenceFilename, exact: true });
  await targetLink.waitFor();
  await referenceLink.waitFor();
  await shot("01-documents.png");

  const targetHref = await targetLink.getAttribute("href");
  const referenceHref = await referenceLink.getAttribute("href");
  assert.match(targetHref ?? "", /^\/documents\/[0-9a-f-]+$/);
  assert.match(referenceHref ?? "", /^\/documents\/[0-9a-f-]+$/);
  const targetDocumentId = targetHref.split("/").at(-1);

  await page.goto(`${baseUrl}/search?document=${targetDocumentId}`, { waitUntil: "networkidle" });
  await page.getByLabel("Query").fill("센서 데이터를 수집하는 통신 장치");
  await page.getByLabel("Mode").selectOption("hybrid");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("heading", { name: "Results", exact: true }).waitFor();
  await shot("02-search-results.png");

  await page.goto(`${baseUrl}/grounded?document=${targetDocumentId}`, { waitUntil: "networkidle" });
  await page.getByRole("textbox", { name: "Question" }).fill("통신부는 어떤 모듈을 포함하는가?");
  await page.getByLabel("Mode").selectOption("hybrid");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await page.getByRole("heading", { name: "Answer", exact: true }).waitFor();
  await shot("03-grounded-answer.png");

  await page.goto(`${baseUrl}/compare?target=${targetDocumentId}`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Compare claims" }).click();
  await page.getByRole("heading", { name: "Comparison result" }).waitFor();
  await shot("04-comparison.png");

  const compareSources = page.getByTitle("Open this exact source span in the document");
  assert.ok((await compareSources.count()) >= 2, "comparison proof needs both source links");
  const targetSourceHref = await compareSources.nth(0).getAttribute("href");
  await assertExactSource(targetSourceHref, "comparison target", targetHref);
  await shot("05-source-highlight.png");

  await page.goto(new URL(targetHref, baseUrl).toString(), { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Decompose & review" }).first().click();
  await page.waitForURL(/\/reviews\/[0-9a-f-]+$/);
  await page.getByRole("heading", { name: "Reviewed elements and evidence" }).waitFor();
  await page.getByRole("button", { name: "Accept decomposition" }).click();
  await page.waitForURL(/review_saved=accepted/);
  await page.getByText("Review saved: Accepted", { exact: true }).waitFor();
  await shot("06-human-review.png");

  const reviewedSource = page.getByTitle("Open this exact reviewed span in the original document").first();
  const reviewedHref = await reviewedSource.getAttribute("href");
  await assertExactSource(reviewedHref, "human review", targetHref);

  video = page.video();
  console.log("V1-07 proof capture: PASS");
} finally {
  await context.close();
  if (video !== null) {
    await video.saveAs(path.join(demoDir, "claimtrace-golden-path.webm"));
  }
  await browser.close();
}
