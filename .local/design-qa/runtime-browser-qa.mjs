import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { chromium } from "../../frontend/node_modules/@playwright/test/index.mjs";


const root = process.cwd();
const outputDirectory = path.join(root, ".local", "design-qa");
const baseUrl = process.env.QI_MVP_BASE_URL ?? "http://127.0.0.1:3002";
const denseProjectId = process.env.QI_QA_DENSE_PROJECT_ID;
const denseOperatorId = process.env.QI_QA_DENSE_OPERATOR_ID;
const nativePdf = path.join(outputDirectory, "native-linear-smoke.pdf");
const invalidPdf = path.join(outputDirectory, "invalid.pdf");
const uuidPattern =
  /[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/i;


function assert(condition, message) {
  if (!condition) throw new Error(message);
}


function runDocker(args) {
  execFileSync("docker", args, {
    cwd: root,
    stdio: "ignore",
  });
}


function runSql(sql) {
  runDocker([
    "compose",
    "exec",
    "-T",
    "postgres",
    "sh",
    "-lc",
    `psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "${sql}" >/dev/null`,
  ]);
}


function validateRuntimeId(value, label) {
  assert(typeof value === "string" && uuidPattern.test(value), `${label} is invalid`);
  return value;
}


function validateOperatorId(value) {
  assert(
    typeof value === "string" && value.trim().length > 0 && value.length <= 128,
    "operator_id is invalid",
  );
  return value;
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


async function bodyHasUuid(page) {
  return uuidPattern.test(await page.locator("body").innerText());
}


async function screenshot(page, filename) {
  await page.screenshot({
    path: path.join(outputDirectory, filename),
  });
}


async function waitForStatus(page, text) {
  await page.getByRole("status").filter({ hasText: text }).waitFor({
    state: "visible",
    timeout: 30_000,
  });
}


async function setProcessingStage(projectId, stage, { create = false } = {}) {
  validateRuntimeId(projectId, "project_id");
  assert(
    ["queued", "parsing", "recognizing", "preparing_review"].includes(stage),
    "processing stage is invalid",
  );
  if (create) {
    const jobId = randomUUID();
    runSql(
      "INSERT INTO logical_jobs "
      + "(id,project_id,logical_task_key,status,result_ref,processing_stage) "
      + `VALUES ('${jobId}','${projectId}','product-process:${projectId}',`
      + `'processing',NULL,'${stage}') `
      + "ON CONFLICT (project_id,logical_task_key) DO UPDATE SET "
      + `status='processing',result_ref=NULL,processing_stage='${stage}';`,
    );
    return;
  }
  const status = stage === "queued" ? "pending" : "processing";
  runSql(
    "UPDATE logical_jobs SET "
    + `status='${status}',result_ref=NULL,processing_stage='${stage}' `
    + `WHERE project_id='${projectId}' `
    + `AND logical_task_key='product-process:${projectId}';`,
  );
}


async function exactEnvironment(page) {
  return await page.evaluate(() => ({
    width: innerWidth,
    height: innerHeight,
    deviceScaleFactor: devicePixelRatio,
    locale: Intl.DateTimeFormat().resolvedOptions().locale,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }));
}


async function clearProjectContext(page) {
  await page.evaluate(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await page.reload({ waitUntil: "networkidle" });
}


async function rootAndProcessingQa(context) {
  const page = await context.newPage();
  const diag = diagnostics(page);
  let workerStopped = false;
  let workerRestarted = false;

  try {
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    await clearProjectContext(page);

    const environment = await exactEnvironment(page);
    assert(environment.width === 1565 && environment.height === 796, "viewport drift");
    assert(environment.deviceScaleFactor === 1, "device scale factor drift");
    assert(environment.locale === "zh-CN", "locale drift");
    assert(environment.timezone === "Asia/Hong_Kong", "timezone drift");
    assert(
      await page.getByText("智检通", { exact: true }).isVisible(),
      "text brand is missing",
    );
    assert(
      await page.getByRole("heading", { name: "工程图纸智能检验" }).isVisible(),
      "upload heading is missing",
    );
    assert(
      await page.getByRole("button", { name: "上传并开始识别" }).isDisabled(),
      "empty upload action must be disabled",
    );
    assert(!(await bodyHasUuid(page)), "idle page exposes an internal UUID");
    assert(
      await page.evaluate(() => document.documentElement.scrollWidth === innerWidth),
      "idle page has horizontal overflow",
    );
    assert(
      await page.locator("header img, header svg").count() === 0,
      "header contains a logo graphic",
    );
    await screenshot(page, "01-upload-idle.png");

    let focusEvidence = null;
    for (let index = 0; index < 8; index += 1) {
      await page.keyboard.press("Tab");
      focusEvidence = await page.evaluate(() => {
        const active = document.activeElement;
        if (!(active instanceof HTMLElement)) return null;
        const focusTarget = active.closest(".pdf-dropzone") ?? active;
        const style = getComputedStyle(focusTarget);
        return {
          tag: active.tagName,
          type: active.getAttribute("type"),
          name: active.getAttribute("aria-label") ?? active.innerText.trim(),
          outlineWidth: style.outlineWidth,
          outlineStyle: style.outlineStyle,
        };
      });
      if (
        focusEvidence?.tag === "BUTTON"
        || (focusEvidence?.tag === "INPUT" && focusEvidence?.type === "file")
      ) break;
    }
    assert(
      focusEvidence?.tag === "BUTTON"
      || (focusEvidence?.tag === "INPUT" && focusEvidence?.type === "file"),
      "keyboard did not reach the upload action",
    );
    assert(
      focusEvidence.outlineStyle !== "none" && focusEvidence.outlineWidth !== "0px",
      "focus-visible indicator is missing",
    );

    const fileInput = page.locator("input[type=file]");
    await fileInput.setInputFiles(nativePdf);
    const nativeSize = (await readFile(nativePdf)).byteLength;
    assert(
      await page.getByText("native-linear-smoke.pdf", { exact: true }).isVisible(),
      "selected filename is missing",
    );
    assert(
      (await page.locator("[aria-label='已选择文件']").innerText()).includes(
        nativeSize < 1024 ? `${nativeSize} B` : "KB",
      ),
      "selected file size is missing",
    );
    assert(
      await page.getByRole("button", { name: "上传并开始识别" }).isEnabled(),
      "selected upload action must be enabled",
    );
    await screenshot(page, "02-file-selected.png");

    runDocker(["compose", "stop", "worker"]);
    workerStopped = true;
    await page.getByRole("button", { name: "上传并开始识别" }).click();
    await waitForStatus(page, "项目已创建，等待处理");
    const projectId = validateRuntimeId(
      await page.evaluate(() => sessionStorage.getItem("qi.current-project-id")),
      "uploaded project_id",
    );
    assert(
      await page.locator("main[aria-busy=true]").count() === 1,
      "queued processing is not marked busy",
    );
    assert(!(await bodyHasUuid(page)), "queued page exposes an internal UUID");
    await screenshot(page, "03-processing.png");

    await setProcessingStage(projectId, "parsing", { create: true });
    await page.reload({ waitUntil: "networkidle" });
    await waitForStatus(page, "正在解析工程图纸");
    assert(
      !/\b\d{1,3}%\b/.test(await page.locator("body").innerText()),
      "parsing screen exposes a synthetic percentage",
    );
    await screenshot(page, "13-processing-parsing.png");

    await setProcessingStage(projectId, "recognizing");
    await page.reload({ waitUntil: "networkidle" });
    await waitForStatus(page, "正在识别检验项");
    assert(
      !/\b\d{1,3}%\b/.test(await page.locator("body").innerText()),
      "recognizing screen exposes a synthetic percentage",
    );
    await screenshot(page, "14-processing-recognizing.png");

    await setProcessingStage(projectId, "preparing_review");
    await page.reload({ waitUntil: "networkidle" });
    await waitForStatus(page, "正在准备审核");
    assert(
      !/\b\d{1,3}%\b/.test(await page.locator("body").innerText()),
      "preparing-review screen exposes a synthetic percentage",
    );
    await screenshot(page, "19-processing-preparing-review.png");

    await setProcessingStage(projectId, "queued");
    runDocker(["compose", "start", "worker"]);
    workerRestarted = true;
    await page.getByRole("heading", { name: "检验项目审核" }).waitFor({
      state: "visible",
      timeout: 120_000,
    });
    await page.locator("[data-testid=pdf-canvas]").waitFor({
      state: "visible",
      timeout: 30_000,
    });
    await page.locator("[data-testid^=pdf-thumbnail]:not([hidden])").waitFor({
      state: "visible",
      timeout: 30_000,
    });
    const firstInspectionRow = page.locator("[role=row][data-item-id]").first();
    await firstInspectionRow.waitFor({ state: "visible", timeout: 30_000 });
    await firstInspectionRow.click();
    const thumbnailEvidence = await page
      .locator("[data-testid^=pdf-thumbnail]:not([hidden])")
      .first()
      .evaluate((canvas) => {
        const context2d = canvas.getContext("2d");
        const pixels = context2d?.getImageData(0, 0, canvas.width, canvas.height).data;
        let nonwhite = 0;
        if (pixels !== undefined) {
          for (let index = 0; index < pixels.length; index += 4) {
            if (
              pixels[index + 3] > 0
              && (pixels[index] < 245
              || pixels[index + 1] < 245
              || pixels[index + 2] < 245)
            ) {
              nonwhite += 1;
            }
          }
        }
        return { width: canvas.width, height: canvas.height, nonwhite };
      });
    assert(thumbnailEvidence.nonwhite > 0, "thumbnail is not a rendered PDF preview");

    await page.getByRole("button", { name: "适合页面" }).click();
    await page.waitForTimeout(100);
    const fitEvidence = await page.evaluate(() => {
      const frame = document.querySelector("[data-testid=pdf-scroll-frame]");
      const layer = document.querySelector("[data-testid=pdf-page-layer]");
      if (!(frame instanceof HTMLElement) || !(layer instanceof HTMLElement)) {
        return null;
      }
      const frameBox = frame.getBoundingClientRect();
      const layerBox = layer.getBoundingClientRect();
      return {
        frameWidth: frameBox.width,
        frameHeight: frameBox.height,
        layerWidth: layerBox.width,
        layerHeight: layerBox.height,
        fitsWidth: layerBox.width <= frameBox.width + 1,
        fitsHeight: layerBox.height <= frameBox.height + 1,
      };
    });
    assert(fitEvidence?.fitsWidth && fitEvidence?.fitsHeight, "fit-to-container failed");
    assert(!(await bodyHasUuid(page)), "workbench exposes an internal UUID");
    await page.getByLabel("工程图纸", { exact: true }).scrollIntoViewIfNeeded();
    await screenshot(page, "15-real-thumbnails-fit.png");

    const remarks = page.getByLabel(/备注（可选）：/).first();
    await remarks.waitFor({ state: "visible", timeout: 30_000 });
    await remarks.fill("QA 浏览器验证备注");
    assert(await remarks.inputValue() === "QA 浏览器验证备注", "remarks edit failed");
    await remarks.scrollIntoViewIfNeeded();
    await screenshot(page, "16-item-remarks.png");
    await page.getByRole("button", { name: "取消 SIP 字段修改" }).click();
    assert(await remarks.inputValue() === "", "remarks cancel did not restore the value");

    const tableEvidence = await page.evaluate(() => {
      const head = document.querySelector(".inspection-table__head");
      return {
        rowCount: document.querySelectorAll("[role=row][data-item-id]").length,
        sticky: head === null ? null : getComputedStyle(head).position,
      };
    });
    assert(tableEvidence.rowCount > 0, "inspection list is empty");
    assert(tableEvidence.sticky === "sticky", "inspection table header is not sticky");
    assert(diag.consoleErrors.length === 0, "successful flow emitted console errors");
    assert(diag.failedResponses.length === 0, "successful flow emitted failed requests");

    return {
      environment,
      focusVisible: true,
      idleNoHorizontalOverflow: true,
      idleNoLogoGraphic: true,
      idleNoInternalId: true,
      selectedFileTruthful: true,
      busyAria: true,
      indeterminateStages: ["queued", "parsing", "recognizing", "preparing_review"],
      thumbnail: thumbnailEvidence,
      fit: fitEvidence,
      remarksEditCancel: true,
      table: tableEvidence,
      consoleErrors: diag.consoleErrors.length,
      failedResponses: diag.failedResponses.length,
    };
  } finally {
    if (workerStopped && !workerRestarted) {
      runDocker(["compose", "start", "worker"]);
    }
    await page.close();
  }
}


async function fatalQa(context) {
  const page = await context.newPage();
  const diag = diagnostics(page);
  try {
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    await clearProjectContext(page);
    await page.locator("input[type=file]").setInputFiles(invalidPdf);
    await page.getByRole("button", { name: "上传并开始识别" }).click();
    const alert = page.getByRole("alert");
    await alert.waitFor({ state: "visible", timeout: 30_000 });
    const text = await alert.innerText();
    assert(/PDF/.test(text), "fatal guidance does not identify the PDF action");
    assert(!/[A-Za-z]{5,}/.test(text.replaceAll("PDF", "")), "fatal guidance exposes English");
    assert(
      await page.getByRole("button", { name: "重新选择文件" }).isVisible(),
      "fatal next step is missing",
    );
    assert(!(await bodyHasUuid(page)), "fatal page exposes an internal UUID");
    assert(
      await page.locator("main[aria-busy=false]").count() === 1,
      "fatal page remains marked busy",
    );
    await screenshot(page, "04-fatal-retry.png");
    assert(diag.failedResponses.length === 1, "invalid PDF did not produce one expected failure");
    return {
      roleAlert: true,
      chineseGuidance: true,
      noInternalId: true,
      expectedHttpFailure: diag.failedResponses[0],
      consoleErrors: diag.consoleErrors.length,
    };
  } finally {
    await page.close();
  }
}


async function denseWorkbenchQa(context) {
  validateRuntimeId(denseProjectId, "dense project_id");
  validateOperatorId(denseOperatorId);
  const page = await context.newPage();
  const diag = diagnostics(page);
  try {
    const workbenchUrl = new URL(baseUrl);
    workbenchUrl.searchParams.set("project_id", denseProjectId);
    workbenchUrl.searchParams.set("operator_id", denseOperatorId);
    await page.goto(workbenchUrl.toString(), { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "检验项目审核" }).waitFor({
      state: "visible",
      timeout: 30_000,
    });
    await page.locator("[data-testid=pdf-canvas]").waitFor({
      state: "visible",
      timeout: 30_000,
    });

    const density = await page.evaluate(() => ({
      candidateMarkers: document.querySelectorAll("[data-testid^=candidate-]").length,
      sourceMarkers: document.querySelectorAll("[data-testid^=source-]").length,
      tableRows: document.querySelectorAll("[role=row][data-item-id]").length,
      candidateOpacity: getComputedStyle(
        document.querySelector(".pdf-overlay-candidate-marker") ?? document.body,
      ).opacity,
    }));
    assert(density.candidateMarkers >= 50, "dense candidate scene was not loaded");
    assert(density.sourceMarkers >= 50, "dense source scene was not loaded");
    const candidateButton = page.getByRole("button", { name: /^候选气泡/ }).first();
    await candidateButton.click();
    assert(
      await page.locator("[role=row][data-selected=true]").count() === 1,
      "candidate selection did not locate the inspection row",
    );
    await page.getByLabel("工程图纸", { exact: true }).scrollIntoViewIfNeeded();
    await screenshot(page, "17-dense-overlay-focus.png");

    const responsive = [];
    for (const [width, height, filename] of [
      [1366, 768, "11-workbench-1366.png"],
      [1180, 800, "18-workbench-1180.png"],
    ]) {
      await page.setViewportSize({ width, height });
      await page.getByLabel("工程图纸", { exact: true }).scrollIntoViewIfNeeded();
      const evidence = await page.evaluate(() => ({
        width: innerWidth,
        height: innerHeight,
        scrollWidth: document.documentElement.scrollWidth,
        pdfVisible: document.querySelector("[data-testid=pdf-workspace]") !== null,
        tableVisible: document.querySelector("[role=table]") !== null,
      }));
      assert(evidence.scrollWidth === width, `${width}px workbench has horizontal overflow`);
      assert(evidence.pdfVisible && evidence.tableVisible, `${width}px workbench is incomplete`);
      responsive.push(evidence);
      await screenshot(page, filename);
      if (width === 1180) {
        await screenshot(page, "12-workbench-1180.png");
      }
    }

    const ariaSnapshot = typeof page.locator("body").ariaSnapshot === "function"
      ? await page.locator("body").ariaSnapshot()
      : "";
    assert(
      ariaSnapshot.includes("检验项目审核") && ariaSnapshot.includes("工程图纸"),
      "accessibility snapshot misses workbench landmarks",
    );
    assert(!(await bodyHasUuid(page)), "dense workbench exposes an internal UUID");
    assert(diag.consoleErrors.length === 0, "dense workbench emitted console errors");
    assert(diag.failedResponses.length === 0, "dense workbench emitted failed requests");
    return {
      density,
      selectedCrossLink: true,
      responsive,
      accessibilitySnapshot: true,
      noInternalId: true,
      consoleErrors: diag.consoleErrors.length,
      failedResponses: diag.failedResponses.length,
    };
  } finally {
    await page.close();
  }
}


async function reducedMotionQa(browser) {
  const context = await browser.newContext({
    viewport: { width: 1565, height: 796 },
    deviceScaleFactor: 1,
    locale: "zh-CN",
    timezoneId: "Asia/Hong_Kong",
    colorScheme: "light",
    reducedMotion: "reduce",
  });
  try {
    const page = await context.newPage();
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    const evidence = await page.evaluate(() => {
      const button = document.querySelector("button");
      return {
        mediaMatches: matchMedia("(prefers-reduced-motion: reduce)").matches,
        transitionDuration: button === null
          ? ""
          : getComputedStyle(button).transitionDuration,
        animationDuration: button === null
          ? ""
          : getComputedStyle(button).animationDuration,
      };
    });
    assert(evidence.mediaMatches, "reduced-motion media query is inactive");
    assert(
      ["0s", "0.00001s"].includes(evidence.transitionDuration),
      "reduced-motion transition override is inactive",
    );
    return evidence;
  } finally {
    await context.close();
  }
}


const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
});
const contextOptions = {
  viewport: { width: 1565, height: 796 },
  deviceScaleFactor: 1,
  locale: "zh-CN",
  timezoneId: "Asia/Hong_Kong",
  colorScheme: "light",
};
const context = await browser.newContext(contextOptions);

try {
  const rootAndProcessing = await rootAndProcessingQa(context);
  const fatal = await fatalQa(context);
  const denseContext = await browser.newContext(contextOptions);
  const denseWorkbench = await denseWorkbenchQa(denseContext).finally(
    () => denseContext.close(),
  );
  const reducedMotion = await reducedMotionQa(browser);
  const result = {
    browser: "Google Chrome",
    rootAndProcessing,
    fatal,
    denseWorkbench,
    reducedMotion,
  };
  await writeFile(
    path.join(outputDirectory, "runtime-browser-evidence.json"),
    `${JSON.stringify(result, null, 2)}\n`,
  );
  console.log(JSON.stringify(result, null, 2));
} finally {
  await context.close();
  await browser.close();
}
