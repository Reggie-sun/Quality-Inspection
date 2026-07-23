import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ApiError } from "../../api/client";
import type { PostJson } from "../../api/types";
import { ExportPanel } from "./ExportPanel";


afterEach(cleanup);

test("P0-UI-004 gates export and exposes exactly three atomic backend downloads", async () => {
  const post = vi.fn().mockResolvedValue({
    id: "export-1",
    project_id: "project-1",
    reviewed_result_id: "reviewed-1",
    status: "success",
    artifacts: [
      { kind: "ballooned_pdf", downloadable: true },
      { kind: "sip_excel", downloadable: true },
      { kind: "manifest", downloadable: true },
    ],
  }) as unknown as PostJson;
  const { rerender } = render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      balloonBlockers={[]}
      post={post}
    />,
  );

  expect(screen.getByText("尚未审核")).not.toBeNull();
  expect(screen.getByRole("button", { name: "生成正式文件" })
    .hasAttribute("disabled")).toBe(true);
  expect(screen.queryAllByRole("link")).toHaveLength(0);

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={["manual_required"]}
      post={post}
    />,
  );
  expect(screen.getByRole("button", { name: "生成正式文件" })
    .hasAttribute("disabled")).toBe(true);

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={[]}
      post={post}
    />,
  );
  expect(screen.getByText("待生成")).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "生成正式文件" }));

  await waitFor(() => expect(post).toHaveBeenCalledWith(
    "/api/v1/projects/project-1/exports",
    { reviewed_result_id: "reviewed-1" },
    {},
  ));
  const downloads = screen.getAllByRole("link");
  expect(downloads.map((link) => link.textContent)).toEqual([
    "下载带气泡 PDF",
    "下载 SIP Excel",
    "下载校验清单",
  ]);
  expect(downloads.map((link) => link.getAttribute("href"))).toEqual([
    "/api/v1/exports/export-1/downloads/ballooned_pdf",
    "/api/v1/exports/export-1/downloads/sip_excel",
    "/api/v1/exports/export-1/downloads/manifest",
  ]);
});

test("恢复投影如实渲染导出中、失败和三产物原子下载", () => {
  const post = vi.fn() as unknown as PostJson;
  const { rerender } = render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={[]}
      post={post}
      initialExport={{
        id: "export-running",
        project_id: "project-1",
        reviewed_result_id: "reviewed-1",
        status: "running",
        artifacts: [],
      }}
    />,
  );

  expect(screen.getByText("正在生成")).not.toBeNull();
  expect(screen.queryAllByRole("link")).toHaveLength(0);

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={[]}
      post={post}
      initialExport={{
        id: "export-failed",
        project_id: "project-1",
        reviewed_result_id: "reviewed-1",
        status: "failed",
        error_id: "internal-error-id",
        artifacts: [],
      }}
    />,
  );
  expect(screen.getByText("生成失败")).not.toBeNull();
  expect(document.body.textContent).not.toContain("internal-error-id");

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={[]}
      post={post}
      initialExport={{
        id: "export-success",
        project_id: "project-1",
        reviewed_result_id: "reviewed-1",
        status: "success",
        artifacts: [
          { kind: "ballooned_pdf", downloadable: true },
          { kind: "sip_excel", downloadable: true },
          { kind: "manifest", downloadable: true },
        ],
      }}
    />,
  );
  expect(screen.getByText("可下载")).not.toBeNull();
  expect(screen.getAllByRole("link")).toHaveLength(3);
});

test.each(["pending", "running"] as const)(
  "恢复 %s 投影时禁用生成按钮且不重复提交",
  (status) => {
    const post = vi.fn().mockResolvedValue({
      id: `export-${status}`,
      project_id: "project-1",
      reviewed_result_id: "reviewed-1",
      status,
      artifacts: [],
    }) as unknown as PostJson;
    render(
      <ExportPanel
        projectId="project-1"
        reviewedResultId="reviewed-1"
        balloonBlockers={[]}
        post={post}
        initialExport={{
          id: `export-${status}`,
          project_id: "project-1",
          reviewed_result_id: "reviewed-1",
          status,
          artifacts: [],
        }}
      />,
    );

    const button = screen.getByRole("button", { name: "生成正式文件" });
    expect(button.hasAttribute("disabled")).toBe(true);
    fireEvent.click(button);
    expect(post).not.toHaveBeenCalled();
  },
);

test("未知导出状态和错误代码只显示安全中文文案", async () => {
  const post = vi.fn().mockRejectedValue(
    new ApiError(500, "future_export_error", "raw backend failure"),
  ) as unknown as PostJson;
  render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={[]}
      post={post}
      initialExport={{
        id: "export-future",
        project_id: "project-1",
        reviewed_result_id: "reviewed-1",
        status: "future_export_status" as never,
        artifacts: [],
      }}
    />,
  );

  expect(screen.getByText("待生成")).not.toBeNull();
  expect(document.body.textContent).not.toContain("future_export_status");
  fireEvent.click(screen.getByRole("button", { name: "生成正式文件" }));

  expect((await screen.findByRole("alert")).textContent)
    .toContain("操作失败，请重试。");
  expect(document.body.textContent).not.toContain("future_export_error");
  expect(document.body.textContent).not.toContain("raw backend failure");
});
