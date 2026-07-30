import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
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
        candidates: [{ label: "M6" }],
        sources: [{ page_index: 0, raw_text: "M6" }],
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
  expect(screen.getByText("本地已解析：1")).not.toBeNull();
  expect(screen.getByText("缓存已解析：1")).not.toBeNull();
  expect(screen.getByText("视觉处理中：1")).not.toBeNull();
  expect(screen.queryByRole("button", { name: /保存|确认|冻结|气泡|导出/ })).toBeNull();
  expect(document.querySelector("iframe")?.getAttribute("src"))
    .toBe("/api/v1/projects/project-preview/source-pdf");
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/workbench"))).toBe(false);
});


test("recognition preview refreshes canonical state without rendering private diagnostics", async () => {
  let request = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    request += 1;
    return new Response(JSON.stringify({
      revision: request,
      stage: request === 1 ? "local_ready" : "vlm_enriching",
      source_pdf_url: "/api/v1/projects/project-preview/source-pdf",
      semantic_snapshot: { candidates: [], sources: [] },
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
