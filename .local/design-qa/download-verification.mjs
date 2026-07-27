import { readFile } from "node:fs/promises";

import { chromium } from "../../frontend/node_modules/@playwright/test/index.mjs";


const baseUrl = process.env.QI_MVP_BASE_URL ?? "http://127.0.0.1:3002";
const projectId = process.env.QI_REVIEWED_PROJECT_ID;
const operatorId = process.env.QI_REVIEWED_OPERATOR_ID;
const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;


function assert(condition, message) {
  if (!condition) throw new Error(message);
}


assert(typeof projectId === "string" && uuidPattern.test(projectId), "project invalid");
assert(typeof operatorId === "string" && operatorId.trim() !== "", "operator invalid");

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1565, height: 796 },
  deviceScaleFactor: 1,
  locale: "zh-CN",
  timezoneId: "Asia/Hong_Kong",
  acceptDownloads: true,
});

try {
  const page = await context.newPage();
  const failures = [];
  page.on("response", (response) => {
    if (response.status() >= 400) failures.push(response.status());
  });
  const url = new URL(baseUrl);
  url.searchParams.set("project_id", projectId);
  url.searchParams.set("operator_id", operatorId);
  await page.goto(url.toString(), { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "检验项目审核" }).waitFor();
  await page.getByRole("button", { name: "展开 SIP 与导出信息" }).click();
  const projection = await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/projects/${id}/workbench`);
    if (!response.ok) throw new Error("workbench projection failed");
    const payload = await response.json();
    return {
      reviewedResultId: payload.reviewed_result_id,
      artifactReviewedResultIds: (payload.latest_export?.artifacts ?? []).map(
        (artifact) => artifact.reviewed_result_id,
      ),
    };
  }, projectId);
  assert(typeof projection.reviewedResultId === "string", "reviewed result missing");
  assert(
    projection.artifactReviewedResultIds.length === 3
      && projection.artifactReviewedResultIds.every(
        (value) => value === projection.reviewedResultId,
      ),
    "export artifacts do not share one reviewed result",
  );

  const downloads = [];
  for (const [label, signature] of [
    ["下载带气泡 PDF", Buffer.from("%PDF-", "ascii")],
    ["下载 SIP Excel", Buffer.from([0x50, 0x4b, 0x03, 0x04])],
    ["下载校验清单", Buffer.from("{", "ascii")],
  ]) {
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 30_000 }),
      page.getByRole("link", { name: label }).click(),
    ]);
    assert(await download.failure() === null, `${label} failed`);
    const downloadPath = await download.path();
    assert(downloadPath !== null, `${label} path missing`);
    const content = await readFile(downloadPath);
    assert(content.byteLength > signature.byteLength, `${label} is empty`);
    assert(content.subarray(0, signature.byteLength).equals(signature), `${label} signature`);
    downloads.push({ label, sizeBytes: content.byteLength });
    if (label === "下载校验清单") {
      const manifest = JSON.parse(content.toString("utf-8"));
      assert(
        manifest.reviewed_result_id === projection.reviewedResultId
          && Array.isArray(manifest.artifacts)
          && manifest.artifacts.every(
            (artifact) => artifact.reviewed_result_id === projection.reviewedResultId,
          ),
        "manifest reviewed result identity mismatch",
      );
    }
  }
  assert(failures.length === 0, "download QA emitted failed responses");
  console.log(JSON.stringify({
    downloads,
    allNonEmpty: true,
    signaturesValid: true,
    oneReviewedResult: true,
    failedResponses: failures.length,
  }, null, 2));
} finally {
  await context.close();
  await browser.close();
}
