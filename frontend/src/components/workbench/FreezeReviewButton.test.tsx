import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { ProjectWorkbenchResponse } from "../../api/types";
import { ProjectWorkbenchApp } from "./ProjectWorkbenchApp";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    {} as CanvasRenderingContext2D,
  );
});

function pdfFixture() {
  return {
    numPages: 1,
    getPage: vi.fn(async () => ({
      getViewport: ({ scale }: { scale: number }) => ({
        width: 200 * scale,
        height: 200 * scale,
      }),
      render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    })),
  };
}

function response(version = 3): ProjectWorkbenchResponse {
  return {
    project: { id: "project-real", state: "editing", version: 1 },
    working_copy: {
      id: "working-real",
      project_id: "project-real",
      raw_result_id: "raw-real",
      version,
      items: [
        {
          item_id: "i1",
          item_type: "thread",
          raw_text: "M6",
          coordinates: [10, 20, 30, 40],
          source_location_ids: ["s1"],
          balloon_required: true,
          requires_confirmation: false,
          active: true,
        },
      ],
      coverage: { blocking_count: 0, review_required_count: 0 },
      numbering_stale: false,
      items_frozen_at: null,
      items_frozen_by: null,
      items_frozen_version: null,
    },
    pages: [
      {
        page_index: 0,
        width: 200,
        height: 200,
        pdf_to_render_matrix: [1, 0, 0, 1, 0, 0],
        render_to_pdf_matrix: [1, 0, 0, 1, 0, 0],
      },
    ],
    candidates: [
      { id: "candidate-i1", item_id: "i1", page_index: 0, bbox_pdf: [10, 20, 30, 40] },
    ],
    sources: [{ id: "s1", item_ids: ["i1"], page_index: 0, bbox_pdf: [10, 20, 30, 40] }],
    balloons: [],
    balloon_blockers: ["missing_balloon:i1"],
    source_pdf_url: "/api/v1/projects/project-real/source-pdf",
    reviewed_result_id: null,
    latest_export: null,
  };
}

test("P0-UI-008 Save does not freeze and project identity drives real APIs", async () => {
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  let current = response();
  const fetchMock = vi.fn(async (path: RequestInfo | URL, init?: RequestInit) => {
    const value = String(path);
    calls.push({ path: value, init });
    if (value.endsWith("/review/commands")) {
      current = response(4);
      return new Response(JSON.stringify(current.working_copy), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (value.endsWith("/review/lock")) {
      return new Response(
        JSON.stringify({ project_id: "project-real", operator_id: "operator-real" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(JSON.stringify(current), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  const loadPdf = vi.fn().mockResolvedValue(pdfFixture());

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={loadPdf}
    />,
  );

  expect(await screen.findByRole("region", { name: "项目摘要" })).not.toBeNull();
  expect(loadPdf).toHaveBeenCalledWith(
    "/api/v1/projects/project-real/source-pdf",
  );
  fireEvent.click(screen.getByRole("button", { name: "保留检验项：M6" }));
  expect(screen.getByRole("button", { name: "冻结检验项" }).hasAttribute("disabled"))
    .toBe(true);

  await waitFor(() => {
    expect(screen.getByText("审核修改已提交")).not.toBeNull();
  });
  const save = calls.find((call) => call.path.endsWith("/review/commands"));
  expect(save).toBeDefined();
  expect(save?.init?.headers).toMatchObject({ "X-QI-Operator": "operator-real" });
  expect(JSON.parse(String(save?.init?.body))).toEqual({
    expected_version: 3,
    command: { type: "keep", item_id: "i1" },
  });
  expect(calls.some((call) => call.path.endsWith("/review/freeze-items"))).toBe(false);
  expect(calls.some((call) => call.path.endsWith("/review/confirm"))).toBe(false);
  expect(document.body.textContent).not.toContain("asset://");
});

test("P0-UI-008 failed API Save stays failed and preserves the pending command", async () => {
  let commandAttempts = 0;
  const fetchMock = vi.fn(async (path: RequestInfo | URL) => {
    const value = String(path);
    if (value.endsWith("/review/lock")) {
      return new Response(JSON.stringify({ operator_id: "operator-real" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (value.endsWith("/review/commands")) {
      commandAttempts += 1;
      if (commandAttempts === 1) {
        return new Response(
          JSON.stringify({
            error: { code: "stale_working_copy", message: "working copy version is stale" },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify(response().working_copy), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(response()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue(pdfFixture())}
    />,
  );

  const keep = await screen.findByRole("button", { name: "保留检验项：M6" });
  fireEvent.click(keep);

  expect(await screen.findByText("保存失败")).not.toBeNull();
  expect(screen.queryByText("已保存")).toBeNull();
  expect(screen.getByRole("alert").textContent)
    .toContain("审核内容已更新，请刷新后重试。");
  expect(screen.getByRole("alert").textContent)
    .not.toContain("working copy version is stale");
  expect(fetchMock.mock.calls.filter(([path]) => String(path).endsWith("/review/commands")))
    .toHaveLength(1);

  expect((keep as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(keep);

  expect(await screen.findByText("审核修改已提交")).not.toBeNull();
  expect(fetchMock.mock.calls.filter(([path]) => String(path).endsWith("/review/commands")))
    .toHaveLength(2);
});

test("审核锁续期失败保持 fail-closed，续期恢复后重新启用操作", async () => {
  let rejectRenewal = false;
  const fetchMock = vi.fn(async (path: RequestInfo | URL) => {
    const value = String(path);
    if (value.endsWith("/review/lock")) {
      if (rejectRenewal) {
        return new Response(JSON.stringify({
          error: { code: "review_lock_conflict", message: "lock lost" },
        }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ operator_id: "operator-real" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(response()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue(pdfFixture())}
    />,
  );

  const keep = await screen.findByRole("button", { name: "保留检验项：M6" });
  expect((keep as HTMLButtonElement).disabled).toBe(false);

  rejectRenewal = true;
  window.dispatchEvent(new Event("focus"));

  expect(await screen.findByText("审核锁续期失败，修改操作已暂停。")).not.toBeNull();
  expect((keep as HTMLButtonElement).disabled).toBe(true);

  rejectRenewal = false;
  window.dispatchEvent(new Event("focus"));

  await waitFor(() => {
    expect((keep as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText("审核锁续期失败，修改操作已暂停。")).toBeNull();
  });
});

test("P0-UI-008 Freeze, generate and Confirm remain explicit ordered actions", async () => {
  let current = response();
  const paths: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: RequestInfo | URL) => {
      const value = String(path);
      paths.push(value);
      if (value.endsWith("/review/lock")) {
        return new Response(JSON.stringify({ operator_id: "operator-real" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (value.endsWith("/review/freeze-items")) {
        current = {
          ...response(),
          working_copy: {
            ...response().working_copy,
            items_frozen_at: "2026-07-22T00:00:00Z",
            items_frozen_by: "operator-real",
            items_frozen_version: 3,
          },
        };
        return new Response(JSON.stringify(current.working_copy), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (value.endsWith("/balloons/generate")) {
        current = {
          ...current,
          balloons: [
            {
              id: "b1",
              project_id: "project-real",
              inspection_item_id: "i1",
              source_location_id: "s1",
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
            },
          ],
          balloon_blockers: [],
        };
        return new Response(JSON.stringify({ balloons: current.balloons }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (value.endsWith("/review/confirm")) {
        current = {
          ...current,
          project: { ...current.project, state: "reviewed" },
        };
        return new Response(JSON.stringify({ id: "reviewed-real" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(current), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue(pdfFixture())}
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "冻结检验项" }));
  await waitFor(() => {
    expect(screen.getByRole("button", { name: "生成气泡" }).hasAttribute("disabled"))
      .toBe(false);
  });
  expect(screen.getByRole("button", { name: "保留检验项：M6" }).hasAttribute("disabled"))
    .toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "生成气泡" }));
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: "确认审核结果" }).hasAttribute("disabled"),
    ).toBe(false);
  });
  fireEvent.click(screen.getByRole("button", { name: "确认审核结果" }));

  await screen.findByText("审核结果已确认");
  await screen.findByText("已审核");
  expect(screen.getByRole("button", { name: "重新编号" }).hasAttribute("disabled"))
    .toBe(true);
  expect(paths.filter((path) => path.includes("/review/freeze-items"))).toHaveLength(1);
  expect(paths.filter((path) => path.includes("/balloons/generate"))).toHaveLength(1);
  expect(paths.filter((path) => path.includes("/review/confirm"))).toHaveLength(1);
  expect(paths.findIndex((path) => path.includes("freeze-items"))).toBeLessThan(
    paths.findIndex((path) => path.includes("balloons/generate")),
  );
  expect(paths.findIndex((path) => path.includes("balloons/generate"))).toBeLessThan(
    paths.findIndex((path) => path.includes("review/confirm")),
  );
});
