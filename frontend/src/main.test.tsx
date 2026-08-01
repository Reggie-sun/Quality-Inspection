import type { ReactElement } from "react";
import { beforeEach, expect, test, vi } from "vitest";

const { createRootMock, renderRoot } = vi.hoisted(() => {
  const render = vi.fn();
  return {
    renderRoot: render,
    createRootMock: vi.fn(() => ({ render })),
  };
});

vi.mock("react-dom/client", () => ({
  createRoot: createRootMock,
}));

const PROJECT_ID = "550e8400-e29b-41d4-a716-446655440000";
const OPERATOR_ID = "quality-1";


beforeEach(() => {
  vi.resetModules();
  createRootMock.mockClear();
  renderRoot.mockClear();
  document.body.innerHTML = '<div id="root"></div>';
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});


test("完整旧深链仍直接渲染指定工作台", async () => {
  window.history.replaceState(
    {},
    "",
    `/?project_id=${PROJECT_ID}&operator_id=${OPERATOR_ID}`,
  );

  await import("./main");

  expect(createRootMock).toHaveBeenCalledWith(document.getElementById("root"));
  const element = renderRoot.mock.calls[0][0] as ReactElement<{
    projectId?: string;
    operatorId?: string;
    onReset?: () => void;
  }>;
  expect(element.props.projectId).toBe(PROJECT_ID);
  expect(element.props.operatorId).toBe(OPERATOR_ID);
  expect(element.props.onReset).toEqual(expect.any(Function));
});


test("无效旧深链项目会回到列表且不挂载工作台", async () => {
  window.history.replaceState(
    {},
    "",
    `/?project_id=null&operator_id=${OPERATOR_ID}`,
  );

  await import("./main");

  const element = renderRoot.mock.calls[0][0] as ReactElement<{
    projectId?: string;
  }>;
  expect(element.props.projectId).toBeUndefined();
  expect(window.location.pathname).toBe("/");
  expect(window.location.search).toBe("");
});


test("缺少深链参数时规范化为根地址并渲染列表应用", async () => {
  window.history.replaceState(
    {},
    "",
    `/review?project_id=${PROJECT_ID}`,
  );

  await import("./main");

  const element = renderRoot.mock.calls[0][0] as ReactElement<{
    projectId?: string;
  }>;
  expect(element.props.projectId).toBeUndefined();
  expect(window.location.pathname).toBe("/");
  expect(window.location.search).toBe("");
});


test("旧深链返回时不改旧浏览器目录、清除 session 并导航到列表", async () => {
  window.sessionStorage.setItem("qi.current-project-id", PROJECT_ID);
  window.localStorage.setItem("qi.drawing-list.v1", "legacy-value");
  const navigate = vi.fn();
  const { returnFromCompatibilityLink } = await import("./main");

  returnFromCompatibilityLink(PROJECT_ID, navigate);

  expect(window.localStorage.getItem("qi.drawing-list.v1")).toBe("legacy-value");
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBeNull();
  expect(navigate).toHaveBeenCalledWith("/");
});
