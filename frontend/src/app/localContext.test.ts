import { beforeEach, expect, test } from "vitest";

import {
  beginAnotherDrawing,
  canReturnToPreviousWorkbench,
  clearCurrentProjectId,
  getCurrentProjectId,
  getOrCreateLocalOperatorId,
  setCurrentProjectId,
} from "./localContext";


const PROJECT_ID = "550e8400-e29b-41d4-a716-446655440000";


beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});


test("本地操作身份稳定保存在 localStorage 且不进入 URL", () => {
  const first = getOrCreateLocalOperatorId();
  const second = getOrCreateLocalOperatorId();

  expect(first).toBe(second);
  expect(first).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
  expect(window.localStorage.getItem("qi.local-operator-id")).toBe(first);
  expect(window.location.href).not.toContain(first);
  expect(document.body.textContent).not.toContain(first);
});


test("无效的既有操作身份会被替换", () => {
  window.localStorage.setItem("qi.local-operator-id", "not-a-uuid");

  const generated = getOrCreateLocalOperatorId();

  expect(generated).not.toBe("not-a-uuid");
  expect(window.localStorage.getItem("qi.local-operator-id")).toBe(generated);
});


test("当前项目只保存在 sessionStorage 且可清除", () => {
  setCurrentProjectId(PROJECT_ID);

  expect(getCurrentProjectId()).toBe(PROJECT_ID);
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBe(PROJECT_ID);
  expect(window.location.href).not.toContain(PROJECT_ID);
  expect(document.body.textContent).not.toContain(PROJECT_ID);

  clearCurrentProjectId();
  expect(getCurrentProjectId()).toBeUndefined();
});


test("无效的 session 项目不会被复用", () => {
  window.sessionStorage.setItem("qi.current-project-id", "private-project-ref");

  expect(getCurrentProjectId()).toBeUndefined();
  expect(window.sessionStorage.getItem("qi.current-project-id")).toBeNull();
});


test("兼容链接进入新图纸入口时只在 session 中保留无标识的返回标记", () => {
  window.history.replaceState({}, "", "/?project_id=current");
  setCurrentProjectId(PROJECT_ID);

  beginAnotherDrawing();

  expect(canReturnToPreviousWorkbench()).toBe(true);
  expect(getCurrentProjectId()).toBeUndefined();
  expect(window.sessionStorage.getItem("qi.can-return-to-workbench")).toBe("true");
  expect(window.sessionStorage.length).toBe(1);
});
