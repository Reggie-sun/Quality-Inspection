import { expect, test, type Route } from "@playwright/test";

import type { ReviewCommand, ReviewItem } from "../src/api/types";


const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const OPERATOR_ID = "gdt-e2e-operator";
const SOURCE_PDF = `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Count 1 /Kids [3 0 R] >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> >>
endobj
trailer
<< /Size 4 /Root 1 0 R >>
%%EOF`;


function gdtItem(datum: string): ReviewItem {
  return {
    item_id: "gdt-parallelism",
    item_type: "geometric_tolerance",
    schema_version: "geometric-tolerance-candidate/1",
    raw_text: "∥ 0.1 A",
    normalized_text: `∥ | 0.1 | ${datum}`,
    coordinates: [20, 20, 80, 38],
    tolerance_type: "parallelism",
    tolerance_symbol: "∥",
    tolerance_value: "0.1",
    diameter_modifier: false,
    modifiers: [],
    datum_references: [{ datum, modifiers: [] }],
    frames: [{
      segments: [{
        tolerance_value: "0.1",
        diameter_modifier: false,
        modifiers: [],
        datum_references: [{ datum, modifiers: [] }],
      }],
    }],
    standard_context: "unspecified",
    evidence_ref: "asset://gdt-e2e",
    source_location_ids: ["gdt-source"],
    source_type: "automatic",
    source_page: 1,
    page_index: 0,
    status: "pending",
    requires_confirmation: true,
    balloon_required: false,
    active: true,
  };
}


function workbenchSnapshot(item: ReviewItem, version: number) {
  return {
    project: { id: PROJECT_ID, state: "ready_for_review" },
    source_pdf_url: `/api/v1/projects/${PROJECT_ID}/source-pdf`,
    pages: [{
      page_index: 0,
      pdf_to_render_matrix: [1, 0, 0, 1, 0, 0],
      render_to_pdf_matrix: [1, 0, 0, 1, 0, 0],
    }],
    candidates: [{
      id: "candidate-gdt",
      item_id: item.item_id,
      page_index: 0,
      bbox_pdf: item.coordinates,
      confidence_band: "low",
      review_disposition: "review_required",
      status: "candidate",
    }],
    sources: [],
    balloons: [],
    working_copy: {
      id: "22222222-2222-4222-8222-222222222222",
      project_id: PROJECT_ID,
      raw_result_id: "33333333-3333-4333-8333-333333333333",
      version,
      items: [item],
      items_frozen_at: null,
      items_frozen_by: null,
      items_frozen_version: null,
      numbering_stale: false,
      coverage: {
        blocking_count: 0,
        review_required_count: 1,
        coverage_checked: true,
        entries: [],
      },
      manual_review_count: 1,
      sip_metadata: {
        material_code: "MAT-1",
        material_name: "测试件",
        drawing_number: "GDT-1",
        material: "钢",
        revision: "A",
      },
      technical_requirements: [],
    },
    sip_metadata_suggestions: [],
    balloon_blockers: [],
    latest_export: null,
  };
}


test("structured GDT display and edit survive the workbench reload", async ({
  page,
}) => {
  let currentItem = gdtItem("A");
  let version = 1;
  let receivedCommand: ReviewCommand | undefined;
  const routeJson = async (route: Route, payload: unknown) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  };

  await page.route("**/api/v1/projects/*/review/lock", (route) =>
    routeJson(route, {
      project_id: PROJECT_ID,
      operator_id: OPERATOR_ID,
      expires_at: "2026-08-01T12:00:00Z",
    }));
  await page.route("**/api/v1/projects/*/source-pdf", (route) =>
    route.fulfill({ status: 200, contentType: "application/pdf", body: SOURCE_PDF }));
  await page.route("**/api/v1/projects/*/workbench", (route) =>
    routeJson(route, workbenchSnapshot(currentItem, version)));
  await page.route("**/api/v1/projects/*/review/commands", async (route) => {
    const body = route.request().postDataJSON() as { command: ReviewCommand };
    receivedCommand = body.command;
    expect(receivedCommand.type).toBe("edit_geometric_tolerance");
    if (receivedCommand.type === "edit_geometric_tolerance") {
      expect(receivedCommand.item_id).toBe(currentItem.item_id);
      expect(receivedCommand.frames[0]?.segments[0]?.datum_references?.[0]?.datum)
        .toBe("B");
      currentItem = gdtItem("B");
      version += 1;
    }
    await routeJson(route, workbenchSnapshot(currentItem, version));
  });

  await page.goto(`/?project_id=${PROJECT_ID}&operator_id=${OPERATOR_ID}`, {
    waitUntil: "networkidle",
  });
  const editor = page.locator(".gdt-editor");
  await expect(editor).toBeVisible();
  await expect(editor).toContainText("平行度");
  await expect(editor.getByLabel("公差值")).toHaveValue("0.1");
  await expect(editor.getByLabel("基准 1")).toHaveValue("A");

  await editor.getByLabel("基准 1").fill("B");
  await editor.getByRole("button", { name: "保存几何公差" }).click();
  await expect.poll(() => receivedCommand?.type).toBe("edit_geometric_tolerance");

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator(".gdt-editor").getByLabel("基准 1")).toHaveValue("B");
  await expect(page.locator(".gdt-editor")).toContainText("平行度");
});
