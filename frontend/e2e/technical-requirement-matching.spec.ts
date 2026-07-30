import {
  expect,
  test,
  type Page,
  type TestInfo,
} from "@playwright/test";

import type {
  ProjectWorkbenchResponse,
  ReviewWorkingCopy,
} from "../src/api/types";


async function workbench(
  page: Page,
  projectId: string,
): Promise<ProjectWorkbenchResponse> {
  return await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/projects/${id}/workbench`);
    if (!response.ok) {
      throw new Error(`workbench request failed: ${response.status}`);
    }
    return await response.json() as ProjectWorkbenchResponse;
  }, projectId);
}


async function projectIdentity(page: Page): Promise<{
  projectId: string;
  operatorId: string;
}> {
  const projectId = await page.evaluate(
    () => window.sessionStorage.getItem("qi.current-project-id"),
  );
  const operatorId = await page.evaluate(
    () => window.localStorage.getItem("qi.local-operator-id"),
  );
  if (!projectId || !operatorId) {
    throw new Error("real-PDF acceptance requires project and operator identity");
  }
  return { projectId, operatorId };
}


async function confirmSelectedSip(page: Page): Promise<void> {
  const standard = page.getByLabel(/^检验标准：/);
  await expect(standard).not.toHaveValue("");
  await expect(page.getByLabel(/^检验项目：/)).not.toHaveValue("");
  await page.getByLabel(/^检验方法：/).fill("目视与量具检验");
  await page.getByLabel(/^关键尺寸：/).fill("是");
  await page.getByLabel(/^检验角色：/).fill("质量检验员");
  const pageField = page.getByLabel(/^页码：/);
  if (await pageField.inputValue() === "") await pageField.fill("1");

  const commandResponse = page.waitForResponse((candidate) => (
    candidate.request().method() === "POST"
    && candidate.url().includes("/review/commands")
  ));
  const refreshResponse = page.waitForResponse((candidate) => (
    candidate.request().method() === "GET"
    && candidate.url().includes("/workbench")
  ));
  await page.getByRole("button", { name: "确认当前检验项 SIP" }).click();
  expect((await commandResponse).ok()).toBe(true);
  expect((await refreshResponse).ok()).toBe(true);
}


function recordRuntimeFailures(page: Page): {
  consoleErrors: string[];
  failedResponses: string[];
  requestFailures: string[];
} {
  const consoleErrors: string[] = [];
  const failedResponses: string[] = [];
  const requestFailures: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    if (
      request.method() === "GET"
      && request.url().includes("/source-pdf")
      && /ERR_ABORTED/i.test(request.failure()?.errorText ?? "")
    ) {
      return;
    }
    requestFailures.push(
      `${request.method()} ${request.url()}: ${
        request.failure()?.errorText ?? "unknown failure"
      }`,
    );
  });
  return { consoleErrors, failedResponses, requestFailures };
}


test("真实工程 PDF 自动识别六条技术要求并持久化匹配与 SIP 确认", async ({
  page,
}, testInfo: TestInfo) => {
  test.setTimeout(20 * 60_000);
  page.setDefaultTimeout(15_000);
  const sourcePdf = process.env.QI_MVP_E2E_PDF;
  const existingProjectId = process.env.QI_MVP_E2E_PROJECT_ID;
  const existingOperatorId = process.env.QI_MVP_E2E_OPERATOR_ID;
  const runtimeFailures = recordRuntimeFailures(page);

  if (existingProjectId) {
    if (!existingOperatorId) {
      throw new Error(
        "QI_MVP_E2E_OPERATOR_ID is required with QI_MVP_E2E_PROJECT_ID",
      );
    }
    await page.addInitScript(({ operatorId, projectId }) => {
      window.localStorage.setItem("qi.local-operator-id", operatorId);
      window.sessionStorage.setItem("qi.current-project-id", projectId);
    }, {
      operatorId: existingOperatorId,
      projectId: existingProjectId,
    });
    await page.goto("/", { waitUntil: "networkidle" });
  } else {
    if (!sourcePdf) throw new Error("QI_MVP_E2E_PDF is required");
    await page.goto("/", { waitUntil: "networkidle" });
    await page.getByLabel("选择工程 PDF").setInputFiles(sourcePdf);
    await page.getByRole("button", { name: "上传并开始识别" }).click();
  }
  await expect(page.getByRole("region", { name: "项目摘要" }))
    .toBeVisible({ timeout: 15 * 60_000 });

  const identity = await projectIdentity(page);
  const initial = await workbench(page, identity.projectId);
  const requirements = initial.working_copy.technical_requirements ?? [];
  expect(requirements).toHaveLength(6);
  expect(
    requirements.find(
      (item) => item.subtype === "general_dimensional_tolerance",
    )?.match_outcome,
  ).toBe("matched_items");
  const globalItems = initial.working_copy.items.filter(
    (item) => item.item_type === "general_requirement" && item.active,
  );
  expect(globalItems.length).toBeGreaterThan(0);
  expect(globalItems.every((item) => item.balloon_required === false)).toBe(true);

  const panel = page.getByRole("region", { name: "技术要求匹配" });
  await expect(panel).toBeVisible();
  for (const text of [
    /未标注倒角\s*C0\.5/,
    /锐边去毛刺/,
    /零件表面不应有划痕、擦伤等损伤零件外观的缺陷/,
    /阳极氧化亮光银色/,
    /GB\s*\/\s*T\s*1804-m/,
    /GB\s*\/\s*T\s*1184-k/,
  ]) {
    await expect(panel.getByText(text)).toBeVisible();
  }

  const dimensional = requirements.find(
    (item) => item.subtype === "general_dimensional_tolerance",
  );
  if (!dimensional || dimensional.matched_candidate_ids.length === 0) {
    throw new Error("dimensional requirement must have a matched target");
  }
  const matchedItemId = dimensional.matched_candidate_ids[0];
  const dimensionalEntry = panel.locator("li").filter({
    hasText: "GB/T1804-m",
  });
  await dimensionalEntry.getByRole("button", {
    name: /^查看匹配检验项：/,
  }).first().click();
  await expect(page.locator(
    `[role="row"][data-item-id="${matchedItemId}"]`,
  )).toHaveAttribute("data-selected", "true");
  await expect(page.locator(
    `.pdf-overlay-candidate[data-selected="true"]`,
  ).first()).toBeVisible();

  await confirmSelectedSip(page);
  let afterSip = await workbench(page, identity.projectId);
  expect(
    afterSip.working_copy.items.find(
      (item) => item.item_id === matchedItemId,
    )?.sip_detail_fields_confirmed,
  ).toBe(true);

  const geometricEntry = panel.locator("li").filter({
    hasText: "GB/T1184-k",
  });
  const details = geometricEntry.locator("details");
  if (!(await details.evaluate((element) => element.hasAttribute("open")))) {
    await details.locator("summary").click();
  }
  const overrideResponse = page.waitForResponse((candidate) => (
    candidate.request().method() === "POST"
    && candidate.url().includes("/review/commands")
  ));
  const overrideRefresh = page.waitForResponse((candidate) => (
    candidate.request().method() === "GET"
    && candidate.url().includes("/workbench")
  ));
  await details.getByRole("button", {
    name: /^匹配此检验项：/,
  }).first().click();
  expect((await overrideResponse).ok()).toBe(true);
  expect((await overrideRefresh).ok()).toBe(true);

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByRole("region", { name: "技术要求匹配" })).toBeVisible();
  const persisted = await workbench(page, identity.projectId);
  const persistedGeometric = (
    persisted.working_copy.technical_requirements ?? []
  ).find((item) => item.subtype === "general_geometric_tolerance");
  expect(persistedGeometric?.match_outcome).toBe("matched_items");
  expect(persistedGeometric?.matched_candidate_ids).toHaveLength(1);
  expect(
    persisted.working_copy.items.find(
      (item) => item.item_id === matchedItemId,
    )?.sip_detail_fields_confirmed,
  ).toBe(true);

  await page.screenshot({
    path: testInfo.outputPath("technical-requirement-matching.png"),
    fullPage: true,
  });
  expect(runtimeFailures.consoleErrors).toEqual([]);
  expect(runtimeFailures.failedResponses).toEqual([]);
  expect(runtimeFailures.requestFailures).toEqual([]);
});
