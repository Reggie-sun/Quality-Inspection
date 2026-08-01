import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";


afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});


function previewResponse(
  revision: number,
  stage: "local_ready" | "vlm_enriching",
) {
  return new Response(JSON.stringify({
    revision,
    stage,
    source_pdf_url: "/api/v1/projects/project-preview/source-pdf",
    semantic_snapshot: {
      schema_version: "recognition-preview/1",
      stage,
      candidates: [],
      sources: [],
      counts: {
        local_resolved: 1,
        cache_resolved: 0,
        vlm_pending: stage === "local_ready" ? 1 : 0,
        vlm_resolved: stage === "local_ready" ? 0 : 1,
        unresolved: 0,
      },
    },
    counts: {
      local_resolved: 1,
      cache_resolved: 0,
      vlm_pending: stage === "local_ready" ? 1 : 0,
      vlm_resolved: stage === "local_ready" ? 0 : 1,
      unresolved: 0,
    },
  }), { headers: { "Content-Type": "application/json" } });
}


test("recognition preview ignores an older response that resolves after a newer head", async () => {
  vi.useFakeTimers();
  const responses: Array<{ resolve: (response: Response) => void }> = [];
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => {
    responses.push({ resolve });
  })));

  const componentPath = "./RecognitionPreviewApp";
  const { RecognitionPreviewApp } = await import(componentPath);
  render(<RecognitionPreviewApp projectId="project-preview" pollIntervalMs={10} />);

  expect(responses).toHaveLength(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10);
  });
  expect(responses).toHaveLength(2);

  await act(async () => {
    responses[1].resolve(previewResponse(2, "vlm_enriching"));
  });
  expect(screen.getByText("版本 2")).not.toBeNull();
  expect(screen.getByText("正在进行视觉增强")).not.toBeNull();

  await act(async () => {
    responses[0].resolve(previewResponse(1, "local_ready"));
  });
  expect(screen.getByText("版本 2")).not.toBeNull();
  expect(screen.getByText("正在进行视觉增强")).not.toBeNull();
});


test("recognition preview renders canonical backend state with GET-only read-only controls", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(String(input)).toBe("/api/v1/projects/project-preview/recognition-preview");
    expect(init?.method).toBeUndefined();
    return new Response(JSON.stringify({
      revision: 2,
      stage: "vlm_enriching",
      source_pdf_url: "/api/v1/projects/project-preview/source-pdf",
      semantic_snapshot: {
        schema_version: "recognition-preview/1",
        stage: "vlm_enriching",
        candidates: [{ candidate_id: "candidate-1", kind: "thread", label: "M6" }],
        sources: [{ source_location_id: "source-1", source_type: "native", page_index: 0, raw_text: "螺纹 M6" }],
        counts: {
          local_resolved: 1,
          cache_resolved: 1,
          vlm_pending: 1,
          vlm_resolved: 0,
          unresolved: 0,
        },
      },
      counts: {
        local_resolved: 1,
        cache_resolved: 1,
        vlm_pending: 1,
        vlm_resolved: 0,
        unresolved: 0,
      },
    }), { headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);

  const componentPath = "./RecognitionPreviewApp";
  const { RecognitionPreviewApp } = await import(componentPath);
  render(<RecognitionPreviewApp projectId="project-preview" />);

  expect(await screen.findByRole("heading", { name: "识别预览" })).not.toBeNull();
  expect(screen.getByText("版本 2")).not.toBeNull();
  expect(screen.getByText("正在进行视觉增强")).not.toBeNull();
  expect(screen.getByText("M6")).not.toBeNull();
  expect(screen.getByText("螺纹 M6")).not.toBeNull();
  expect(screen.getByText("本地已解析：1")).not.toBeNull();
  expect(screen.getByText("缓存已解析：1")).not.toBeNull();
  expect(screen.getByText("视觉处理中：1")).not.toBeNull();
  expect(screen.queryByRole("button", { name: /保存|确认|冻结|气泡|导出/ })).toBeNull();
  expect(document.querySelector("iframe")?.getAttribute("src"))
    .toBe("/api/v1/projects/project-preview/source-pdf");
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/workbench"))).toBe(false);
});


test("recognition preview keeps the drawing and recognition results in a product layout", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => previewResponse(1, "local_ready")));

  const componentPath = "./RecognitionPreviewApp";
  const { RecognitionPreviewApp } = await import(componentPath);
  render(<RecognitionPreviewApp projectId="project-preview" />);

  const main = await screen.findByRole("main", { name: "识别预览" });
  expect(main.classList.contains("recognition-preview")).toBe(true);

  const drawing = screen.getByRole("region", { name: "工程图纸预览" });
  expect(drawing.classList.contains("recognition-preview__drawing")).toBe(true);
  expect(drawing.querySelector("iframe")).not.toBeNull();

  expect(drawing.parentElement?.classList.contains("recognition-preview__layout")).toBe(true);
  const results = screen.getByRole("complementary", { name: "当前识别结果" });
  expect(results.classList.contains("recognition-preview__results")).toBe(true);
  expect(screen.getByRole("list", { name: "已识别检验项" })).not.toBeNull();
  expect(screen.getByRole("list", { name: "识别来源" })).not.toBeNull();
});


test("recognition preview refreshes canonical state without rendering private diagnostics", async () => {
  let request = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    request += 1;
    return new Response(JSON.stringify({
      revision: request,
      stage: request === 1 ? "local_ready" : "vlm_enriching",
      source_pdf_url: "/api/v1/projects/project-preview/source-pdf",
      semantic_snapshot: {
        schema_version: "recognition-preview/1",
        stage: request === 1 ? "local_ready" : "vlm_enriching",
        candidates: [],
        sources: [],
        counts: {
          local_resolved: 1,
          cache_resolved: 0,
          vlm_pending: request === 1 ? 1 : 0,
          vlm_resolved: request === 1 ? 0 : 1,
          unresolved: 0,
        },
      },
      counts: {
        local_resolved: 1,
        cache_resolved: 0,
        vlm_pending: request === 1 ? 1 : 0,
        vlm_resolved: request === 1 ? 0 : 1,
        unresolved: 0,
      },
      provider_response: "raw provider response",
      storage_path: "/srv/private/preview.json",
    }), { headers: { "Content-Type": "application/json" } });
  }));

  const componentPath = "./RecognitionPreviewApp";
  const { RecognitionPreviewApp } = await import(componentPath);
  render(<RecognitionPreviewApp projectId="project-preview" pollIntervalMs={1} />);

  await waitFor(() => expect(screen.getByText("版本 2")).not.toBeNull());
  expect(document.body.textContent).not.toContain("raw provider response");
  expect(document.body.textContent).not.toContain("/srv/private/preview.json");
});
