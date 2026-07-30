import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ApiError } from "../api/client";
import type { ProjectStatus } from "../api/types";
import type { ProjectApi } from "../features/projects/api";
import { QualityInspectionApp } from "./QualityInspectionApp";
import { beginAnotherDrawing } from "./localContext";


vi.mock("../components/workbench/ProjectWorkbenchApp", () => ({
  ProjectWorkbenchApp: ({ onReset }: { onReset: () => void }) => (
    <>
      <h2>检验项目审核</h2>
      <button type="button" onClick={onReset}>处理另一份图纸</button>
    </>
  ),
}));

const PROJECT_ID = "550e8400-e29b-41d4-a716-446655440000";


afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
  vi.useRealTimers();
});


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
  createProject: ProjectApi["createProject"] = vi.fn().mockResolvedValue(
    status("queued", { project_id: PROJECT_ID }),
  ),
  getProjectStatus: ProjectApi["getProjectStatus"] = vi.fn().mockResolvedValue(
    status("ready_for_review"),
  ),
): ProjectApi {
  return { createProject, getProjectStatus };
}


function choosePdf(name = "drawing.pdf"): File {
  const file = new File(["%PDF-1.7"], name, { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("选择工程 PDF"), {
    target: { files: [file] },
  });
  return file;
}


test("裸根地址显示中文 PDF 上传入口且不要求内部 ID", () => {
  window.history.replaceState({}, "", "/");

  render(<QualityInspectionApp api={fakeApi()} />);

  expect(screen.getByText("智检通")).not.toBeNull();
  expect(screen.getByRole("heading", { name: "工程图纸智能检验" })).not.toBeNull();
  expect(screen.getByLabelText("选择工程 PDF")).not.toBeNull();
  expect(screen.getByRole("button", { name: "上传并开始识别" })
    .hasAttribute("disabled")).toBe(true);
  expect(screen.queryByText(/project_id|operator_id|resource_ref/i)).toBeNull();
  expect(window.location.pathname).toBe("/");
  expect(window.location.search).toBe("");
});


test("文件选择与上传状态都使用真实文件信息和不确定进度", async () => {
  let finishUpload: ((value: ProjectStatus) => void) | undefined;
  const createProject = vi.fn(() => new Promise<ProjectStatus>((resolve) => {
    finishUpload = resolve;
  }));
  render(<QualityInspectionApp api={fakeApi(createProject)} />);

  choosePdf("fixture-bracket.pdf");
  expect(screen.getByText("fixture-bracket.pdf")).not.toBeNull();
  expect(screen.getByRole("button", { name: "上传并开始识别" })
    .hasAttribute("disabled")).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));

  expect(await screen.findByText("正在上传工程 PDF")).not.toBeNull();
  expect(screen.getByRole("main").getAttribute("aria-busy")).toBe("true");
  expect(document.body.textContent).not.toMatch(/\d+%/);

  finishUpload?.(status("queued", { project_id: PROJECT_ID }));
});

test("已选文件可以直接更换或移除", () => {
  render(<QualityInspectionApp api={fakeApi()} />);
  choosePdf("待更换图纸.pdf");
  const input = screen.getByLabelText("选择工程 PDF") as HTMLInputElement;
  const openPicker = vi.fn();
  Object.defineProperty(input, "click", {
    configurable: true,
    value: openPicker,
  });

  fireEvent.click(screen.getByRole("button", { name: "重新选择文件" }));
  expect(openPicker).toHaveBeenCalledOnce();
  expect(screen.getByText("待更换图纸.pdf")).not.toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "移除已选文件" }));
  expect(screen.queryByText("待更换图纸.pdf")).toBeNull();
  expect(screen.getByRole("button", { name: "上传并开始识别" })
    .hasAttribute("disabled")).toBe(true);
});


test("上传后显示处理进度并自动进入现有工作台", async () => {
  const createProject = vi.fn().mockResolvedValue(
    status("queued", { project_id: PROJECT_ID }),
  );
  const getProjectStatus = vi.fn()
    .mockResolvedValueOnce(status("processing"))
    .mockResolvedValueOnce(status("ready_for_review"));
  render(
    <QualityInspectionApp
      api={fakeApi(createProject, getProjectStatus)}
      pollIntervalMs={1}
    />,
  );

  choosePdf();
  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));

  expect(await screen.findByText("正在识别检验项")).not.toBeNull();
  expect(await screen.findByRole("heading", { name: "检验项目审核" })).not.toBeNull();
  expect(screen.queryByText("识别完成，已进入审核")).toBeNull();
  expect(screen.getByRole("button", { name: "处理另一份图纸" })).not.toBeNull();
  expect(createProject).toHaveBeenCalledTimes(1);
  expect(getProjectStatus).toHaveBeenCalledTimes(2);
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBe(PROJECT_ID);
  expect(window.location.pathname).toBe("/");
  expect(window.location.search).toBe("");
  expect(document.body.textContent).not.toContain(PROJECT_ID);
});

test("处理另一份图纸时保留当前项目并可直接返回", async () => {
  window.sessionStorage.setItem("qi.current-project-id", PROJECT_ID);
  const getProjectStatus = vi.fn().mockResolvedValue(status("ready_for_review"));
  render(<QualityInspectionApp api={fakeApi(undefined, getProjectStatus)} />);

  expect(await screen.findByRole("heading", { name: "检验项目审核" })).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "处理另一份图纸" }));

  expect(screen.getByLabelText("选择工程 PDF")).not.toBeNull();
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBe(PROJECT_ID);

  fireEvent.click(screen.getByRole("button", { name: "返回当前图纸" }));

  expect(await screen.findByRole("heading", { name: "检验项目审核" })).not.toBeNull();
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBe(PROJECT_ID);
});

test("兼容工作台返回入口通过浏览器历史回到原图纸", () => {
  beginAnotherDrawing();
  const back = vi.spyOn(window.history, "back").mockImplementation(() => undefined);

  render(<QualityInspectionApp api={fakeApi()} />);
  fireEvent.click(screen.getByRole("button", { name: "返回当前图纸" }));

  expect(back).toHaveBeenCalledOnce();
});


test.each([
  ["parsing", "正在解析工程图纸"],
  ["recognizing", "正在识别检验项"],
  ["preparing_review", "正在准备审核"],
] as const)("显示真实后端阶段 %s", async (stage, label) => {
  window.sessionStorage.setItem("qi.current-project-id", PROJECT_ID);
  const getProjectStatus = vi.fn().mockResolvedValue(
    status("processing", { stage }),
  );
  render(
    <QualityInspectionApp
      api={fakeApi(undefined, getProjectStatus)}
      pollIntervalMs={60_000}
    />,
  );

  expect(await screen.findByText(label)).not.toBeNull();
  expect(screen.queryByText(/%/)).toBeNull();
});


test("非重试配置错误不把有效 PDF 说成无效", async () => {
  window.sessionStorage.setItem("qi.current-project-id", PROJECT_ID);
  const getProjectStatus = vi.fn().mockResolvedValue(
    status("failed", {
      retryable: false,
      error: {
        code: "vision_provider_unavailable",
        stage: "preflight",
      },
    }),
  );
  render(<QualityInspectionApp api={fakeApi(undefined, getProjectStatus)} />);

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("若文件有效，请联系管理员检查服务配置");
  expect(alert.textContent).not.toContain("有效的工程 PDF");
  expect(screen.queryByRole("button", { name: "重新处理" })).toBeNull();
});


test("已完成流程保留数字标记并以可见文字说明完成状态", async () => {
  window.sessionStorage.setItem("qi.current-project-id", PROJECT_ID);
  const getProjectStatus = vi.fn().mockResolvedValue(status("processing"));
  render(
    <QualityInspectionApp
      api={fakeApi(undefined, getProjectStatus)}
      pollIntervalMs={60_000}
    />,
  );

  const uploadStage = screen.getByText("上传图纸").closest("li");
  expect(uploadStage).not.toBeNull();
  expect(uploadStage?.textContent).toContain("1");
  expect(uploadStage?.textContent).toContain("已完成");
  expect(uploadStage?.getAttribute("aria-label")).toBe("上传图纸，已完成");
  expect(screen.queryByText("✓")).toBeNull();
});


test("后端已识别但工作台未就绪时显示正在准备审核并继续轮询", async () => {
  let resolveReady: ((value: ProjectStatus) => void) | undefined;
  const createProject = vi.fn().mockResolvedValue(
    status("queued", { project_id: PROJECT_ID }),
  );
  const getProjectStatus = vi.fn()
    .mockResolvedValueOnce(status("ready_for_review", { workbench_ready: false }))
    .mockImplementationOnce(() => new Promise<ProjectStatus>((resolve) => {
      resolveReady = resolve;
    }));
  render(
    <QualityInspectionApp
      api={fakeApi(createProject, getProjectStatus)}
      pollIntervalMs={1}
    />,
  );

  choosePdf();
  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));

  expect(await screen.findByText("正在准备审核")).not.toBeNull();
  expect(screen.queryByRole("heading", { name: "检验项目审核" })).toBeNull();
  await waitFor(() => expect(getProjectStatus).toHaveBeenCalledTimes(2));

  resolveReady?.(status("ready_for_review"));
  expect(await screen.findByRole("heading", { name: "检验项目审核" })).not.toBeNull();
});


test("不支持的 PDF 显示中文错误并只允许重新选择文件", async () => {
  const createProject = vi.fn()
    .mockResolvedValue(status("queued", { project_id: PROJECT_ID }));
  const getProjectStatus = vi.fn().mockResolvedValue(status("failed", {
    error: { code: "unsupported_input", stage: "page_inventory" },
  }));
  render(
    <QualityInspectionApp
      api={fakeApi(createProject, getProjectStatus)}
      pollIntervalMs={1}
    />,
  );

  choosePdf();
  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));

  expect((await screen.findByRole("alert")).textContent).toContain("当前 PDF 暂不支持");
  expect(screen.queryByRole("button", { name: "重新处理" })).toBeNull();
  expect(screen.getByRole("button", { name: "重新选择文件" })).not.toBeNull();
  expect(document.body.textContent).not.toContain("unsupported_input");
  expect(createProject).toHaveBeenCalledOnce();
});

test("上传校验失败不允许对同一无效 PDF 重新处理", async () => {
  const createProject = vi.fn().mockRejectedValue(
    new ApiError(422, "invalid_pdf", "private backend validation message"),
  );
  render(<QualityInspectionApp api={fakeApi(createProject)} />);

  choosePdf();
  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("PDF 格式错误，请选择有效的工程 PDF");
  expect(alert.textContent).not.toContain("private backend validation message");
  expect(screen.queryByRole("button", { name: "重新处理" })).toBeNull();
  expect(screen.getByRole("button", { name: "重新选择文件" })).not.toBeNull();
});


test("识别服务不可用时显示安全中文错误并保留重试入口", async () => {
  const createProject = vi.fn()
    .mockResolvedValue(status("queued", { project_id: PROJECT_ID }));
  const getProjectStatus = vi.fn().mockResolvedValue(status("failed", {
    error: { code: "ocr_provider_unavailable", stage: "preflight" },
    retryable: true,
  }));
  render(
    <QualityInspectionApp
      api={fakeApi(createProject, getProjectStatus)}
      pollIntervalMs={1}
    />,
  );

  choosePdf();
  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("文字识别服务暂不可用，请稍后重试");
  expect(alert.textContent).not.toContain("处理失败，请重新选择 PDF");
  expect(document.body.textContent).not.toContain("ocr_provider_unavailable");
  expect(document.body.textContent).not.toContain("OCR provider is unavailable");
  expect(screen.getByRole("button", { name: "重新处理" })
    .hasAttribute("disabled")).toBe(false);
});


test("状态请求失败保留项目并允许重新获取", async () => {
  const createProject = vi.fn()
    .mockResolvedValue(status("queued", { project_id: PROJECT_ID }));
  const getProjectStatus = vi.fn()
    .mockRejectedValueOnce(new ApiError(
      503,
      "project_status_failed",
      "private backend status message",
    ))
    .mockResolvedValueOnce(status("ready_for_review"));
  render(
    <QualityInspectionApp
      api={fakeApi(createProject, getProjectStatus)}
      pollIntervalMs={1}
    />,
  );

  choosePdf();
  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));

  expect((await screen.findByRole("alert")).textContent).toContain("状态获取失败，请重试");
  expect(document.body.textContent).not.toContain("private backend status message");
  expect(screen.getByRole("main").getAttribute("aria-busy")).toBe("false");
  expect(screen.queryByText("等待处理")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新获取状态" }));

  expect(await screen.findByRole("heading", { name: "检验项目审核" })).not.toBeNull();
  expect(createProject).toHaveBeenCalledTimes(1);
  expect(getProjectStatus).toHaveBeenCalledTimes(2);
});

test("状态请求失败后选择新 PDF 会放弃旧项目并恢复上传入口", async () => {
  const createProject = vi.fn()
    .mockResolvedValue(status("queued", { project_id: PROJECT_ID }));
  const getProjectStatus = vi.fn().mockRejectedValue(
    new ApiError(503, "project_status_failed", "private backend status message"),
  );
  render(
    <QualityInspectionApp
      api={fakeApi(createProject, getProjectStatus)}
      pollIntervalMs={1}
    />,
  );

  choosePdf("旧图纸.pdf");
  fireEvent.click(screen.getByRole("button", { name: "上传并开始识别" }));
  expect((await screen.findByRole("alert")).textContent)
    .toContain("状态获取失败，请重试");
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBe(PROJECT_ID);

  choosePdf("新图纸.pdf");

  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByText("新图纸.pdf")).not.toBeNull();
  expect(screen.getByRole("button", { name: "上传并开始识别" })
    .hasAttribute("disabled")).toBe(false);
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBeNull();
  expect(createProject).toHaveBeenCalledOnce();
});


test("卸载后停止处理状态轮询", async () => {
  vi.useFakeTimers();
  window.sessionStorage.setItem("qi.current-project-id", PROJECT_ID);
  const getProjectStatus = vi.fn().mockResolvedValue(status("processing"));
  const { unmount } = render(
    <QualityInspectionApp
      api={fakeApi(undefined, getProjectStatus)}
      pollIntervalMs={1_500}
    />,
  );

  await act(async () => {
    await Promise.resolve();
  });
  expect(getProjectStatus).toHaveBeenCalledTimes(1);

  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(4_500);
  });
  expect(getProjectStatus).toHaveBeenCalledTimes(1);
});
