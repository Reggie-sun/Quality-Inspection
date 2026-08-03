import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ApiError } from "../../api/client";
import type {
  ExportArtifactKind,
  ExportJob,
  PostJson,
} from "../../api/types";
import { ExportPanel } from "./ExportPanel";


afterEach(cleanup);

function exportArtifact(kind: ExportArtifactKind) {
  return {
    kind,
    sha256: `${kind}-sha256`,
    size_bytes: 1,
    reviewed_result_id: "reviewed-1",
    downloadable: true,
  };
}

function exportJob(
  status: ExportJob["status"],
  artifacts: ExportJob["artifacts"] = [],
): ExportJob {
  return {
    id: `export-${status}`,
    project_id: "project-1",
    reviewed_result_id: "reviewed-1",
    status,
    error_id: status === "failed" ? "internal-error-id" : null,
    template_version: "template/1",
    mapping_version: "mapping/1",
    renderer_version: "renderer/1",
    artifacts,
  };
}

test("P0-UI-004 gates export and exposes exactly three atomic backend downloads", async () => {
  const post = vi.fn().mockResolvedValue({
    ...exportJob("success", [
      exportArtifact("ballooned_pdf"),
      exportArtifact("sip_excel"),
      exportArtifact("manifest"),
    ]),
    id: "export-1",
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
  const status = screen.getByRole("status");
  expect(status.getAttribute("aria-live")).toBe("polite");
  expect(status.getAttribute("aria-atomic")).toBe("true");
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

test("首次导出先在后台确认审核结果，再提交同一 reviewed result 导出", async () => {
  const postMock = vi.fn().mockResolvedValue(exportJob("running"));
  const post = postMock as unknown as PostJson;
  const confirmReview = vi.fn().mockResolvedValue("reviewed-1");
  render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      canFinalize
      balloonBlockers={[]}
      post={post}
      onConfirmReview={confirmReview}
    />,
  );

  const action = screen.getByRole("button", { name: "生成正式文件" });
  expect(action.hasAttribute("disabled")).toBe(false);
  fireEvent.click(action);

  await waitFor(() => expect(confirmReview).toHaveBeenCalledOnce());
  expect(post).toHaveBeenCalledWith(
    "/api/v1/projects/project-1/exports",
    { reviewed_result_id: "reviewed-1" },
    {},
  );
  expect(confirmReview.mock.invocationCallOrder[0]).toBeLessThan(
    postMock.mock.invocationCallOrder[0],
  );
});

test("未完成审核时优先显示精确的 SIP 异常阻断", () => {
  const post = vi.fn() as unknown as PostJson;
  const { rerender } = render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      canFinalize={false}
      balloonBlockers={[]}
      sipExceptionCount={112}
      projectMetadataConfirmed
      post={post}
    />,
  );

  expect(screen.getByRole("status").textContent)
    .toBe("SIP 异常 112 项");

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      canFinalize={false}
      balloonBlockers={[]}
      sipExceptionCount={0}
      projectMetadataConfirmed={false}
      missingProjectMetadataFields={["物料编码"]}
      post={post}
    />,
  );
  expect(screen.getByRole("status").textContent).toBe("待补充项目 SIP：物料编码");
});

test("检验项已冻结但气泡仍有阻断时显示真实气泡原因而不是尚未审核", () => {
  const post = vi.fn() as unknown as PostJson;
  render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      canFinalize={false}
      balloonBlockers={[
        "missing_required_balloon",
        "manual_required",
      ]}
      projectMetadataConfirmed
      post={post}
    />,
  );

  expect(screen.getByRole("status").textContent).toBe("存在气泡阻断项");
  expect(screen.getByRole("button", { name: "生成正式文件" })
    .hasAttribute("disabled")).toBe(true);
});

test("项目 SIP 识别冲突时正式文件门禁显示精确原因", () => {
  const post = vi.fn() as unknown as PostJson;
  render(
    <ExportPanel
      projectId="project"
      canFinalize={false}
      reviewedResultId={undefined}
      balloonBlockers={[]}
      projectMetadataConfirmed={false}
      projectMetadataBlocker="conflict"
      post={post}
    />,
  );

  expect(screen.getByRole("status").textContent).toBe(
    "项目 SIP 信息存在识别冲突",
  );
});

test("待生成的 SIP 行与真实异常分开显示", () => {
  const post = vi.fn() as unknown as PostJson;
  const { rerender } = render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      canFinalize={false}
      balloonBlockers={[]}
      sipPendingCount={112}
      sipExceptionCount={0}
      projectMetadataConfirmed
      post={post}
    />,
  );

  expect(screen.getByRole("status").textContent)
    .toBe("SIP 待生成 112 项");

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      canFinalize={false}
      balloonBlockers={[]}
      sipPendingCount={112}
      sipExceptionCount={2}
      projectMetadataConfirmed
      post={post}
    />,
  );
  expect(screen.getByRole("status").textContent)
    .toBe("SIP 异常 2 项");
});

test("正式文件门禁显示真实待审核与待确认气泡需求数量", () => {
  const post = vi.fn() as unknown as PostJson;
  render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      canFinalize={false}
      pendingReviewCount={13}
      pendingBalloonDecisionCount={4}
      balloonBlockers={[]}
      projectMetadataConfirmed
      post={post}
    />,
  );

  expect(screen.getByRole("status").textContent).toBe(
    "待审核检验项 13 项 · 待确认是否需要气泡 4 项",
  );
  expect(screen.getByRole("button", { name: "生成正式文件" })
    .hasAttribute("disabled")).toBe(true);
});

test("恢复投影如实渲染导出中、失败和三产物原子下载", () => {
  const post = vi.fn() as unknown as PostJson;
  const { rerender } = render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={[]}
      post={post}
      initialExport={exportJob("running")}
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
      initialExport={exportJob("failed")}
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
      initialExport={exportJob("success", [
        exportArtifact("ballooned_pdf"),
        exportArtifact("sip_excel"),
        exportArtifact("manifest"),
      ])}
    />,
  );
  expect(screen.getByText("可下载")).not.toBeNull();
  expect(screen.getAllByRole("link")).toHaveLength(3);
});

test("恢复 running 投影时禁用生成按钮且不重复提交", () => {
    const post = (
      vi.fn().mockResolvedValue(exportJob("running"))
    ) as unknown as PostJson;
    render(
      <ExportPanel
        projectId="project-1"
        reviewedResultId="reviewed-1"
        balloonBlockers={[]}
        post={post}
        initialExport={{
          ...exportJob("running"),
          id: "export-running",
        }}
      />,
    );

    const button = screen.getByRole("button", { name: "生成正式文件" });
    expect(button.hasAttribute("disabled")).toBe(true);
    fireEvent.click(button);
    expect(post).not.toHaveBeenCalled();
});

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
        ...exportJob("failed"),
        id: "export-future",
        status: "future_export_status" as never,
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
