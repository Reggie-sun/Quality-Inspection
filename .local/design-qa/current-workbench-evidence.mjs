import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { chromium } from "../../frontend/node_modules/@playwright/test/index.mjs";


const root = process.cwd();
const outputDirectory = path.join(root, ".local", "design-qa");
const baseUrl = process.env.QI_MVP_BASE_URL ?? "http://127.0.0.1:3002";
const referencePath = process.env.QI_REFERENCE_IMAGE ?? "/tmp/qi-task5-reference.png";
const reviewedProjectId = process.env.QI_REVIEWED_PROJECT_ID;
const reviewedOperatorId = process.env.QI_REVIEWED_OPERATOR_ID;
const frozenProjectId = process.env.QI_FROZEN_PROJECT_ID;
const frozenOperatorId = process.env.QI_FROZEN_OPERATOR_ID;
const uuidPattern =
  /[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/i;


function assert(condition, message) {
  if (!condition) throw new Error(message);
}


function validateProjectId(value, label) {
  assert(typeof value === "string" && uuidPattern.test(value), `${label} is invalid`);
  return value;
}


function validateOperatorId(value, label) {
  assert(
    typeof value === "string" && value.trim().length > 0 && value.length <= 128,
    `${label} is invalid`,
  );
  return value;
}


function workbenchUrl(projectId, operatorId) {
  const url = new URL(baseUrl);
  url.searchParams.set("project_id", projectId);
  url.searchParams.set("operator_id", operatorId);
  return url.toString();
}


function diagnostics(page) {
  const state = {
    consoleErrors: [],
    failedResponses: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error") state.consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) state.failedResponses.push(response.status());
  });
  return state;
}


async function screenshot(page, filename) {
  await page.screenshot({
    path: path.join(outputDirectory, filename),
  });
}


async function sha256(filename) {
  return createHash("sha256")
    .update(await readFile(path.join(outputDirectory, filename)))
    .digest("hex");
}


async function openWorkbench(context, projectId, operatorId) {
  const page = await context.newPage();
  const diag = diagnostics(page);
  await page.goto(workbenchUrl(projectId, operatorId), { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "检验项目审核" }).waitFor({
    state: "visible",
    timeout: 30_000,
  });
  await page.locator("[data-testid=pdf-canvas]").waitFor({
    state: "visible",
    timeout: 30_000,
  });
  assert(!uuidPattern.test(await page.locator("body").innerText()), "workbench exposes UUID");
  return { page, diag };
}


const reviewedId = validateProjectId(reviewedProjectId, "reviewed project_id");
const reviewedOperator = validateOperatorId(
  reviewedOperatorId,
  "reviewed operator_id",
);
const frozenId = validateProjectId(frozenProjectId, "frozen project_id");
const frozenOperator = validateOperatorId(frozenOperatorId, "frozen operator_id");

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 1565, height: 796 },
  deviceScaleFactor: 1,
  locale: "zh-CN",
  timezoneId: "Asia/Hong_Kong",
  colorScheme: "light",
});

try {
  const reviewed = await openWorkbench(context, reviewedId, reviewedOperator);
  const expandAuxiliary = reviewed.page.getByRole("button", {
    name: "展开 SIP 与导出信息",
  });
  await expandAuxiliary.waitFor({ state: "visible" });
  const layout = await reviewed.page.evaluate(() => {
    const drawing = document.querySelector(".drawing-pane");
    const inspection = document.querySelector(".inspection-pane");
    const auxiliary = document.querySelector("#pdf-auxiliary-panel");
    if (
      !(drawing instanceof HTMLElement)
      || !(inspection instanceof HTMLElement)
      || !(auxiliary instanceof HTMLElement)
    ) return null;
    return {
      drawingWidth: drawing.getBoundingClientRect().width,
      inspectionWidth: inspection.getBoundingClientRect().width,
      auxiliaryHidden: auxiliary.hidden,
      pageScrollWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
    };
  });
  assert(layout !== null, "current workbench layout is missing");
  assert(layout.drawingWidth > layout.inspectionWidth, "PDF is not the largest pane");
  assert(layout.auxiliaryHidden, "auxiliary panel must be collapsed by default");
  assert(layout.pageScrollWidth === layout.viewportWidth, "workbench overflows horizontally");
  await screenshot(reviewed.page, "05-workbench-overview.png");

  const firstRow = reviewed.page.locator("[role=row][data-item-id]").first();
  await firstRow.click();
  await reviewed.page.locator("[role=row][data-selected=true]").waitFor({
    state: "visible",
  });
  await screenshot(reviewed.page, "06-item-selected.png");

  const firstBalloon = reviewed.page.getByRole("button", { name: /^气泡 \d+/ }).first();
  await firstBalloon.waitFor({ state: "visible" });
  await firstBalloon.click();
  await reviewed.page.locator("[data-testid^=balloon-][data-selected=true]").waitFor({
    state: "visible",
  });
  await screenshot(reviewed.page, "08-balloons-adjusted.png");

  await expandAuxiliary.click();
  await reviewed.page.getByRole("region", { name: "SIP基本信息" }).waitFor({
    state: "visible",
  });
  await reviewed.page.getByRole("navigation", { name: "正式文件下载" }).waitFor({
    state: "visible",
  });
  assert(
    await reviewed.page.getByRole("link", { name: "下载带气泡 PDF" }).isVisible()
      && await reviewed.page.getByRole("link", { name: "下载 SIP Excel" }).isVisible()
      && await reviewed.page.getByRole("link", { name: "下载校验清单" }).isVisible(),
    "formal download set is incomplete",
  );
  await screenshot(reviewed.page, "09-export-success.png");
  assert(reviewed.diag.consoleErrors.length === 0, "reviewed workbench has console errors");
  assert(reviewed.diag.failedResponses.length === 0, "reviewed workbench has failed requests");
  await reviewed.page.close();

  const frozen = await openWorkbench(context, frozenId, frozenOperator);
  assert(
    await frozen.page.getByRole("button", { name: "冻结检验项" }).isDisabled(),
    "frozen workbench still allows freezing",
  );
  assert(
    await frozen.page.getByRole("navigation", { name: "正式文件下载" }).count() === 0,
    "frozen workbench exposes formal downloads",
  );
  await screenshot(frozen.page, "07-items-frozen.png");
  assert(frozen.diag.consoleErrors.length === 0, "frozen workbench has console errors");
  assert(frozen.diag.failedResponses.length === 0, "frozen workbench has failed requests");
  await frozen.page.close();

  const comparison = await context.newPage();
  const referenceData = (await readFile(referencePath)).toString("base64");
  const currentData = (
    await readFile(path.join(outputDirectory, "05-workbench-overview.png"))
  ).toString("base64");
  await comparison.setContent(`
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8">
        <style>
          * { box-sizing: border-box; }
          html, body { width: 100%; height: 100%; margin: 0; }
          body {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            padding: 12px;
            background: #eef2f6;
            color: #172033;
            font: 600 14px/1.4 "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
          }
          figure {
            min-width: 0;
            margin: 0;
            display: grid;
            grid-template-rows: auto minmax(0, 1fr);
            gap: 8px;
            padding: 10px;
            border: 1px solid #c9d3df;
            background: #fff;
          }
          figcaption { color: #315f94; }
          img {
            width: 100%;
            height: 100%;
            min-height: 0;
            object-fit: contain;
            object-position: center top;
            border: 1px solid #dce3eb;
            background: #f8fafc;
          }
        </style>
      </head>
      <body>
        <figure>
          <figcaption>已确认参考图（仅视觉方向）</figcaption>
          <img src="data:image/png;base64,${referenceData}" alt="">
        </figure>
        <figure>
          <figcaption>当前实现（当前 worktree）</figcaption>
          <img src="data:image/png;base64,${currentData}" alt="">
        </figure>
      </body>
    </html>
  `);
  await screenshot(comparison, "10-reference-comparison.png");
  await comparison.close();

  const files = [
    "05-workbench-overview.png",
    "06-item-selected.png",
    "07-items-frozen.png",
    "08-balloons-adjusted.png",
    "09-export-success.png",
    "10-reference-comparison.png",
  ];
  const hashes = Object.fromEntries(
    await Promise.all(files.map(async (filename) => [filename, await sha256(filename)])),
  );
  const evidence = {
    browser: "Google Chrome",
    viewport: { width: 1565, height: 796, deviceScaleFactor: 1 },
    locale: "zh-CN",
    timezone: "Asia/Hong_Kong",
    currentTwoPaneLayout: layout,
    auxiliaryCollapsedByDefault: true,
    reviewedWorkbench: {
      selectedItem: true,
      selectedBalloon: true,
      formalDownloads: ["ballooned_pdf", "sip_excel", "manifest"],
      consoleErrors: reviewed.diag.consoleErrors.length,
      failedResponses: reviewed.diag.failedResponses.length,
    },
    frozenWorkbench: {
      freezeDisabled: true,
      formalDownloadsHidden: true,
      consoleErrors: frozen.diag.consoleErrors.length,
      failedResponses: frozen.diag.failedResponses.length,
    },
    hashes,
  };
  await writeFile(
    path.join(outputDirectory, "current-workbench-evidence.json"),
    `${JSON.stringify(evidence, null, 2)}\n`,
  );
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  await context.close();
  await browser.close();
}
