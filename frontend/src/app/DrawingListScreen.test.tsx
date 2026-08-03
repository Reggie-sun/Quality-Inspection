import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { ProjectStatus } from "../api/types";
import type { ProjectApi } from "../features/projects/api";
import { DrawingListScreen } from "./DrawingListScreen";
import type { ProjectListItem } from "../features/projects/api";


const PROJECT_A = "11111111-1111-4111-8111-111111111111";
const PROJECT_B = "22222222-2222-4222-8222-222222222222";
const ENTRY_A: ProjectListItem = {
  projectId: PROJECT_A,
  fileName: "A.pdf",
  createdAt: "2026-07-30T01:00:00.000Z",
  lastOpenedAt: "2026-07-30T03:00:00.000Z",
};
const ENTRY_B: ProjectListItem = {
  projectId: PROJECT_B,
  fileName: "B.pdf",
  createdAt: "2026-07-30T02:00:00.000Z",
  lastOpenedAt: "2026-07-30T02:00:00.000Z",
};


function status(
  phase: ProjectStatus["phase"],
  options: Partial<ProjectStatus> = {},
): ProjectStatus {
  return {
    phase,
    workbench_ready: phase === "ready_for_review",
    retryable: false,
    error: null,
    ...options,
  };
}


function fakeApi(
  getProjectStatus: ProjectApi["getProjectStatus"] = vi.fn().mockResolvedValue(
    status("ready_for_review"),
  ),
): ProjectApi {
  return {
    createProject: vi.fn(),
    getProjectStatus,
    listProjects: vi.fn().mockResolvedValue([]),
    markProjectOpened: vi.fn().mockResolvedValue(undefined),
    reprocessProject: vi.fn(),
    deleteProject: vi.fn(),
  };
}


afterEach(cleanup);


it("shows an empty drawing list with an upload action", () => {
  const onUpload = vi.fn();
  render(
    <DrawingListScreen
      entries={[]}
      api={fakeApi()}
      onUpload={onUpload}
      onOpen={vi.fn()}
      onReprocess={vi.fn()}
      onDelete={vi.fn()}
    />,
  );

  expect(screen.getByRole("heading", { name: "图纸列表" })).not.toBeNull();
  const emptyState = screen.getByText("还没有图纸任务").parentElement;
  expect(emptyState).not.toBeNull();
  fireEvent.click(
    within(emptyState as HTMLElement).getByRole(
      "button",
      { name: "上传新图纸" },
    ),
  );
  expect(onUpload).toHaveBeenCalledOnce();
});


it("shows multiple drawings and opens the selected entry", async () => {
  const onOpen = vi.fn();
  const getProjectStatus = vi.fn(async (projectId: string) =>
    projectId === PROJECT_A
      ? status("ready_for_review")
      : status("processing", { stage: "recognizing" }));
  render(
    <DrawingListScreen
      entries={[ENTRY_A, ENTRY_B]}
      api={fakeApi(getProjectStatus)}
      onUpload={vi.fn()}
      onOpen={onOpen}
      onReprocess={vi.fn()}
      onDelete={vi.fn()}
    />,
  );

  expect(screen.getByText("A.pdf")).not.toBeNull();
  expect(screen.getByText("B.pdf")).not.toBeNull();
  expect(await screen.findByText("可继续审核")).not.toBeNull();
  expect(await screen.findByText("正在识别检验项")).not.toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "继续处理 A.pdf" }));
  expect(onOpen).toHaveBeenCalledWith(ENTRY_A);
});


it("isolates a status request failure to its drawing row", async () => {
  const getProjectStatus = vi.fn(async (projectId: string) => {
    if (projectId === PROJECT_A) throw new Error("offline");
    return status("queued");
  });
  render(
    <DrawingListScreen
      entries={[ENTRY_A, ENTRY_B]}
      api={fakeApi(getProjectStatus)}
      onUpload={vi.fn()}
      onOpen={vi.fn()}
      onReprocess={vi.fn()}
      onDelete={vi.fn()}
    />,
  );

  expect(await screen.findByText("状态暂不可用")).not.toBeNull();
  expect(await screen.findByText("等待处理")).not.toBeNull();
  expect(screen.getByText("A.pdf")).not.toBeNull();
  expect(screen.getByText("B.pdf")).not.toBeNull();
});


it("aborts pending status requests when unmounted", async () => {
  const signals: AbortSignal[] = [];
  const getProjectStatus = vi.fn(
    (_projectId: string, signal?: AbortSignal) =>
      new Promise<ProjectStatus>(() => {
        if (signal !== undefined) signals.push(signal);
      }),
  );
  const { unmount } = render(
    <DrawingListScreen
      entries={[ENTRY_A, ENTRY_B]}
      api={fakeApi(getProjectStatus)}
      onUpload={vi.fn()}
      onOpen={vi.fn()}
      onReprocess={vi.fn()}
      onDelete={vi.fn()}
    />,
  );

  await waitFor(() => expect(signals).toHaveLength(2));
  unmount();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
});


it("在继续处理旁提供重新识别和删除操作", async () => {
  render(
    <DrawingListScreen
      entries={[ENTRY_A]}
      api={fakeApi()}
      onUpload={vi.fn()}
      onOpen={vi.fn()}
      onReprocess={vi.fn()}
      onDelete={vi.fn()}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "打开 A.pdf 的更多操作" }));
  const menu = screen.getByRole("menu");
  expect(within(menu).getAllByRole("menuitem").map((item) => item.textContent))
    .toEqual(["重新识别", "删除图纸"]);

  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "打开 A.pdf 的更多操作" }));
  fireEvent.mouseDown(document.body);
  expect(screen.queryByRole("menu")).toBeNull();
});


it("确认重新识别时保留当前版本说明并防止重复提交", async () => {
  let finish: (() => void) | undefined;
  const onReprocess = vi.fn(() => new Promise<void>((resolve) => {
    finish = resolve;
  }));
  render(
    <DrawingListScreen
      entries={[ENTRY_A]}
      api={fakeApi()}
      onUpload={vi.fn()}
      onOpen={vi.fn()}
      onReprocess={onReprocess}
      onDelete={vi.fn()}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "打开 A.pdf 的更多操作" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "重新识别" }));
  const dialog = screen.getByRole("dialog", { name: "重新识别 A.pdf？" });
  expect(within(dialog).getByText(
    "系统将使用当前识别能力重新处理原始 PDF。新结果成功前，当前版本仍可继续使用；成功后将切换到新版本。",
  )).not.toBeNull();

  fireEvent.click(within(dialog).getByRole("button", { name: "确认重新识别" }));
  expect(onReprocess).toHaveBeenCalledOnce();
  expect(within(dialog).getByRole("button", { name: "正在提交" })
    .hasAttribute("disabled")).toBe(true);

  finish?.();
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});


it("对话框支持安全取消并把焦点还给更多操作按钮", async () => {
  render(
    <DrawingListScreen
      entries={[ENTRY_A]}
      api={fakeApi()}
      onUpload={vi.fn()}
      onOpen={vi.fn()}
      onReprocess={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  const trigger = screen.getByRole("button", { name: "打开 A.pdf 的更多操作" });

  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("menuitem", { name: "重新识别" }));
  const reprocessDialog = screen.getByRole("dialog", { name: "重新识别 A.pdf？" });
  await waitFor(() => expect(document.activeElement).toBe(
    within(reprocessDialog).getByRole("button", { name: "取消" }),
  ));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);

  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("menuitem", { name: "删除图纸" }));
  const deleteDialog = screen.getByRole("dialog", { name: "删除 A.pdf？" });
  fireEvent.mouseDown(deleteDialog);
  expect(screen.getByRole("dialog")).toBe(deleteDialog);
  fireEvent.mouseDown(deleteDialog.parentElement as HTMLElement);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});


it("删除确认说明产品侧不可恢复并安全呈现失败", async () => {
  const onDelete = vi.fn().mockRejectedValue(new Error("private backend detail"));
  render(
    <DrawingListScreen
      entries={[ENTRY_A]}
      api={fakeApi()}
      onUpload={vi.fn()}
      onOpen={vi.fn()}
      onReprocess={vi.fn()}
      onDelete={onDelete}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "打开 A.pdf 的更多操作" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "删除图纸" }));
  const dialog = screen.getByRole("dialog", { name: "删除 A.pdf？" });
  expect(within(dialog).getByText(
    "删除后，这张图纸将从图纸列表和工作区永久移除，无法恢复。系统仅按审计和数据完整性要求保留内部记录。",
  )).not.toBeNull();

  fireEvent.click(within(dialog).getByRole("button", { name: "确认删除" }));
  expect((await within(dialog).findByRole("alert")).textContent)
    .toContain("操作失败，请稍后重试。");
  expect(document.body.textContent).not.toContain("private backend detail");
});
