import { readFile } from "node:fs/promises";

import { expect, test, type Locator, type Page } from "@playwright/test";

import type { ProjectWorkbenchResponse } from "../src/api/types";


const UUID_SOURCE = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const UUID_PATTERN = new RegExp(UUID_SOURCE, "gi");
const UUID_DETECTOR = new RegExp(UUID_SOURCE, "i");
const SOURCE_PDF_PATTERN = new RegExp(
  `/api/v1/projects/${UUID_SOURCE}/source-pdf(?:$|[?#])`,
  "i",
);
const INTERMEDIATE_STATUS = /^(正在上传工程 PDF|项目已创建，等待处理|正在解析图纸并识别检验项|正在准备审核)$/;


function sanitizeDiagnostic(value: string): string {
  return value.replace(UUID_PATTERN, "<uuid>");
}


function sanitizeUrl(value: string): string {
  try {
    const url = new URL(value);
    const query = url.search === "" ? "" : "?<query>";
    return `${url.origin}${sanitizeDiagnostic(url.pathname)}${query}`;
  } catch {
    return sanitizeDiagnostic(value);
  }
}


async function submitReviewAction(
  page: Page,
  action: Locator,
): Promise<void> {
  const commandResponse = page.waitForResponse(
    (response) => (
      response.request().method() === "POST"
      && response.url().includes("/review/commands")
    ),
    { timeout: 60_000 },
  );
  const refreshedWorkbench = page.waitForResponse(
    (response) => (
      response.request().method() === "GET"
      && response.url().endsWith("/workbench")
    ),
    { timeout: 60_000 },
  );
  await expect(action).toBeEnabled();
  await action.click();
  expect((await commandResponse).ok(), "审核命令响应必须成功").toBe(true);
  expect((await refreshedWorkbench).ok(), "审核命令后的工作台刷新必须成功").toBe(true);
}


async function resolveSourceOnlyCoverage(page: Page): Promise<number> {
  const activeCount = await page.getByTestId("summary-active-count").textContent();
  await page.getByRole("button", { name: "筛选需人工处理" }).click();
  const table = page.getByRole("table", { name: "检验项列表" });
  let resolved = 0;

  for (;;) {
    const sourceRows = table.locator("[role='row'][data-source-id]:visible");
    if (await sourceRows.count() === 0) break;

    await sourceRows.first().click();
    const ignore = page.getByRole("button", {
      name: "忽略，不作为检验项",
    });
    await submitReviewAction(page, ignore);
    resolved += 1;
    expect(
      resolved,
      "待判定来源数量异常，审核循环必须有界",
    ).toBeLessThan(1_000);
  }

  await expect(page.getByTestId("summary-active-count")).toHaveText(
    activeCount?.trim() ?? "",
  );
  return resolved;
}


async function processActiveItems(page: Page, activeCount: number): Promise<void> {
  await page.getByRole("button", { name: "筛选有效项" }).click();
  const table = page.getByRole("table", { name: "检验项列表" });
  const pagination = page.getByRole("navigation", { name: "检验项分页" });
  const nextPage = pagination.getByRole("button", { name: "下一页" });
  let processed = 0;

  for (;;) {
    const activeRows = table.locator("[role='row'][data-active='true']:visible");
    const rowCount = await activeRows.count();
    for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
      await activeRows.nth(rowIndex).click();
      const selectedEditor = page.locator("article.review-selected-item[data-selected='true']");
      await expect(selectedEditor).toBeVisible();

      const acceptConfirmation = selectedEditor.getByRole("button", {
        name: /^确认候选项：/,
      });
      if (await acceptConfirmation.isEnabled()) {
        await submitReviewAction(page, acceptConfirmation);
        await expect(acceptConfirmation).toBeDisabled();
      }

      const requireBalloon = selectedEditor.getByRole("button", {
        name: /^设为需要气泡：/,
      });
      const noBalloon = selectedEditor.getByRole("button", {
        name: /^设为无需气泡：/,
      });
      if (await requireBalloon.isEnabled() && await noBalloon.isEnabled()) {
        await submitReviewAction(page, requireBalloon);
        await expect(requireBalloon).toBeDisabled();
      }

      const sip = page.getByRole("region", { name: "SIP 信息" });
      const sipDetails = sip.getByRole("group", { name: "SIP 确认字段" });
      await expect(sipDetails).toBeVisible();
      const textInputs = sipDetails.locator("input:not([type='number'])");
      await expect(textInputs).toHaveCount(5);
      const fallbackValues = [
        `自动化检验项目 ${processed + 1}`,
        "图纸要求",
        "目视与量具检验",
        "关键尺寸",
        "质量检验员",
      ];
      for (let index = 0; index < fallbackValues.length; index += 1) {
        const input = textInputs.nth(index);
        const currentValue = await input.inputValue();
        await input.fill(currentValue.trim() || fallbackValues[index]);
      }
      const sourcePage = sipDetails.locator("input[type='number']");
      await expect(sourcePage).toHaveCount(1);
      const currentPage = await sourcePage.inputValue();
      await sourcePage.fill(currentPage.trim() || "1");
      await submitReviewAction(
        page,
        sipDetails.getByRole("button", { name: "确认当前检验项 SIP" }),
      );

      processed += 1;
    }
    if (await nextPage.isDisabled()) break;
    await nextPage.click();
  }

  expect(processed, "每个有效检验项都必须完成审核命令").toBe(activeCount);
}


async function populateSipMetadata(page: Page): Promise<void> {
  const sip = page.getByRole("region", { name: "SIP 信息" });
  await sip.locator("summary")
    .filter({ hasText: "编辑项目 SIP 信息" })
    .click();
  const fields = [
    ["物料编码", "MVP-001"],
    ["产品名称", "自动化样件"],
    ["图号", "QI-MVP-001"],
    ["版本号", "A"],
    ["材质", "钢"],
  ] as const;
  for (const [label, value] of fields) {
    await sip.getByLabel(label, { exact: true }).fill(value);
  }
  await submitReviewAction(
    page,
    sip.getByRole("button", { name: "确认项目 SIP 信息" }),
  );
}


async function clickAndRefresh(
  page: Page,
  buttonName: string,
  responsePath: string,
): Promise<void> {
  const button = page.getByRole("button", { name: buttonName });
  await expect(button).toBeEnabled();
  const actionResponse = page.waitForResponse(
    (response) => (
      response.request().method() === "POST"
      && response.url().includes(responsePath)
    ),
    { timeout: 120_000 },
  );
  const refreshedWorkbench = page.waitForResponse(
    (response) => (
      response.request().method() === "GET"
      && response.url().endsWith("/workbench")
    ),
    { timeout: 120_000 },
  );
  await button.click();
  expect((await actionResponse).ok(), `${buttonName}响应必须成功`).toBe(true);
  expect((await refreshedWorkbench).ok(), `${buttonName}后的工作台刷新必须成功`).toBe(true);
}


function alternatingOffsets(limit: number, step: number): number[] {
  const offsets = [0];
  for (let value = step; value <= limit; value += step) {
    offsets.push(value, -value);
  }
  return offsets;
}


async function resolveManualBalloonPlacements(page: Page): Promise<number> {
  const summaryCount = page.getByTestId("summary-manual-count");
  const manualFilter = page.getByRole("button", { name: "筛选需人工处理" });
  await manualFilter.click();
  const table = page.getByRole("table", { name: "检验项列表" });
  const rows = table.locator("[role='row'][data-active='true']:visible");
  const xOffsets = alternatingOffsets(240, 24);
  let resolved = 0;

  while (Number((await summaryCount.textContent())?.trim()) > 0) {
    await expect(rows.first()).toBeVisible();
    const selectedItemId = await rows.first().getAttribute("data-item-id");
    if (selectedItemId === null) {
      throw new Error("需人工处理行缺少检验项标识");
    }
    await rows.first().click();
    const selected = page.locator(
      "[data-testid^='balloon-'][data-selected='true']",
    );
    await expect(selected).toHaveCount(1);
    await expect(selected).toBeVisible();
    const selectedBalloonTestId = await selected.getAttribute("data-testid");
    if (selectedBalloonTestId === null) {
      throw new Error("需人工处理气泡缺少测试标识");
    }
    const currentBalloon = page.getByTestId(selectedBalloonTestId);
    const initialCircle = (await currentBalloon.getAttribute("data-circle"))
      ?.split(",")
      .map(Number);
    if (
      initialCircle === undefined
      || initialCircle.length !== 3
      || initialCircle.some((value) => !Number.isFinite(value))
    ) {
      throw new Error("需人工处理气泡缺少可用的画布坐标");
    }
    const overlay = page.getByLabel("工程图纸标注层");
    await expect(overlay).toHaveCount(1);
    const scale = Number(await overlay.getAttribute("data-scale"));
    if (!Number.isFinite(scale) || scale <= 0) {
      throw new Error("气泡标注层缺少有效缩放比例");
    }
    const collisionFlags = (await currentBalloon.getAttribute("data-collision-flags"))
      ?.split(",") ?? [];
    const yOffsets = collisionFlags.includes("source_text_overlap")
      ? [
          -24, -48, -72, -96, -120, -144, -168, -192, -216, -240,
          0, 24, 48, 72, 96, 120, 144, 168, 192, 216, 240,
        ]
      : [
          -168, -192, -144, -216, -120, -240, -96, -72, -48, -24,
          0, 24, 48, 72, 96, 120, 144, 168, 192, 216, 240,
        ];

    let placed = false;
    for (const yOffset of yOffsets) {
      for (const xOffset of xOffsets) {
        const overlayBox = await overlay.boundingBox();
        const leader = currentBalloon.locator("line");
        const leaderPoints = await Promise.all(
          ["x1", "y1", "x2", "y2"].map(async (attribute) =>
            Number(await leader.getAttribute(attribute))
          ),
        );
        if (overlayBox === null || leaderPoints.some((value) => !Number.isFinite(value))) {
          throw new Error("需人工处理气泡当前不可拖动");
        }
        const [x1, y1, x2, y2] = leaderPoints;
        const startX = overlayBox.x + ((x1 + x2) / 2) * scale;
        const startY = overlayBox.y + ((y1 + y2) / 2) * scale;
        const targetX = overlayBox.x + (initialCircle[0] + xOffset) * scale;
        const targetY = overlayBox.y + (initialCircle[1] + yOffset) * scale;
        if (
          targetX <= 2 || targetX >= 1563
          || targetY <= 2 || targetY >= 794
        ) {
          continue;
        }

        const moveResponse = page.waitForResponse(
          (response) => (
            response.request().method() === "POST"
            && response.url().includes("/balloons/commands")
          ),
          { timeout: 60_000 },
        );
        const moveRefresh = page.waitForResponse(
          (response) => (
            response.request().method() === "GET"
            && response.url().endsWith("/workbench")
          ),
          { timeout: 60_000 },
        );
        await page.mouse.move(startX, startY);
        await page.mouse.down();
        await page.mouse.move(targetX, targetY, { steps: 3 });
        await page.mouse.up();
        expect((await moveResponse).ok(), "人工气泡调整命令响应必须成功")
          .toBe(true);
        const refreshedResponse = await moveRefresh;
        expect(refreshedResponse.ok(), "人工气泡调整后的工作台刷新必须成功")
          .toBe(true);
        const refreshedWorkbench = await refreshedResponse.json() as
          ProjectWorkbenchResponse;
        const refreshedBalloon = refreshedWorkbench.balloons.find(
          (balloon) => (
            balloon.inspection_item_id === selectedItemId
            && balloon.status === "active"
          ),
        );
        if (refreshedBalloon === undefined) {
          throw new Error("人工调整后的工作台缺少当前气泡");
        }

        if (
          refreshedBalloon.placement_status === "placed"
          && refreshedBalloon.collision_flags.length === 0
        ) {
          placed = true;
          break;
        }
        await expect(currentBalloon).toHaveAttribute(
          "data-placement-status",
          refreshedBalloon.placement_status,
        );
        await expect(currentBalloon).toHaveAttribute(
          "data-collision-flags",
          refreshedBalloon.collision_flags.join(","),
        );
      }
      if (placed) break;
    }
    expect(placed, "每个需人工处理气泡都必须通过可见拖动找到合法位置")
      .toBe(true);
    await expect.poll(
      async () => rows.evaluateAll(
        (currentRows, itemId) => currentRows.some(
          (row) => row.getAttribute("data-item-id") === itemId,
        ),
        selectedItemId,
      ),
      { message: "人工调整后当前气泡必须离开需人工处理列表" },
    ).toBe(false);
    resolved += 1;
    expect(resolved, "需人工处理气泡数量异常，调整循环必须有界")
      .toBeLessThan(500);
  }

  return resolved;
}


async function verifyDownload(
  page: Page,
  label: string,
  kind: "ballooned_pdf" | "sip_excel",
  extension: ".pdf" | ".xlsx",
  signature: Buffer,
): Promise<void> {
  const link = page.getByRole("link", { name: label });
  await expect(link).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 120_000 }),
    link.click(),
  ]);
  expect(
    download.url().includes(`/downloads/${kind}`),
    `${label}必须来自 canonical 下载地址`,
  ).toBe(true);
  const downloadFailure = await download.failure();
  expect(
    downloadFailure === null,
    `${label}下载失败：${sanitizeDiagnostic(downloadFailure ?? "")}`,
  ).toBe(true);
  expect(
    download.suggestedFilename().toLowerCase().endsWith(extension),
    `${label}文件扩展名必须为 ${extension}`,
  ).toBe(true);
  const downloadPath = await download.path();
  if (downloadPath === null) throw new Error(`${label}没有本地临时文件`);
  const content = await readFile(downloadPath);
  expect(content.byteLength, `${label}必须为非空文件`).toBeGreaterThan(0);
  expect(
    content.subarray(0, signature.byteLength).equals(signature),
    `${label}文件签名必须有效`,
  ).toBe(true);
}


test("裸根地址可完成 PDF 上传、审核和双格式下载", async ({ page }) => {
  test.setTimeout(30 * 60_000);

  const sourcePdf = process.env.QI_MVP_E2E_PDF;
  if (!sourcePdf) throw new Error("QI_MVP_E2E_PDF is required");

  const consoleErrors: string[] = [];
  const failedResponses: string[] = [];
  const requestFailures: string[] = [];
  const sourcePdfAborts: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(sanitizeDiagnostic(message.text()));
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push(`${response.status()} ${sanitizeUrl(response.url())}`);
    }
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "unknown request failure";
    const sanitized = `${request.method()} ${sanitizeUrl(request.url())}: ${
      sanitizeDiagnostic(failure)
    }`;
    if (
      request.method() === "GET"
      && SOURCE_PDF_PATTERN.test(request.url())
      && /ERR_ABORTED/i.test(failure)
    ) {
      sourcePdfAborts.push(sanitized);
      return;
    }
    requestFailures.push(sanitized);
  });

  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "工程图纸智能检验" })).toBeVisible();
  await page.getByLabel("选择工程 PDF").setInputFiles(sourcePdf);
  await page.getByRole("button", { name: "上传并开始识别" }).click();
  await expect(page.getByText(INTERMEDIATE_STATUS, { exact: true }).first())
    .toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("region", { name: "项目摘要" }))
    .toBeVisible({ timeout: 10 * 60_000 });
  const candidateMarkers = page.getByRole("button", {
    name: /^候选气泡 [1-9]\d*$/,
  });
  await expect(candidateMarkers.first()).toBeVisible();
  expect(
    await candidateMarkers.count(),
    "审核前必须显示正整数候选气泡序号",
  ).toBeGreaterThan(0);
  expect(new URL(page.url()).search, "产品 URL 不得包含 query").toBe("");

  const activeCountText = await page.getByTestId("summary-active-count").textContent();
  const activeCount = Number(activeCountText?.trim());
  expect(activeCount, "有效检验项数量必须大于零").toBeGreaterThan(0);
  const pdfWorkspace = page.getByTestId("pdf-workspace");
  const pdfCanvas = page.getByTestId("pdf-canvas");
  await expect(pdfWorkspace).toBeVisible();
  await expect(pdfCanvas).toBeVisible();
  await expect(pdfCanvas).toHaveAttribute("width", /^[1-9]\d*$/);
  await expect(pdfCanvas).toHaveAttribute("height", /^[1-9]\d*$/);
  const candidateScreenshot = process.env.QI_MVP_CANDIDATE_SCREENSHOT;
  if (candidateScreenshot) {
    await page.screenshot({ path: candidateScreenshot });
  }

  await resolveSourceOnlyCoverage(page);
  await processActiveItems(page, activeCount);
  await populateSipMetadata(page);
  await clickAndRefresh(page, "冻结检验项", "/review/freeze");
  await clickAndRefresh(page, "生成气泡", "/balloons/generate");
  await expect(page.getByRole("button", { name: /^候选气泡 / })).toHaveCount(0);
  const generatedBalloons = page.getByRole("button", {
    name: /^气泡 [1-9]\d*(?:，需人工处理)?$/,
  });
  await expect(generatedBalloons.first()).toBeVisible();
  expect(
    await generatedBalloons.count(),
    "生成后必须显示正式气泡编号",
  ).toBeGreaterThan(0);

  const activeRows = page.getByRole("table", { name: "检验项列表" })
    .locator("[role='row'][data-active='true']:visible");
  await expect(activeRows.first()).toBeVisible();
  await activeRows.first().click();
  const selectedBalloon = page.locator(
    "[data-testid^='balloon-'][data-selected='true']",
  );
  await expect(selectedBalloon).toHaveCount(1);
  await expect(selectedBalloon).toBeVisible();
  await expect(selectedBalloon).toHaveAttribute(
    "aria-label",
    /^气泡 [1-9]\d*(?:，需人工处理)?$/,
  );
  await expect(selectedBalloon.locator("text")).toHaveText(/^[1-9]\d*$/);
  await selectedBalloon.click();
  await expect(activeRows.first()).toHaveAttribute("data-selected", "true");

  const balloonBox = await selectedBalloon.boundingBox();
  if (balloonBox === null) throw new Error("所选气泡没有可拖动的可见几何");
  const moveResponse = page.waitForResponse(
    (response) => (
      response.request().method() === "POST"
      && response.url().includes("/balloons/commands")
    ),
    { timeout: 60_000 },
  );
  const moveRefresh = page.waitForResponse(
    (response) => (
      response.request().method() === "GET"
      && response.url().endsWith("/workbench")
    ),
    { timeout: 60_000 },
  );
  const centerX = balloonBox.x + balloonBox.width / 2;
  const centerY = balloonBox.y + balloonBox.height / 2;
  await page.mouse.move(centerX, centerY);
  await page.mouse.down();
  await page.mouse.move(centerX + 6, centerY, { steps: 3 });
  await page.mouse.up();
  expect((await moveResponse).ok(), "气泡拖动命令响应必须成功").toBe(true);
  expect((await moveRefresh).ok(), "气泡拖动后的工作台刷新必须成功").toBe(true);

  const resolvedManualBalloons = await resolveManualBalloonPlacements(page);
  expect(resolvedManualBalloons, "真实 PDF 必须覆盖人工气泡调整残余路径")
    .toBeGreaterThan(0);
  await expect(page.getByTestId("summary-manual-count")).toHaveText("0");
  await expect(page.getByTestId("summary-collision-count")).toHaveText("0");
  await page.getByRole("button", { name: "筛选全部" }).click();
  await page.getByRole("table", { name: "检验项列表" })
    .locator("[role='row'][data-active='true']:visible")
    .first()
    .click();
  const numberedScreenshot = process.env.QI_MVP_NUMBERED_SCREENSHOT;
  if (numberedScreenshot) {
    await page.screenshot({ path: numberedScreenshot });
  }
  await expect(page.getByRole("button", { name: "确认审核结果" })).toBeEnabled();
  await clickAndRefresh(page, "确认审核结果", "/review/confirm");

  const openButton = page.getByRole("button", {
    name: "展开导出与处理信息",
  });
  if (await openButton.count() > 0) await openButton.click();
  const exportResponse = page.waitForResponse(
    (response) => (
      response.request().method() === "POST"
      && /\/api\/v1\/projects\/[^/]+\/exports$/.test(response.url())
    ),
    { timeout: 120_000 },
  );
  const exportButton = page.getByRole("button", { name: "生成正式文件" });
  await expect(exportButton).toBeEnabled();
  await exportButton.click();
  expect((await exportResponse).ok(), "正式导出响应必须成功").toBe(true);

  const downloadRegion = page.getByRole("navigation", { name: "正式文件下载" });
  await expect(downloadRegion).toBeVisible({ timeout: 120_000 });
  await expect(downloadRegion.getByRole("link", { name: "下载校验清单" }))
    .toBeVisible();
  await verifyDownload(
    page,
    "下载带气泡 PDF",
    "ballooned_pdf",
    ".pdf",
    Buffer.from("%PDF-", "ascii"),
  );
  await verifyDownload(
    page,
    "下载 SIP Excel",
    "sip_excel",
    ".xlsx",
    Buffer.from([0x50, 0x4b, 0x03, 0x04]),
  );

  const visibleText = await page.locator("body").innerText();
  expect(
    UUID_DETECTOR.test(visibleText),
    "页面可见文本不得包含内部 UUID",
  ).toBe(false);
  const finalUrl = new URL(page.url());
  expect(finalUrl.pathname, "产品 URL 必须保持裸根路径").toBe("/");
  expect(finalUrl.search, "产品 URL 不得包含 query").toBe("");
  expect(
    UUID_DETECTOR.test(finalUrl.href),
    "产品 URL 不得包含内部 UUID",
  ).toBe(false);

  if (sourcePdfAborts.length > 0) {
    await expect(pdfCanvas).toBeVisible();
    await expect(pdfCanvas).toHaveAttribute("width", /^[1-9]\d*$/);
    await expect(pdfCanvas).toHaveAttribute("height", /^[1-9]\d*$/);
    await expect(page.getByText("PDF 页面渲染失败，请切换页面后重试。"))
      .toHaveCount(0);
  }
  const unexplainedConsoleErrors = consoleErrors.filter(
    (message) => !(
      sourcePdfAborts.length > 0
      && /ERR_ABORTED/i.test(message)
    ),
  );
  expect(unexplainedConsoleErrors, "不得出现未解释的 console error").toEqual([]);
  expect(failedResponses, "不得出现 HTTP >= 400 响应").toEqual([]);
  expect(requestFailures, "不得出现未解释的请求失败").toEqual([]);
});
