import { createHash } from "node:crypto";
import { writeFile } from "node:fs/promises";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";


type Rect = [number, number, number, number];
type Circle = [number, number, number];
type ItemNumber = { item_id: string; formal_number: number };
type Workbench = {
  working_copy: {
    items: Array<{ item_id: string; active: boolean; balloon_required?: boolean }>;
  };
  balloons: Array<{
    status: string;
    inspection_item_id: string;
    formal_number: number;
    collision_flags?: string[];
    placement_status?: string;
  }>;
};


function numbers(value: string | null): number[] {
  if (value === null) throw new Error("missing geometry evidence");
  const parsed = value.split(",").map(Number);
  if (parsed.some((item) => !Number.isFinite(item))) {
    throw new Error("non-finite geometry evidence");
  }
  return parsed;
}


function rectanglesOverlap(left: Rect, right: Rect): boolean {
  return !(
    left[2] <= right[0] || right[2] <= left[0]
    || left[3] <= right[1] || right[3] <= left[1]
  );
}


function rectangleIntersectsCircle(rectangle: Rect, circle: Circle): boolean {
  const [x, y, radius] = circle;
  const nearestX = Math.max(rectangle[0], Math.min(x, rectangle[2]));
  const nearestY = Math.max(rectangle[1], Math.min(y, rectangle[3]));
  return Math.hypot(nearestX - x, nearestY - y) < radius;
}


async function assertPageGeometry(page: Page) {
  const balloons = page.locator("[data-testid^='balloon-']");
  const count = await balloons.count();
  const geometry = await balloons.evaluateAll((elements) => elements.map((element) => {
    const parseGeometry = (attribute: string): number[] => {
      const value = element.getAttribute(attribute);
      if (value === null) throw new Error(`missing ${attribute} geometry evidence`);
      const parsed = value.split(",").map(Number);
      if (parsed.some((item) => !Number.isFinite(item))) {
        throw new Error(`non-finite ${attribute} geometry evidence`);
      }
      return parsed;
    };
    const circle = parseGeometry("data-circle") as Circle;
    const glyph = parseGeometry("data-glyph-bbox") as Rect;
    const text = element.querySelector("text");
    if (text === null) throw new Error("balloon glyph is missing");
    const box = (text as SVGGraphicsElement).getBBox();
    const style = window.getComputedStyle(text);
    const renderedGlyph = {
      box: [box.x, box.y, box.x + box.width, box.y + box.height] as Rect,
      fontFamily: style.fontFamily,
      fontWeight: style.fontWeight,
    };
    const glyphTolerance = 0.75;
    return {
      itemId: element.getAttribute("data-item-id"),
      circle,
      glyph,
      renderedGlyph,
      glyphMetricsVerified: (
        renderedGlyph.fontFamily.includes("DejaVu Sans")
        && ["400", "normal"].includes(renderedGlyph.fontWeight)
        && renderedGlyph.box[0] >= glyph[0] - glyphTolerance
        && renderedGlyph.box[1] >= glyph[1] - glyphTolerance
        && renderedGlyph.box[2] <= glyph[2] + glyphTolerance
        && renderedGlyph.box[3] <= glyph[3] + glyphTolerance
      ),
      number: text.textContent?.trim() ?? "",
      collisionFlags: element.getAttribute("data-collision-flags"),
      placementStatus: element.getAttribute("data-placement-status"),
    };
  }));
  expect(geometry).toHaveLength(count);
  const violations: string[] = [];
  const record = (violated: boolean, message: string) => {
    if (violated && violations.length < 20) violations.push(message);
  };
  for (const [index, item] of geometry.entries()) {
    const identity = item.itemId ?? `index ${index}`;
    record(!item.itemId, `${identity}: missing item identity`);
    record(!/^\d+$/.test(item.number), `${identity}: invalid formal number`);
    record(item.collisionFlags !== "", `${identity}: collision flags present`);
    record(item.placementStatus !== "placed", `${identity}: not placed`);
    record(!item.glyphMetricsVerified, `${identity}: glyph metrics mismatch`);
    const [x, y, radius] = item.circle;
    const corners = [
      [item.glyph[0], item.glyph[1]],
      [item.glyph[0], item.glyph[3]],
      [item.glyph[2], item.glyph[1]],
      [item.glyph[2], item.glyph[3]],
    ];
    record(
      !corners.every(([gx, gy]) => Math.hypot(gx - x, gy - y) < radius),
      `${identity}: glyph escapes balloon circle`,
    );
  }
  for (let left = 0; left < geometry.length; left += 1) {
    for (let right = left + 1; right < geometry.length; right += 1) {
      const a = geometry[left];
      const b = geometry[right];
      const identity = `${a.itemId ?? left}/${b.itemId ?? right}`;
      record(
        Math.hypot(a.circle[0] - b.circle[0], a.circle[1] - b.circle[1])
          < a.circle[2] + b.circle[2],
        `${identity}: balloon circles overlap`,
      );
      record(rectanglesOverlap(a.glyph, b.glyph), `${identity}: glyph boxes overlap`);
      record(
        rectanglesOverlap(a.renderedGlyph.box, b.renderedGlyph.box),
        `${identity}: rendered glyphs overlap`,
      );
      record(
        rectangleIntersectsCircle(a.glyph, b.circle),
        `${identity}: first glyph intersects second circle`,
      );
      record(
        rectangleIntersectsCircle(b.glyph, a.circle),
        `${identity}: second glyph intersects first circle`,
      );
      record(
        rectangleIntersectsCircle(a.renderedGlyph.box, b.circle),
        `${identity}: first rendered glyph intersects second circle`,
      );
      record(
        rectangleIntersectsCircle(b.renderedGlyph.box, a.circle),
        `${identity}: second rendered glyph intersects first circle`,
      );
    }
  }
  expect(violations).toEqual([]);
  await expect(page.locator("[data-testid^='leader-']")).toHaveCount(count);
  return {
    numbers: geometry.map((item) => item.number),
    itemNumbers: geometry
      .map((item) => ({
        item_id: item.itemId as string,
        formal_number: Number(item.number),
      }))
      .sort((left, right) => left.item_id.localeCompare(right.item_id)),
    glyphMetricsVerified: geometry.every((item) => item.glyphMetricsVerified),
  };
}


async function tableEvidence(page: Page) {
  const pagination = page.getByRole("navigation", { name: "检验项分页" });
  const previousPage = pagination.getByRole("button", { name: "上一页" });
  const nextPage = pagination.getByRole("button", { name: "下一页" });
  const table = page.getByRole("table", { name: "检验项列表" });
  const rowsByItemId = new Map<string, {
    itemId: string;
    active: boolean;
    formalNumber: number | null;
  }>();
  const rewindTable = async () => {
    while (!(await previousPage.isDisabled())) await previousPage.click();
  };

  await rewindTable();
  for (;;) {
    const visibleRows = table.locator("[role='row'][data-item-id]:visible");
    await expect(visibleRows.first()).toBeVisible();
    const pageRows = await visibleRows.evaluateAll((elements) => (
      elements.map((row) => {
        const itemId = row.getAttribute("data-item-id");
        const text = row.querySelector(".inspection-number")?.textContent?.trim() ?? "";
        if (!itemId) throw new Error("inspection row is missing item identity");
        return {
          itemId,
          active: row.getAttribute("data-active") === "true",
          formalNumber: /^\d+$/.test(text) ? Number(text) : null,
        };
      })
    ));
    expect(pageRows.length).toBeGreaterThan(0);
    expect(new Set(pageRows.map((row) => row.itemId)).size).toBe(pageRows.length);
    for (const row of pageRows) {
      expect(rowsByItemId.has(row.itemId)).toBe(false);
      rowsByItemId.set(row.itemId, row);
    }
    if (await nextPage.isDisabled()) break;
    await nextPage.click();
  }
  await rewindTable();
  const rows = [...rowsByItemId.values()];
  return {
    activeItemIds: rows
      .filter((row) => row.active)
      .map((row) => row.itemId)
      .sort(),
    itemNumbers: rows
      .filter((row) => row.formalNumber !== null)
      .map((row) => ({
        item_id: row.itemId,
        formal_number: row.formalNumber as number,
      }))
      .sort((left, right) => left.item_id.localeCompare(right.item_id)),
  };
}


async function rewindToFirstPage(page: Page): Promise<void> {
  const pageIndicator = page.getByTestId("page-indicator");
  const pdfControls = page.getByLabel("PDF 控件");
  for (;;) {
    const indicator = (await pageIndicator.textContent())?.trim() ?? "";
    const currentPage = Number(indicator.split("/")[0]?.trim());
    if (currentPage === 1) return;
    if (!Number.isInteger(currentPage) || currentPage < 1) {
      throw new Error("invalid page indicator");
    }
    await pdfControls.getByRole("button", { name: "上一页" }).click();
  }
}


async function collectAllPageGeometry(page: Page, totalPages: number) {
  await rewindToFirstPage(page);
  const pageIndicator = page.getByTestId("page-indicator");
  const result: string[] = [];
  const itemNumbers: ItemNumber[] = [];
  let glyphMetricsVerified = true;
  for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) {
    await expect(pageIndicator).toContainText(`${pageNumber} / ${totalPages}`);
    const pageGeometry = await assertPageGeometry(page);
    result.push(...pageGeometry.numbers);
    itemNumbers.push(...pageGeometry.itemNumbers);
    glyphMetricsVerified = glyphMetricsVerified && pageGeometry.glyphMetricsVerified;
    if (pageNumber < totalPages) {
      await page.getByLabel("PDF 控件")
        .getByRole("button", { name: "下一页" })
        .click();
    }
  }
  return {
    numbers: result.sort((left, right) => Number(left) - Number(right)),
    itemNumbers: itemNumbers.sort((left, right) => (
      left.item_id.localeCompare(right.item_id)
    )),
    glyphMetricsVerified,
  };
}


async function workbench(page: Page, projectId: string): Promise<Workbench> {
  return await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/projects/${id}/workbench`);
    if (!response.ok) throw new Error(`workbench projection failed: ${response.status}`);
    return await response.json();
  }, projectId);
}


function activeRequiredItemIds(snapshot: Workbench): string[] {
  return snapshot.working_copy.items
    .filter((item) => item.active && item.balloon_required)
    .map((item) => item.item_id)
    .sort();
}


function activeItemIds(snapshot: Workbench): string[] {
  return snapshot.working_copy.items
    .filter((item) => item.active)
    .map((item) => item.item_id)
    .sort();
}


function activeBalloons(snapshot: Workbench) {
  const required = new Set(activeRequiredItemIds(snapshot));
  return snapshot.balloons
    .filter((balloon) => (
      balloon.status === "active" && required.has(balloon.inspection_item_id)
    ))
    .sort((left, right) => left.formal_number - right.formal_number);
}


function sha256(content: Buffer): string {
  return createHash("sha256").update(content).digest("hex");
}


test("P0 current-four workbench gates formal publication behind per-sample evidence", async ({ page }) => {
  const projectUrl = process.env.QI_P0_PROJECT_URL;
  const runId = process.env.QI_P0_RUN_ID;
  const reportDirectory = process.env.QI_P0_REPORT_DIR;
  const sampleOrder = process.env.QI_P0_SAMPLE_ORDER;
  const phase = process.env.QI_P0_E2E_PHASE;
  if (!projectUrl || !runId || !reportDirectory || !sampleOrder) {
    throw new Error("run-bound current-four Playwright environment is required");
  }
  if (phase !== "pre-export" && phase !== "export") {
    throw new Error("QI_P0_E2E_PHASE must be pre-export or export");
  }
  const parsedUrl = new URL(projectUrl);
  const projectId = parsedUrl.searchParams.get("project_id");
  if (!projectId) throw new Error("run-bound project_id is required");

  const consoleErrors: string[] = [];
  const failedResponses: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });

  await page.goto(projectUrl, { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "检验项目审核" })).toBeVisible();
  const inspectionTable = page.getByRole("table", { name: "检验项列表" });
  await expect(inspectionTable).toBeVisible();
  await expect(inspectionTable.locator(".inspection-table__head"))
    .toHaveCSS("position", "sticky");
  await expect(page.getByLabel("工程图纸")).toBeVisible();

  const pageIndicator = page.getByTestId("page-indicator");
  const indicator = (await pageIndicator.textContent())?.trim() ?? "";
  const totalPages = Number(indicator.split("/")[1]?.trim());
  expect(totalPages).toBeGreaterThan(0);
  const initialGeometry = await collectAllPageGeometry(page, totalPages);
  const overlayNumbers = initialGeometry.numbers;

  const initial = await workbench(page, projectId);
  const initialBalloons = activeBalloons(initial);
  const initialNumbers = initialBalloons.map((balloon) => String(balloon.formal_number));
  const initialBackendItemNumbers = initialBalloons
    .map((balloon) => ({
      item_id: balloon.inspection_item_id,
      formal_number: balloon.formal_number,
    }))
    .sort((left, right) => left.item_id.localeCompare(right.item_id));
  expect(overlayNumbers).toEqual(initialNumbers);
  expect(initialGeometry.itemNumbers).toEqual(initialBackendItemNumbers);

  await page.getByRole("button", { name: "放大" }).click();
  await expect(page.getByLabel("缩放比例")).toHaveText("125%");
  await page.getByRole("button", { name: "向右平移" }).click();
  await page.getByRole("button", { name: "向左平移" }).click();
  await page.getByRole("button", { name: "缩小" }).click();
  await expect(page.getByLabel("缩放比例")).toHaveText("100%");

  if (phase === "pre-export") {
    await rewindToFirstPage(page);
    const firstNumber = initialNumbers[0];
    const firstItemId = initialBalloons[0]?.inspection_item_id;
    if (!firstNumber) throw new Error("formal live sample has no required balloon");
    if (!firstItemId) throw new Error("formal live sample has no required item");
    const row = page.locator(
      `[role="row"][data-item-id="${firstItemId}"]`,
    );
    await row.click();
    const firstBalloon = page.getByRole("button", {
      name: new RegExp(`^正式气泡 ${firstNumber}(?:，|$)`),
    });
    await expect(firstBalloon).toHaveAttribute("data-selected", "true");
    await firstBalloon.click();
    await expect(row).toHaveAttribute("data-selected", "true");

    const box = await firstBalloon.boundingBox();
    if (box === null) throw new Error("selected balloon has no visible geometry");
    const moveResponse = page.waitForResponse((response) => (
      response.url().includes("/balloons/commands") && response.request().method() === "POST"
    ));
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 4, box.y + box.height / 2, { steps: 2 });
    await page.mouse.up();
    expect((await moveResponse).ok()).toBe(true);

    const actionButtons = ["删除气泡", "重建气泡", "重新编号"];
    for (const name of actionButtons) {
      const responsePromise = page.waitForResponse((response) => (
        response.url().includes("/balloons/commands")
        && response.request().method() === "POST"
      ));
      await page.getByRole("button", { name }).click();
      expect((await responsePromise).ok()).toBe(true);
    }
    await expect(page.getByRole("button", { name: "确认审核结果" })).toBeEnabled();
    await page.getByRole("button", { name: "展开检验、导出与处理信息" }).click();
    await expect(page.getByRole("button", { name: "生成正式文件" })).toBeDisabled();
    await expect(page.getByRole("navigation", { name: "正式文件下载" })).toHaveCount(0);
    await page.getByRole("button", { name: "收起检验、导出与处理信息" }).click();

    const finalSnapshot = await workbench(page, projectId);
    const balloons = activeBalloons(finalSnapshot);
    const requiredBalloonItemIds = balloons
      .map((balloon) => balloon.inspection_item_id)
      .sort();
    const activeItemNumbers = balloons.map((balloon) => String(balloon.formal_number));
    const finalGeometry = await collectAllPageGeometry(page, totalPages);
    const finalOverlayNumbers = finalGeometry.numbers;
    const finalTable = await tableEvidence(page);
    const expectedTableItemNumbers = balloons
      .map((balloon) => ({
        item_id: balloon.inspection_item_id,
        formal_number: balloon.formal_number,
      }))
      .sort((left, right) => left.item_id.localeCompare(right.item_id));
    const hardCollisionCount = balloons.reduce(
      (count, balloon) => count + (balloon.collision_flags?.length ?? 0),
      0,
    );
    const unresolvedManualRequiredCount = balloons.filter(
      (balloon) => balloon.placement_status === "manual_required",
    ).length;
    expect(hardCollisionCount).toBe(0);
    expect(unresolvedManualRequiredCount).toBe(0);
    expect(finalOverlayNumbers).toEqual(activeItemNumbers);
    expect(finalGeometry.itemNumbers).toEqual(expectedTableItemNumbers);
    expect(finalTable.itemNumbers).toEqual(expectedTableItemNumbers);
    expect(finalTable.activeItemIds).toEqual(activeItemIds(finalSnapshot));
    expect(consoleErrors).toEqual([]);
    expect(failedResponses).toEqual([]);

    const screenshot = path.join(reportDirectory, `workbench-${sampleOrder}-${phase}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    await writeFile(
      path.join(reportDirectory, `e2e-${sampleOrder}-${phase}.json`),
      `${JSON.stringify({
        schema_version: "p0-browser-pre-export-evidence/1",
        run_id: runId,
        order: Number(sampleOrder),
        project_id: projectId,
        phase,
        captured_at: new Date().toISOString(),
        formal_publish_attempted: false,
        page_count: totalPages,
        active_item_ids: requiredBalloonItemIds,
        active_item_numbers: activeItemNumbers,
        overlay_numbers: finalOverlayNumbers,
        overlay_item_numbers: finalGeometry.itemNumbers,
        backend_item_numbers: expectedTableItemNumbers,
        table_item_numbers: finalTable.itemNumbers,
        table_active_item_ids: finalTable.activeItemIds,
        glyph_metrics_verified: finalGeometry.glyphMetricsVerified,
        hard_collision_count: hardCollisionCount,
        unresolved_manual_required_count: unresolvedManualRequiredCount,
        actions: { drag: true, delete: true, rebuild: true, renumber: true },
      }, null, 2)}\n`,
      "utf-8",
    );
    return;
  }

  const confirmResponse = page.waitForResponse((response) => (
    response.url().includes("/review/confirm") && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "确认审核结果" }).click();
  const reviewedResponse = await confirmResponse;
  expect(reviewedResponse.ok()).toBe(true);
  const reviewed = await reviewedResponse.json();
  await page.getByRole("button", { name: "展开检验、导出与处理信息" }).click();
  await expect(page.getByRole("button", { name: "生成正式文件" })).toBeEnabled();

  const exportResponse = page.waitForResponse((response) => (
    response.url().includes("/exports") && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "生成正式文件" }).click();
  const createdResponse = await exportResponse;
  expect(createdResponse.ok()).toBe(true);
  const created = await createdResponse.json();
  expect(created.status).toBe("success");
  expect(created.reviewed_result_id).toBe(reviewed.id);
  expect(created.artifacts).toHaveLength(3);

  const canonicalKinds = ["ballooned_pdf", "sip_excel", "manifest"];
  const downloads = page.getByRole("navigation", { name: "正式文件下载" }).getByRole("link");
  await expect(downloads).toHaveCount(3);
  const artifactByKind = new Map(
    created.artifacts.map((artifact: { kind: string }) => [artifact.kind, artifact]),
  );
  const artifacts = [];
  for (let index = 0; index < canonicalKinds.length; index += 1) {
    const kind = canonicalKinds[index];
    const href = await downloads.nth(index).getAttribute("href");
    if (!href || !href.endsWith(`/downloads/${kind}`)) {
      throw new Error(`download ${index + 1} is not canonical`);
    }
    const response = await page.request.get(new URL(href, projectUrl).toString());
    expect(response.ok()).toBe(true);
    const body = await response.body();
    const artifact = artifactByKind.get(kind) as {
      kind: string;
      sha256: string;
      size_bytes: number;
      reviewed_result_id: string;
      downloadable: boolean;
    } | undefined;
    if (!artifact) throw new Error(`missing ${kind} API artifact evidence`);
    expect(artifact.downloadable).toBe(true);
    expect(artifact.reviewed_result_id).toBe(reviewed.id);
    expect(artifact.sha256).toBe(sha256(body));
    expect(artifact.size_bytes).toBe(body.byteLength);
    artifacts.push({
      ...artifact,
      download_sha256: sha256(body),
      download_size_bytes: body.byteLength,
      content_type: response.headers()["content-type"],
    });
  }

  const finalSnapshot = await workbench(page, projectId);
  const finalBalloons = activeBalloons(finalSnapshot);
  const workbenchNumbers = finalBalloons.map((balloon) => balloon.formal_number);
  const reviewedBalloons = reviewed.balloons
    .filter((balloon: { status?: string }) => balloon.status !== "deleted")
    .sort((left: { formal_number: number }, right: { formal_number: number }) => (
      left.formal_number - right.formal_number
    ));
  const reviewedNumbers = reviewedBalloons.map(
    (balloon: { formal_number: number }) => balloon.formal_number,
  );
  const finalTable = await tableEvidence(page);
  const reviewedItemNumbers = reviewedBalloons
    .map((balloon: { inspection_item_id: string; formal_number: number }) => ({
      item_id: balloon.inspection_item_id,
      formal_number: balloon.formal_number,
    }))
    .sort((left: { item_id: string }, right: { item_id: string }) => (
      left.item_id.localeCompare(right.item_id)
    ));
  const finalBackendItemNumbers = finalBalloons
    .map((balloon) => ({
      item_id: balloon.inspection_item_id,
      formal_number: balloon.formal_number,
    }))
    .sort((left, right) => left.item_id.localeCompare(right.item_id));
  const finalGeometry = await collectAllPageGeometry(page, totalPages);
  expect(reviewedNumbers).toEqual(workbenchNumbers);
  expect(finalBackendItemNumbers).toEqual(reviewedItemNumbers);
  expect(finalGeometry.itemNumbers).toEqual(reviewedItemNumbers);
  expect(finalTable.itemNumbers).toEqual(reviewedItemNumbers);
  expect(finalTable.activeItemIds).toEqual(activeItemIds(finalSnapshot));
  expect(consoleErrors).toEqual([]);
  expect(failedResponses).toEqual([]);

  const screenshot = path.join(reportDirectory, `workbench-${sampleOrder}-${phase}.png`);
  await page.screenshot({ path: screenshot, fullPage: true });
  await writeFile(
    path.join(reportDirectory, `e2e-${sampleOrder}-${phase}.json`),
    `${JSON.stringify({
      schema_version: "p0-browser-export-evidence/1",
      run_id: runId,
      order: Number(sampleOrder),
      project_id: projectId,
      phase,
      captured_at: new Date().toISOString(),
      formal_publish_attempted: true,
      reviewed_result_id: reviewed.id,
      export_id: created.id,
      status: created.status,
      reviewed_item_ids: reviewed.items
        .filter((item: { active?: boolean; balloon_required?: boolean }) => (
          item.active !== false && item.balloon_required
        ))
        .map((item: { item_id: string }) => item.item_id)
        .sort(),
      reviewed_numbers: reviewedNumbers,
      workbench_numbers: workbenchNumbers,
      overlay_item_numbers: finalGeometry.itemNumbers,
      backend_item_numbers: finalBackendItemNumbers,
      table_item_numbers: finalTable.itemNumbers,
      table_active_item_ids: finalTable.activeItemIds,
      glyph_metrics_verified: finalGeometry.glyphMetricsVerified,
      artifacts,
      download_kinds: canonicalKinds,
    }, null, 2)}\n`,
    "utf-8",
  );
});
