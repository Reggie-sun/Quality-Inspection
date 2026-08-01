import { afterEach, expect, test, vi } from "vitest";

import { ApiError, getJson, postForm } from "../../api/client";
import {
  createProject,
  getProjectStatus,
  listProjects,
  markProjectOpened,
} from "./api";


const PROJECT_ID = "550e8400-e29b-41d4-a716-446655440000";


afterEach(() => {
  vi.unstubAllGlobals();
});


test("createProject 使用浏览器 multipart boundary 且不手工设置 Content-Type", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    project_id: PROJECT_ID,
    phase: "queued",
    workbench_ready: false,
    retryable: false,
    error: null,
  }), {
    status: 202,
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchSpy);
  const file = new File(["%PDF-1.7"], "fixture.pdf", {
    type: "application/pdf",
  });

  const result = await createProject(file);

  expect(result.phase).toBe("queued");
  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [path, request] = fetchSpy.mock.calls[0] as [string, RequestInit];
  expect(path).toBe("/api/v1/projects");
  expect(request.method).toBe("POST");
  expect(request.body).toBeInstanceOf(FormData);
  expect(request.headers).toBeUndefined();
  expect((request.body as FormData).get("file")).toBe(file);
});


test("getProjectStatus 编码项目标识并使用 GET", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    phase: "processing",
    workbench_ready: false,
    retryable: false,
    error: null,
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchSpy);

  await getProjectStatus("project/with spaces");

  expect(fetchSpy).toHaveBeenCalledWith(
    "/api/v1/projects/project%2Fwith%20spaces/status",
    { headers: { Accept: "application/json" } },
  );
});


test("listProjects 读取服务端目录并映射为 camelCase", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    items: [{
      project_id: PROJECT_ID,
      file_name: "fixture.pdf",
      created_at: "2026-08-01T01:00:00Z",
      last_opened_at: "2026-08-01T02:00:00Z",
    }],
    count: 1,
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchSpy);

  await expect(listProjects()).resolves.toEqual([{
    projectId: PROJECT_ID,
    fileName: "fixture.pdf",
    createdAt: "2026-08-01T01:00:00Z",
    lastOpenedAt: "2026-08-01T02:00:00Z",
  }]);
  expect(fetchSpy).toHaveBeenCalledWith(
    "/api/v1/projects",
    { headers: { Accept: "application/json" } },
  );
});


test("markProjectOpened 编码项目标识并使用 POST", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    project_id: PROJECT_ID,
    file_name: "fixture.pdf",
    created_at: "2026-08-01T01:00:00Z",
    last_opened_at: "2026-08-01T03:00:00Z",
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchSpy);

  await expect(markProjectOpened("project/with spaces")).resolves.toMatchObject({
    fileName: "fixture.pdf",
    lastOpenedAt: "2026-08-01T03:00:00Z",
  });
  expect(fetchSpy).toHaveBeenCalledWith(
    "/api/v1/projects/project%2Fwith%20spaces/open",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: undefined,
    },
  );
});


test("postForm 和 getJson 使用同一个脱敏错误合同", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: "invalid_pdf", message: "backend detail" },
  }), {
    status: 422,
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchSpy);

  await expect(postForm("/api/v1/projects", new FormData())).rejects.toEqual(
    new ApiError(422, "invalid_pdf", "backend detail"),
  );
  expect(typeof getJson).toBe("function");
});
