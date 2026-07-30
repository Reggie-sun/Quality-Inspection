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
import type { LocalDrawingEntry } from "./localDrawingRegistry";


const PROJECT_A = "11111111-1111-4111-8111-111111111111";
const PROJECT_B = "22222222-2222-4222-8222-222222222222";
const ENTRY_A: LocalDrawingEntry = {
  projectId: PROJECT_A,
  fileName: "A.pdf",
  createdAt: "2026-07-30T01:00:00.000Z",
  lastOpenedAt: "2026-07-30T03:00:00.000Z",
};
const ENTRY_B: LocalDrawingEntry = {
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
    />,
  );

  await waitFor(() => expect(signals).toHaveLength(2));
  unmount();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
});
