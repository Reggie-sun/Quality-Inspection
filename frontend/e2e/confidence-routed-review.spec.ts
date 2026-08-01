import { expect, test, type Page } from "@playwright/test";

import type {
  BalloonRecord,
  ExportJob,
  ProjectWorkbenchResponse,
  ReviewCommand,
  ReviewItem,
  ReviewWorkingCopy,
} from "../src/api/types";


const EDITABLE_TYPES = new Set([
  "linear_dimension",
  "diameter_dimension",
  "thread",
  "radius",
  "angle",
]);


type ApiResult<T> = {
  status: number;
  payload: T;
};

type ReviewedResult = {
  id: string;
  schema_version: string;
  items: ReviewItem[];
  balloons: BalloonRecord[];
};

type ErrorPayload = {
  error?: {
    code?: string;
    blockers?: string[];
  };
};

type Manifest = {
  schema_version: string;
  export_id: string;
  project_id: string;
  reviewed_result_id: string;
  confidence_policy_versions: string[];
  auto_accepted_item_count: number;
  manual_override_item_count: number;
  artifacts: Array<{
    kind: string;
    reviewed_result_id: string;
  }>;
};


function isAutoAccepted(item: ReviewItem): boolean {
  return item.active === true
    && item.status === "auto_accepted"
    && item.requires_confirmation === false
    && item.acceptance_source === "confidence_policy"
    && item.confidence_decision?.band === "high"
    && item.confidence_decision.review_disposition === "auto_accepted"
    && item.confidence_decision.policy_version === "candidate-confidence/1";
}


function requiresManualReview(item: ReviewItem): boolean {
  return item.active && item.requires_confirmation === true;
}


async function apiRequest<T>(
  page: Page,
  path: string,
  method = "GET",
  body?: unknown,
  operatorId?: string,
): Promise<ApiResult<T>> {
  return await page.evaluate(
    async ({ requestPath, requestMethod, requestBody, operator }) => {
      const headers: Record<string, string> = {
        Accept: "application/json",
      };
      if (requestBody !== undefined) headers["Content-Type"] = "application/json";
      if (operator !== undefined) headers["X-QI-Operator"] = operator;
      const response = await fetch(requestPath, {
        method: requestMethod,
        headers,
        body: requestBody === undefined
          ? undefined
          : JSON.stringify(requestBody),
      });
      return {
        status: response.status,
        payload: await response.json(),
      };
    },
    {
      requestPath: path,
      requestMethod: method,
      requestBody: body,
      operator: operatorId,
    },
  ) as ApiResult<T>;
}


async function workbench(
  page: Page,
  projectId: string,
): Promise<ProjectWorkbenchResponse> {
  const response = await apiRequest<ProjectWorkbenchResponse>(
    page,
    `/api/v1/projects/${projectId}/workbench`,
  );
  expect(response.status).toBe(200);
  return response.payload;
}


async function reviewCommand(
  page: Page,
  projectId: string,
  operatorId: string,
  expectedVersion: number,
  command: ReviewCommand,
): Promise<ReviewWorkingCopy> {
  const response = await apiRequest<ReviewWorkingCopy>(
    page,
    `/api/v1/projects/${projectId}/review/commands`,
    "POST",
    { expected_version: expectedVersion, command },
    operatorId,
  );
  expect(response.status, `review command ${command.type} must succeed`).toBe(200);
  return response.payload;
}


async function collectDefaultQueue(page: Page): Promise<{
  itemIds: string[];
  sourceIds: string[];
}> {
  const pagination = page.getByRole("navigation", { name: "检验项分页" });
  const previous = pagination.getByRole("button", { name: "上一页" });
  const next = pagination.getByRole("button", { name: "下一页" });
  const table = page.getByRole("table", { name: "检验项列表" });
  while (!(await previous.isDisabled())) await previous.click();

  const itemIds: string[] = [];
  const sourceIds: string[] = [];
  for (;;) {
    itemIds.push(...await table.locator(
      "[role='row'][data-item-id]:visible",
    ).evaluateAll((rows) => rows.map(
      (row) => row.getAttribute("data-item-id") ?? "",
    )));
    sourceIds.push(...await table.locator(
      "[role='row'][data-source-id]:visible",
    ).evaluateAll((rows) => rows.map(
      (row) => row.getAttribute("data-source-id") ?? "",
    )));
    if (await next.isDisabled()) break;
    await next.click();
  }
  while (!(await previous.isDisabled())) await previous.click();
  return {
    itemIds: itemIds.filter(Boolean).sort(),
    sourceIds: sourceIds.filter(Boolean).sort(),
  };
}


async function selectTableItem(page: Page, itemId: string): Promise<void> {
  const pagination = page.getByRole("navigation", { name: "检验项分页" });
  const previous = pagination.getByRole("button", { name: "上一页" });
  const next = pagination.getByRole("button", { name: "下一页" });
  while (!(await previous.isDisabled())) await previous.click();
  for (;;) {
    const row = page.locator(`[role='row'][data-item-id='${itemId}']`);
    if (await row.count() > 0) {
      await row.click();
      return;
    }
    if (await next.isDisabled()) break;
    await next.click();
  }
  throw new Error(`table item ${itemId} is not present in the selected filter`);
}


async function resolveManualReview(
  page: Page,
  projectId: string,
  operatorId: string,
  initial: ReviewWorkingCopy,
): Promise<ReviewWorkingCopy> {
  let current = initial;
  const sourceObservationIds = (current.coverage.entries ?? [])
    .filter((entry) => (
      entry.requires_confirmation
      && (entry.candidate_id === null || entry.candidate_id === undefined)
    ))
    .map((entry) => entry.observation_id);
  if (sourceObservationIds.length > 0) {
    current = await reviewCommand(
      page,
      projectId,
      operatorId,
      current.version,
      { type: "ignore_sources", observation_ids: sourceObservationIds },
    );
  }

  for (;;) {
    const item = current.items.find(requiresManualReview);
    if (item === undefined) break;
    current = await reviewCommand(
      page,
      projectId,
      operatorId,
      current.version,
      item.requires_confirmation === true
        ? {
            type: "resolve_confirmation",
            item_id: item.item_id,
            accepted: true,
          }
        : { type: "keep", item_id: item.item_id },
    );
  }

  for (const item of current.items.filter(
    (candidate) => candidate.active && candidate.balloon_required == null,
  )) {
    current = await reviewCommand(
      page,
      projectId,
      operatorId,
      current.version,
      {
        type: "set_balloon_required",
        item_id: item.item_id,
        balloon_required: true,
      },
    );
  }
  return current;
}


async function confirmSip(
  page: Page,
  projectId: string,
  operatorId: string,
  initial: ReviewWorkingCopy,
): Promise<ReviewWorkingCopy> {
  let current = await reviewCommand(
    page,
    projectId,
    operatorId,
    initial.version,
    {
      type: "set_sip_metadata",
      material_code: "CONF-ROUTE-001",
      material_name: "置信度路由验证件",
      drawing_number: "QI-CONFIDENCE-001",
      material: "钢",
      revision: "A",
    },
  );
  for (const [index, item] of current.items.filter(
    (candidate) => candidate.active,
  ).entries()) {
    current = await reviewCommand(
      page,
      projectId,
      operatorId,
      current.version,
      {
        type: "set_sip_detail_fields",
        item_id: item.item_id,
        inspection_item: item.inspection_item?.trim()
          || item.raw_text.trim()
          || `检验项目 ${index + 1}`,
        inspection_standard: item.inspection_standard?.trim() || "图纸要求",
        inspection_method: item.inspection_method?.trim() || "目视与量具检验",
        key_dimension: item.key_dimension?.trim() || "关键尺寸",
        inspection_role: item.inspection_role?.trim() || "质量检验员",
        source_page: Number.isInteger(item.source_page) && (item.source_page ?? 0) > 0
          ? item.source_page as number
          : (item.page_index ?? 0) + 1,
        remarks: item.remarks ?? "",
      },
    );
  }
  return current;
}


function alternatingOffsets(limit: number, step: number): number[] {
  const offsets = [0];
  for (let value = step; value <= limit; value += step) {
    offsets.push(value, -value);
  }
  return offsets;
}


async function resolveBalloonBlockers(page: Page): Promise<number> {
  const manualCount = page.getByTestId("summary-manual-count");
  const collisionCount = page.getByTestId("summary-collision-count");
  const table = page.getByRole("table", { name: "检验项列表" });
  const xOffsets = alternatingOffsets(240, 24);
  let resolved = 0;

  while (
    Number((await manualCount.textContent())?.trim()) > 0
    || Number((await collisionCount.textContent())?.trim()) > 0
  ) {
    const manual = Number((await manualCount.textContent())?.trim()) > 0;
    await page.getByRole("button", {
      name: manual ? "筛选需人工处理" : "筛选硬碰撞",
    }).click();
    const row = table.locator(
      "[role='row'][data-item-id][data-active='true']:visible",
    ).first();
    await expect(row).toBeVisible();
    const itemId = await row.getAttribute("data-item-id");
    if (itemId === null) throw new Error("blocked balloon row has no item id");
    await row.click();
    const balloon = page.locator(
      `[data-testid^='balloon-'][data-item-id='${itemId}'][data-selected='true']`,
    );
    await expect(balloon).toBeVisible();
    const initialCircle = (await balloon.getAttribute("data-circle"))
      ?.split(",")
      .map(Number);
    if (
      initialCircle === undefined
      || initialCircle.length !== 3
      || initialCircle.some((value) => !Number.isFinite(value))
    ) {
      throw new Error("blocked balloon has no usable geometry");
    }
    const overlay = page.getByLabel("工程图纸标注层");
    const scale = Number(await overlay.getAttribute("data-scale"));
    if (!Number.isFinite(scale) || scale <= 0) {
      throw new Error("balloon overlay has no usable scale");
    }

    let placed = false;
    for (const yOffset of alternatingOffsets(160, 24)) {
      for (const xOffset of xOffsets) {
        const current = page.locator(
          `[data-testid^='balloon-'][data-item-id='${itemId}']`,
        );
        const box = await current.boundingBox();
        const circle = (await current.getAttribute("data-circle"))
          ?.split(",")
          .map(Number);
        if (box === null || circle === undefined || circle.length !== 3) continue;
        const response = page.waitForResponse((candidate) => (
          candidate.request().method() === "POST"
          && candidate.url().includes("/balloons/commands")
        ));
        const refresh = page.waitForResponse((candidate) => (
          candidate.request().method() === "GET"
          && candidate.url().endsWith("/workbench")
        ));
        const startX = box.x + box.width / 2;
        const startY = box.y + box.height / 2;
        const targetX = startX + (
          initialCircle[0] + xOffset - circle[0]
        ) * scale;
        const targetY = startY + (
          initialCircle[1] + yOffset - circle[1]
        ) * scale;
        await page.mouse.move(startX, startY);
        await page.mouse.down();
        await page.mouse.move(targetX, targetY, { steps: 3 });
        await page.mouse.up();
        expect((await response).ok()).toBe(true);
        const updated = await (await refresh).json() as ProjectWorkbenchResponse;
        const updatedBalloon = updated.balloons.find(
          (candidate) => (
            candidate.inspection_item_id === itemId
            && candidate.status === "active"
          ),
        );
        if (
          updatedBalloon?.placement_status === "placed"
          && updatedBalloon.collision_flags.length === 0
        ) {
          placed = true;
          break;
        }
      }
      if (placed) break;
    }
    expect(placed, `balloon ${itemId} must be manually placeable`).toBe(true);
    resolved += 1;
    expect(resolved, "balloon blocker loop must be bounded").toBeLessThan(500);
  }
  return resolved;
}


test("confidence policy routes only exceptions to review and preserves publication owners", async ({
  page,
}) => {
  test.setTimeout(30 * 60_000);
  const sourcePdf = process.env.QI_MVP_E2E_PDF;
  if (!sourcePdf) throw new Error("QI_MVP_E2E_PDF is required");

  let reviewCommandPosts = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST"
      && request.url().includes("/review/commands")
    ) {
      reviewCommandPosts += 1;
    }
  });

  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByLabel("选择工程 PDF").setInputFiles(sourcePdf);
  await page.getByRole("button", { name: "上传并开始识别" }).click();
  await expect(page.getByRole("region", { name: "项目摘要" }))
    .toBeVisible({ timeout: 20 * 60_000 });
  const projectId = await page.evaluate(
    () => window.sessionStorage.getItem("qi.current-project-id"),
  );
  const operatorId = await page.evaluate(
    () => window.localStorage.getItem("qi.local-operator-id"),
  );
  if (!projectId || !operatorId) {
    throw new Error("local project/operator identity is required");
  }

  const initial = await workbench(page, projectId);
  const active = initial.working_copy.items.filter((item) => item.active);
  const byBand = {
    high: active.filter((item) => item.confidence_decision?.band === "high"),
    medium: active.filter((item) => item.confidence_decision?.band === "medium"),
    low: active.filter((item) => item.confidence_decision?.band === "low"),
  };
  expect(byBand.high.length, "approved PDF must produce high decisions")
    .toBeGreaterThan(0);
  expect(byBand.medium.length, "approved PDF must produce medium decisions")
    .toBeGreaterThan(0);
  expect(byBand.low.length, "approved PDF must produce low decisions")
    .toBeGreaterThan(0);
  expect(byBand.high.every(isAutoAccepted)).toBe(true);
  for (const [band, items] of [
    ["medium", byBand.medium],
    ["low", byBand.low],
  ] as const) {
    for (const item of items) {
      expect(item.confidence_decision?.band).toBe(band);
      expect(item.confidence_decision?.review_disposition).toBe(
        "review_required",
      );
      expect(item.confidence_decision?.policy_version).toBe(
        "candidate-confidence/1",
      );
      expect(item.requires_confirmation).toBe(true);
    }
  }

  const expectedReviewItems = active.filter(requiresManualReview)
    .map((item) => item.item_id)
    .sort();
  const expectedReviewSources = (initial.working_copy.coverage.entries ?? [])
    .filter((entry) => (
      entry.requires_confirmation
      && (entry.candidate_id === null || entry.candidate_id === undefined)
    ))
    .map((entry) => entry.source_location_id)
    .sort();
  await expect(page.getByRole("button", { name: "筛选待人工审核" }))
    .toHaveAttribute("data-active", "true");
  const defaultQueue = await collectDefaultQueue(page);
  expect(defaultQueue.itemIds).toEqual(expectedReviewItems);
  expect(defaultQueue.sourceIds).toEqual(expectedReviewSources);
  expect(initial.working_copy.manual_review_count).toBe(
    expectedReviewItems.length + expectedReviewSources.length,
  );

  const editableHigh = byBand.high.find((item) => (
    item.balloon_required === true
    && EDITABLE_TYPES.has(item.item_type ?? "")
    && initial.candidates.some((candidate) => candidate.item_id === item.item_id)
  ));
  if (editableHigh === undefined) {
    throw new Error("approved PDF must produce one editable high balloon candidate");
  }
  const immutableDecision = structuredClone(editableHigh.confidence_decision);
  await page.getByRole("button", { name: "筛选自动通过" }).click();
  await selectTableItem(page, editableHigh.item_id);
  const highRow = page.locator(
    `[role='row'][data-item-id='${editableHigh.item_id}']`,
  );
  const provisional = page.locator(
    `[data-testid^='candidate-number-'][data-item-id='${editableHigh.item_id}']`,
  );
  await expect(provisional).toBeVisible();
  const provisionalLabel = await provisional.getAttribute("aria-label");
  const candidateNumberMatch = provisionalLabel?.match(
    /^自动通过气泡 ([1-9]\d*)$/,
  );
  if (candidateNumberMatch === undefined || candidateNumberMatch === null) {
    throw new Error("auto-accepted marker has no deterministic candidate number");
  }
  const candidateNumber = candidateNumberMatch[1];
  await expect(provisional).toHaveAttribute("data-item-id", editableHigh.item_id);
  await expect(highRow).toHaveAttribute("data-item-id", editableHigh.item_id);
  await expect(highRow.locator(".inspection-number")).toHaveAttribute(
    "aria-label",
    `自动通过气泡 ${candidateNumber}`,
  );
  await expect(provisional).toHaveAttribute(
    "data-review-disposition",
    "auto_accepted",
  );
  await expect(provisional.locator("circle")).toHaveAttribute(
    "stroke",
    "#c23b3b",
  );
  expect(reviewCommandPosts, "showing high marker must not submit review commands")
    .toBe(0);
  await provisional.click();
  await expect(highRow).toHaveAttribute("data-selected", "true");
  const selectedEditor = page.locator(
    "article.review-selected-item[data-selected='true']",
  );
  await expect(selectedEditor).toHaveAttribute(
    "aria-label",
    new RegExp(`^检验项 ${candidateNumber} · `),
  );
  await expect(selectedEditor).toContainText(editableHigh.raw_text);
  await expect(selectedEditor.getByRole("group", { name: "置信度依据" }))
    .toContainText("candidate-confidence/1");

  const editableField = selectedEditor.locator(
    ".review-field-group--parsed input",
  ).first();
  await expect(editableField).toBeVisible();
  await editableField.fill((await editableField.inputValue()) === "1" ? "2" : "1");
  const saveResponse = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes("/review/commands")
  ));
  const saveRefresh = page.waitForResponse((response) => (
    response.request().method() === "GET"
    && response.url().endsWith("/workbench")
  ));
  await selectedEditor.getByRole("button", {
    name: /^保存修改检验项：/,
  }).click();
  expect((await saveResponse).ok()).toBe(true);
  expect((await saveRefresh).ok()).toBe(true);
  await page.reload({ waitUntil: "networkidle" });
  let current = await workbench(page, projectId);
  const overridden = current.working_copy.items.find(
    (item) => item.item_id === editableHigh.item_id,
  );
  expect(overridden?.acceptance_source).toBe("manual_override");
  expect(overridden?.status).toBe("kept");
  expect(overridden?.requires_confirmation).toBe(false);
  expect(overridden?.confidence_decision).toEqual(immutableDecision);

  current.working_copy = await resolveManualReview(
    page,
    projectId,
    operatorId,
    current.working_copy,
  );
  expect(current.working_copy.manual_review_count).toBe(0);
  const sipBlocked = await apiRequest<ErrorPayload>(
    page,
    `/api/v1/projects/${projectId}/review/freeze-items`,
    "POST",
    { expected_version: current.working_copy.version },
    operatorId,
  );
  expect(sipBlocked.status).toBe(409);
  expect(sipBlocked.payload.error?.code).toBe("unresolved_confirmation");
  expect(sipBlocked.payload.error?.blockers).toContain("unresolved_confirmation");

  current.working_copy = await confirmSip(
    page,
    projectId,
    operatorId,
    current.working_copy,
  );
  const frozen = await apiRequest<ReviewWorkingCopy>(
    page,
    `/api/v1/projects/${projectId}/review/freeze-items`,
    "POST",
    { expected_version: current.working_copy.version },
    operatorId,
  );
  expect(frozen.status).toBe(200);
  expect(frozen.payload.items_frozen_at).not.toBeNull();
  const generated = await apiRequest<{ balloons: BalloonRecord[] }>(
    page,
    `/api/v1/projects/${projectId}/balloons/generate`,
    "POST",
    { expected_version: frozen.payload.version },
    operatorId,
  );
  expect(generated.status).toBe(200);
  const activeBalloons = generated.payload.balloons
    .filter((balloon) => balloon.status === "active")
    .sort((left, right) => (
      (left.formal_number ?? 0) - (right.formal_number ?? 0)
    ));
  expect(activeBalloons.map((balloon) => balloon.formal_number)).toEqual(
    activeBalloons.map((_, index) => index + 1),
  );

  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("button", { name: "筛选全部" }).click();
  for (const balloon of activeBalloons.slice(0, 3)) {
    await selectTableItem(page, balloon.inspection_item_id);
    await expect(page.locator(
      `[data-testid^='balloon-'][data-item-id='${balloon.inspection_item_id}']`,
    )).toHaveAttribute(
      "aria-label",
      new RegExp(`^正式气泡 ${balloon.formal_number}(?:，|$)`),
    );
    await expect(page.locator(
      `[data-testid^='candidate-number-'][data-item-id='${
        balloon.inspection_item_id
      }']`,
    )).toHaveCount(0);
  }

  const beforePlacement = await workbench(page, projectId);
  const blockedBalloons = beforePlacement.balloons.filter((balloon) => (
    balloon.status === "active"
    && (
      balloon.placement_status === "manual_required"
      || balloon.collision_flags.length > 0
    )
  ));
  expect(
    blockedBalloons.length,
    "approved PDF must retain a real placement/collision veto case",
  ).toBeGreaterThan(0);
  const expectedVetoCodes = new Set<string>();
  if (blockedBalloons.some(
    (balloon) => balloon.placement_status === "manual_required",
  )) {
    expectedVetoCodes.add("manual_required");
  }
  for (const balloon of blockedBalloons) {
    for (const flag of balloon.collision_flags) {
      expectedVetoCodes.add(
        flag === "forbidden_overlap" ? "source_text_overlap" : flag,
      );
    }
  }
  expect(expectedVetoCodes.size).toBeGreaterThan(0);
  for (const code of expectedVetoCodes) {
    expect(beforePlacement.balloon_blockers).toContain(code);
  }
  const blockedConfirm = await apiRequest<ErrorPayload>(
    page,
    `/api/v1/projects/${projectId}/review/confirm`,
    "POST",
    { expected_version: beforePlacement.working_copy.version },
    operatorId,
  );
  expect(blockedConfirm.status).toBe(409);
  for (const code of expectedVetoCodes) {
    expect(blockedConfirm.payload.error?.blockers).toContain(code);
  }
  expect(blockedConfirm.payload.error?.code).toBe(
    beforePlacement.balloon_blockers[0],
  );
  expect(await resolveBalloonBlockers(page)).toBeGreaterThan(0);

  const ready = await workbench(page, projectId);
  expect(ready.balloon_blockers).toEqual([]);
  const confirmed = await apiRequest<ReviewedResult>(
    page,
    `/api/v1/projects/${projectId}/review/confirm`,
    "POST",
    { expected_version: ready.working_copy.version },
    operatorId,
  );
  expect(confirmed.status).toBe(200);
  expect(confirmed.payload.schema_version).toBe("reviewed-result/2");
  const finalActiveItems = confirmed.payload.items.filter((item) => item.active);
  const finalAutoIds = new Set(
    finalActiveItems
      .filter((item) => item.acceptance_source === "confidence_policy")
      .map((item) => item.item_id),
  );
  const finalManualOverrideIds = new Set(
    finalActiveItems
      .filter((item) => item.acceptance_source === "manual_override")
      .map((item) => item.item_id),
  );
  expect(finalAutoIds.size).toBeGreaterThan(0);
  expect(finalManualOverrideIds.size).toBeGreaterThan(0);
  const finalBalloons = confirmed.payload.balloons
    .filter((balloon) => balloon.status === "active")
    .sort((left, right) => (
      (left.formal_number ?? 0) - (right.formal_number ?? 0)
    ));
  expect(finalBalloons.map((balloon) => balloon.formal_number)).toEqual(
    finalBalloons.map((_, index) => index + 1),
  );
  expect(finalBalloons.some(
    (balloon) => finalAutoIds.has(balloon.inspection_item_id),
  )).toBe(true);
  expect(finalBalloons.some(
    (balloon) => finalManualOverrideIds.has(balloon.inspection_item_id),
  )).toBe(true);
  const created = await apiRequest<ExportJob>(
    page,
    `/api/v1/projects/${projectId}/exports`,
    "POST",
    { reviewed_result_id: confirmed.payload.id },
  );
  expect(created.status).toBe(200);
  expect(created.payload.status).toBe("success");
  expect(created.payload.reviewed_result_id).toBe(confirmed.payload.id);
  expect(created.payload.artifacts.map((artifact) => artifact.kind).sort())
    .toEqual(["ballooned_pdf", "manifest", "sip_excel"]);
  expect(created.payload.artifacts.every(
    (artifact) => artifact.reviewed_result_id === confirmed.payload.id,
  )).toBe(true);

  const manifestResponse = await page.request.get(
    `/api/v1/exports/${created.payload.id}/downloads/manifest`,
  );
  expect(manifestResponse.ok()).toBe(true);
  const manifest = await manifestResponse.json() as Manifest;
  expect(manifest.schema_version).toBe("export-manifest/2");
  expect(manifest.export_id).toBe(created.payload.id);
  expect(manifest.project_id).toBe(projectId);
  expect(manifest.reviewed_result_id).toBe(confirmed.payload.id);
  expect(manifest.confidence_policy_versions).toEqual([
    "candidate-confidence/1",
  ]);
  expect(manifest.auto_accepted_item_count).toBe(finalAutoIds.size);
  expect(manifest.auto_accepted_item_count).toBeGreaterThan(0);
  expect(manifest.manual_override_item_count).toBe(
    finalManualOverrideIds.size,
  );
  expect(manifest.manual_override_item_count).toBeGreaterThan(0);
  expect(manifest.artifacts.every(
    (artifact) => artifact.reviewed_result_id === confirmed.payload.id,
  )).toBe(true);
});
