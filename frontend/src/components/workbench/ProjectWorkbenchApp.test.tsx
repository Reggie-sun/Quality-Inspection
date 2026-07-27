import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { ProjectWorkbenchResponse } from "../../api/types";
import { ProjectWorkbenchApp } from "./ProjectWorkbenchApp";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});


function reviewedResponse(): ProjectWorkbenchResponse {
  return {
    project: { id: "project-real", state: "reviewed", version: 1 },
    working_copy: {
      id: "working-real",
      project_id: "project-real",
      raw_result_id: "raw-real",
      version: 7,
      items: [{
        item_id: "item-secret-uuid",
        item_type: "thread",
        raw_text: "M6",
        coordinates: [10, 20, 30, 40],
        balloon_required: true,
        requires_confirmation: false,
        page_index: 0,
        status: "kept",
        active: true,
      }],
      coverage: { blocking_count: 0, review_required_count: 0 },
      numbering_stale: false,
      items_frozen_at: "2026-07-23T01:00:00Z",
      items_frozen_by: "operator-secret-uuid",
      items_frozen_version: 7,
      sip_metadata: {
        material_code: "MAT-001",
        material_name: "上座",
        drawing_number: "JS26032501",
        material: "SUS304",
        revision: "A1",
      },
    },
    pages: [{
      page_index: 0,
      width: 200,
      height: 200,
      pdf_to_render_matrix: [1, 0, 0, 1, 0, 0],
      render_to_pdf_matrix: [1, 0, 0, 1, 0, 0],
    }],
    candidates: [],
    sources: [],
    balloons: [{
      id: "balloon-secret-uuid",
      project_id: "project-real",
      inspection_item_id: "item-secret-uuid",
      source_location_id: "source-secret-uuid",
      page_index: 0,
      suggested_number: 1,
      formal_number: 1,
      sort_order: 0,
      anchor_bbox_pdf: [10, 20, 30, 40],
      leader_target_pdf: [20, 30],
      center_pdf: [50, 60],
      placement_status: "placed",
      collision_flags: [],
      status: "active",
      version: 1,
    }],
    balloon_blockers: [],
    source_pdf_url: "/api/v1/projects/project-real/source-pdf",
    reviewed_result_id: "reviewed-secret-uuid",
    latest_export: {
      id: "export-secret-uuid",
      project_id: "project-real",
      reviewed_result_id: "reviewed-secret-uuid",
      status: "success",
      error_id: null,
      artifacts: [
        { kind: "ballooned_pdf", downloadable: true },
        { kind: "sip_excel", downloadable: true },
        { kind: "manifest", downloadable: true },
      ],
    },
  } as ProjectWorkbenchResponse;
}


test("工作台加载态使用中文并标记 aria-busy", () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn()}
    />,
  );

  const loading = screen.getByText("正在加载审核工作台");
  expect(loading.closest("[aria-busy='true']")).not.toBeNull();
});


test.each([
  ["review_lock_conflict", "审核项目正由其他人员编辑，请稍后重试。"],
  ["unknown_backend_code", "操作失败，请重试。"],
])("ApiError %s 只显示安全中文，不显示后端 message", async (code, expected) => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
    error: { code, message: "RAW backend secret path /srv/private" },
  }), {
    status: 409,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn()}
    />,
  );

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(expected);
  expect(alert.textContent).not.toContain("RAW backend secret");
  expect(alert.textContent).not.toContain("/srv/private");
});


test("刷新后从只读 projection 恢复 reviewed result 和三项下载", async () => {
  const snapshot = reviewedResponse();
  const fetchMock = vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => {
    if (String(path).endsWith("/review/lock")) {
      return new Response(JSON.stringify({ operator_id: "operator-real" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(snapshot), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  fireEvent.click(await screen.findByRole("button", {
    name: "展开 SIP 与导出信息",
  }));
  await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(3));
  expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
    "下载带气泡 PDF",
    "下载 SIP Excel",
    "下载校验清单",
  ]);
  expect(fetchMock.mock.calls.some(([path, init]) => (
    String(path).endsWith("/exports") && init?.method === "POST"
  ))).toBe(false);
  expect(document.body.textContent).not.toContain("project-real");
  expect(document.body.textContent).not.toContain("operator-real");
  expect(document.body.textContent).not.toContain("item-secret-uuid");
});

test("就绪页头部横向组合纯文字品牌、真实阶段和重新处理入口", async () => {
  const snapshot = reviewedResponse();
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));
  const onReset = vi.fn();

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
      onReset={onReset}
    />,
  );

  const header = await screen.findByRole("banner", {
    name: "工程图纸检验流程",
  });
  expect(within(header).getByText("智检通")).not.toBeNull();
  expect(within(header).getByText("工程图纸智能检验")).not.toBeNull();
  expect(header.querySelector("img, svg")).toBeNull();

  const stages = within(header).getByRole("navigation", {
    name: "检验处理阶段",
  });
  for (const label of [
    "PDF文件上传",
    "识别检验项",
    "确认检验项",
    "调整气泡位置",
    "生成PDF与SIP",
  ]) {
    expect(within(stages).getByText(label)).not.toBeNull();
  }
  expect(
    within(stages).getByRole("listitem", {
      name: "文件导出，当前阶段",
    }).getAttribute("aria-current"),
  ).toBe("step");

  fireEvent.click(within(header).getByRole("button", {
    name: "处理另一份图纸",
  }));
  expect(onReset).toHaveBeenCalledOnce();
});


test("工作台加载完成后不保留过期识别状态", async () => {
  const snapshot = reviewedResponse();
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  expect(await screen.findByRole("region", { name: "项目摘要" })).not.toBeNull();
  expect(screen.queryByText("识别完成，已进入审核")).toBeNull();
});


test("无正式气泡时显示候选气泡并在检验项详情复用候选序号", async () => {
  const snapshot = reviewedResponse();
  snapshot.project.state = "editing";
  snapshot.working_copy.items_frozen_at = null;
  snapshot.working_copy.items_frozen_by = null;
  snapshot.working_copy.items_frozen_version = null;
  snapshot.candidates = [{
    id: "candidate-secret-uuid",
    item_id: "item-secret-uuid",
    page_index: 0,
    bbox_pdf: [10, 20, 30, 40],
  }];
  snapshot.balloons = [];
  snapshot.reviewed_result_id = null;
  snapshot.latest_export = null;
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  expect(await screen.findByRole("button", { name: "候选气泡 1" })).not.toBeNull();
  const detail = screen.getByRole("article", { name: "检验项 1 · 螺纹" });
  expect(within(detail).getByText("候选序号 1")).not.toBeNull();
});
