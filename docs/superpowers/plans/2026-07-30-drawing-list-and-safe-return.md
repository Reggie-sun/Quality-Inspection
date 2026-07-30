# Drawing List And Safe Return Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把根地址升级为可恢复多个本机图纸任务的首页，并让工作台在返回列表前显式处理全部未保存草稿。

**Architecture:** 后端项目、working copy 和状态接口保持不变；新增纯前端 `localDrawingRegistry` 作为浏览器目录的唯一 Owner，`QualityInspectionApp` 继续拥有上传、轮询和顶层 screen 路由。工作台通过三个显式 `DraftSaveHandle` 和 metadata 保存函数按顺序复用既有 `submitCommand()`，任何一步失败都停止返回。

**Tech Stack:** React 19、TypeScript 5.8、Vitest、Testing Library、Vite、现有 REST client。

## Global Constraints

- 固定使用 `localStorage` key `qi.drawing-list.v1`，不新增数据库字段、migration 或项目列表 API。
- `projectId` 必须是 UUID；文件名必须非空；时间必须是合法 ISO 字符串。
- 本机目录损坏或写入失败不能阻断已成功创建的后端项目。
- 工作台按钮统一为“回到图纸列表”。
- 保存不得通过 DOM click、隐藏按钮、synthetic event 或新建批量后端 API 实现。
- 每条保存命令必须继续经过现有 `submitCommand()`，并在前一条刷新后读取最新 working-copy version。
- 任一保存失败立即停止并留在工作台；不保存返回不得发保存请求。
- 保留旧 session 当前项目和 `project_id` / `operator_id` 深链兼容。
- 不实现删除、归档、重命名、搜索、分页或跨设备同步。
- 只 stage 和 commit 本计划列出的文件，不触碰现有无关 dirty files。

---

### Task 1: Local Drawing Registry

**Files:**
- Create: `frontend/src/app/localDrawingRegistry.ts`
- Create: `frontend/src/app/localDrawingRegistry.test.ts`

**Interfaces:**
- Consumes: 浏览器 `Storage`、UUID project ID、上传文件名和可注入的 `Date`。
- Produces:

```ts
export type LocalDrawingEntry = {
  projectId: string;
  fileName: string;
  createdAt: string;
  lastOpenedAt: string;
};

export const LOCAL_DRAWING_REGISTRY_KEY = "qi.drawing-list.v1";

export function readLocalDrawings(
  storage?: Storage,
): LocalDrawingEntry[];

export function registerLocalDrawing(
  projectId: string,
  fileName: string,
  now?: Date,
  storage?: Storage,
): boolean;

export function touchLocalDrawing(
  projectId: string,
  fallbackFileName?: string,
  now?: Date,
  storage?: Storage,
): boolean;
```

- `registerLocalDrawing()` 和 `touchLocalDrawing()` 返回是否成功写入；失败只返回 `false`，不把 storage exception 抛给应用。

- [ ] **Step 1: Write the failing registry tests**

覆盖以下具名行为：

```ts
it("keeps multiple drawings and sorts by last opened time", () => {
  registerLocalDrawing(PROJECT_A, "A.pdf", new Date("2026-07-30T01:00:00Z"), storage);
  registerLocalDrawing(PROJECT_B, "B.pdf", new Date("2026-07-30T02:00:00Z"), storage);
  expect(readLocalDrawings(storage).map((entry) => entry.projectId))
    .toEqual([PROJECT_B, PROJECT_A]);
});

it("updates an existing drawing without replacing other entries", () => {
  registerLocalDrawing(PROJECT_A, "A.pdf", FIRST, storage);
  registerLocalDrawing(PROJECT_B, "B.pdf", SECOND, storage);
  touchLocalDrawing(PROJECT_A, undefined, THIRD, storage);
  expect(readLocalDrawings(storage)).toMatchObject([
    { projectId: PROJECT_A, fileName: "A.pdf" },
    { projectId: PROJECT_B, fileName: "B.pdf" },
  ]);
});

it("filters malformed entries and tolerates malformed JSON", () => {
  storage.setItem(LOCAL_DRAWING_REGISTRY_KEY, JSON.stringify([
    VALID_ENTRY,
    { ...VALID_ENTRY, projectId: "not-a-uuid" },
    { ...VALID_ENTRY, fileName: " " },
  ]));
  expect(readLocalDrawings(storage)).toEqual([VALID_ENTRY]);
  storage.setItem(LOCAL_DRAWING_REGISTRY_KEY, "{");
  expect(readLocalDrawings(storage)).toEqual([]);
});

it("returns false when storage cannot be written", () => {
  const blocked = { getItem: () => null, setItem: () => { throw new Error("quota"); } };
  expect(registerLocalDrawing(PROJECT_A, "A.pdf", FIRST, blocked as Storage))
    .toBe(false);
});
```

- [ ] **Step 2: Run the registry test to verify RED**

Run:

```bash
cd frontend
npm test -- src/app/localDrawingRegistry.test.ts
```

Expected: FAIL because `localDrawingRegistry.ts` does not exist.

- [ ] **Step 3: Implement validated registry read/write**

实现要点：

```ts
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function validEntry(value: unknown): value is LocalDrawingEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.projectId === "string"
    && UUID_PATTERN.test(entry.projectId)
    && typeof entry.fileName === "string"
    && entry.fileName.trim() !== ""
    && typeof entry.createdAt === "string"
    && !Number.isNaN(Date.parse(entry.createdAt))
    && typeof entry.lastOpenedAt === "string"
    && !Number.isNaN(Date.parse(entry.lastOpenedAt));
}
```

读取时捕获 `getItem()`、`JSON.parse()` 异常；过滤非法项、按 `projectId` 去重并按 `lastOpenedAt` 倒序。写入时保留其他项目，使用 `JSON.stringify()` 一次覆盖 registry key，并捕获 `setItem()` 异常。

- [ ] **Step 4: Run the registry tests to verify GREEN**

Run:

```bash
cd frontend
npm test -- src/app/localDrawingRegistry.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the registry**

```bash
git add frontend/src/app/localDrawingRegistry.ts frontend/src/app/localDrawingRegistry.test.ts
git commit -m "feat: add local drawing registry"
```

---

### Task 2: Drawing List Homepage

**Files:**
- Create: `frontend/src/app/DrawingListScreen.tsx`
- Create: `frontend/src/app/DrawingListScreen.test.tsx`
- Modify: `frontend/src/app/QualityInspectionApp.tsx`
- Modify: `frontend/src/app/QualityInspectionApp.test.tsx`
- Modify: `frontend/src/app/localContext.ts`
- Modify: `frontend/src/app/localContext.test.ts`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/app.css`

**Interfaces:**
- Consumes: `LocalDrawingEntry[]`, existing `ProjectApi.getProjectStatus()`, callbacks to upload and open a project.
- Produces:

```ts
type DrawingListScreenProps = {
  entries: LocalDrawingEntry[];
  api: ProjectApi;
  onUpload: () => void;
  onOpen: (entry: LocalDrawingEntry) => void;
};
```

- `QualityInspectionApp` adds `{ kind: "list" }` to `ProductScreen`.
- `clearCurrentProjectId()` remains the single session cleanup function; obsolete `beginAnotherDrawing()` and `canReturnToPreviousWorkbench()` are removed with their tests.

- [ ] **Step 1: Write failing homepage component tests**

测试必须证明：

```tsx
render(
  <DrawingListScreen
    entries={[ENTRY_A, ENTRY_B]}
    api={fakeApi({ [PROJECT_A]: READY, [PROJECT_B]: PROCESSING })}
    onUpload={onUpload}
    onOpen={onOpen}
  />,
);
expect(screen.getByRole("heading", { name: "图纸列表" })).toBeVisible();
expect(screen.getByText("A.pdf")).toBeVisible();
expect(screen.getByText("B.pdf")).toBeVisible();
await user.click(screen.getByRole("button", { name: "继续处理 A.pdf" }));
expect(onOpen).toHaveBeenCalledWith(ENTRY_A);
```

另加：
- 空目录显示“还没有图纸任务”和“上传新图纸”。
- 一个状态请求 reject 时该行显示“状态暂不可用”，另一行仍正常显示。
- processing 行显示现有阶段文案，ready 行显示“可继续审核”。

- [ ] **Step 2: Run homepage tests to verify RED**

Run:

```bash
cd frontend
npm test -- src/app/DrawingListScreen.test.tsx
```

Expected: FAIL because the screen component does not exist.

- [ ] **Step 3: Implement the semantic list**

使用 `<main>`、`<table>`、行内可读状态和包含文件名的按钮。每一行独立请求状态并独立捕获错误；组件卸载时 abort 所有请求。不要让列表状态决定正式业务状态，只把点击交给 `onOpen(entry)`。

- [ ] **Step 4: Run homepage component tests to verify GREEN**

Run:

```bash
cd frontend
npm test -- src/app/DrawingListScreen.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Write failing app-routing tests**

在 `QualityInspectionApp.test.tsx` 替换旧“处理另一份图纸 / 返回当前图纸”断言，增加：

```ts
it("shows the drawing list by default and opens upload on demand", async () => {
  render(<QualityInspectionApp api={fakeApi()} />);
  expect(screen.getByRole("heading", { name: "图纸列表" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "上传新图纸" }));
  expect(screen.getByText("拖入 PDF 图纸")).toBeVisible();
});

it("registers a newly created drawing without replacing existing drawings", async () => {
  seedRegistry([ENTRY_A]);
  render(<QualityInspectionApp api={fakeApiCreating(PROJECT_B)} pollIntervalMs={1} />);
  await openUploadAndSubmit("B.pdf");
  expect(readLocalDrawings()).toEqual(expect.arrayContaining([
    expect.objectContaining({ projectId: PROJECT_A }),
    expect.objectContaining({ projectId: PROJECT_B, fileName: "B.pdf" }),
  ]));
});

it("opens a listed drawing and updates current project context", async () => {
  seedRegistry([ENTRY_A]);
  render(<QualityInspectionApp api={fakeApiReady(PROJECT_A)} pollIntervalMs={1} />);
  await user.click(screen.getByRole("button", { name: "继续处理 A.pdf" }));
  expect(sessionStorage.getItem("qi.current-project-id")).toBe(PROJECT_A);
  expect(await screen.findByTestId("project-workbench")).toBeVisible();
});
```

保留旧 session 项目直接恢复 processing/workbench 的兼容测试。

- [ ] **Step 6: Run app-routing tests to verify RED**

Run:

```bash
cd frontend
npm test -- src/app/QualityInspectionApp.test.tsx src/app/localContext.test.ts
```

Expected: FAIL on the new list-first behavior and obsolete return helpers.

- [ ] **Step 7: Implement list-first screen routing**

修改 `QualityInspectionApp`：

- 无 session 项目时 `initialScreen()` 返回 `{ kind: "list" }`。
- `list` 渲染 `DrawingListScreen`。
- “上传新图纸”切换到 `{ kind: "idle" }`；上传取消回到 list。
- create 成功后立即 `registerLocalDrawing(result.project_id, file.name)`，失败只设置非阻断 warning。
- 打开条目时调用 `setCurrentProjectId()`、`touchLocalDrawing()` 并进入 processing。
- 工作台允许返回后调用 `clearCurrentProjectId()` 并进入 list。
- 旧 session 项目若不在 registry，使用 `未命名图纸.pdf` 登记后继续恢复。

删除临时 `returnProjectId`、`historyReturnAvailable` 和旧返回分支。把新增文案集中加入 `zhCN.ts`，把首页样式加入 `app.css`，不改 `workbench.css` 的现有无关样式。

- [ ] **Step 8: Run app-routing tests to verify GREEN**

Run:

```bash
cd frontend
npm test -- src/app/DrawingListScreen.test.tsx src/app/QualityInspectionApp.test.tsx src/app/localContext.test.ts
```

Expected: PASS.

- [ ] **Step 9: Commit the homepage**

```bash
git add frontend/src/app/DrawingListScreen.tsx frontend/src/app/DrawingListScreen.test.tsx frontend/src/app/QualityInspectionApp.tsx frontend/src/app/QualityInspectionApp.test.tsx frontend/src/app/localContext.ts frontend/src/app/localContext.test.ts frontend/src/copy/zhCN.ts frontend/src/styles/app.css
git commit -m "feat: add drawing list homepage"
```

---

### Task 3: Explicit Draft Save Contracts

**Files:**
- Create: `frontend/src/components/workbench/draftSave.ts`
- Create: `frontend/src/components/workbench/draftSave.test.ts`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/workbench/SelectedSipDetailFields.tsx`
- Modify: `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
- Modify: `frontend/src/components/workbench/SipInformationPanel.tsx`
- Modify: `frontend/src/components/workbench/SipInformationPanel.test.tsx`

**Interfaces:**
- Produces:

```ts
export type DraftSaveHandle = {
  saveDrafts: () => Promise<boolean>;
};

export async function saveDraftHandlesInOrder(
  handles: ReadonlyArray<DraftSaveHandle | null>,
): Promise<boolean>;
```

- `ReviewPanel`, `InspectionItemTable` and `SelectedSipDetailFields` accept `draftSaveRef?: Ref<DraftSaveHandle>`.
- `SipInformationPanel` accepts `selectedSipDraftSaveRef?: Ref<DraftSaveHandle>` and forwards it.
- `saveDrafts()` returns `false` on validation failure or command failure and stops its own remaining commands.

- [ ] **Step 1: Write the failing orchestration test**

```ts
it("stops at the first failed saver", async () => {
  const calls: string[] = [];
  const result = await saveDraftHandlesInOrder([
    { saveDrafts: async () => { calls.push("review"); return true; } },
    { saveDrafts: async () => { calls.push("source"); return false; } },
    { saveDrafts: async () => { calls.push("sip"); return true; } },
  ]);
  expect(result).toBe(false);
  expect(calls).toEqual(["review", "source"]);
});
```

- [ ] **Step 2: Run the orchestration test to verify RED**

Run:

```bash
cd frontend
npm test -- src/components/workbench/draftSave.test.ts
```

Expected: FAIL because `draftSave.ts` does not exist.

- [ ] **Step 3: Implement the minimal sequential helper**

遍历非空 handle，逐个 `await handle.saveDrafts()`；返回 `false` 时立即停止，全部成功返回 `true`。

- [ ] **Step 4: Write failing editor-handle tests**

分别证明：

- `ReviewPanel` 保存 dirty item edit、dirty split 和 manual item，按当前稳定次序执行，首个失败后停止，成功项才清 dirty。
- `InspectionItemTable` 把每个 dirty source 通过现有 `promote_source` command 保存，非法 draft 返回 `false`。
- `SelectedSipDetailFields` 把每个 dirty SIP draft 通过 `set_sip_detail_fields` 保存，非法 draft 返回 `false`。
- `SipInformationPanel` 原样转发 handle ref。

测试通过 `createRef<DraftSaveHandle>()` 调用：

```tsx
const draftSaveRef = createRef<DraftSaveHandle>();
render(<ReviewPanel {...props} draftSaveRef={draftSaveRef} />);
await act(async () => {
  expect(await draftSaveRef.current?.saveDrafts()).toBe(true);
});
```

- [ ] **Step 5: Run editor tests to verify RED**

Run:

```bash
cd frontend
npm test -- src/components/review/ReviewPanel.test.tsx src/components/workbench/InspectionItemTable.test.tsx src/components/workbench/SelectedSipDetailFields.test.tsx src/components/workbench/SipInformationPanel.test.tsx
```

Expected: FAIL because the draft-save props and handles are absent.

- [ ] **Step 6: Expose existing command builders through handles**

在三个 editor 内用 `useImperativeHandle()` 暴露 `saveDrafts()`，复用现有 `editItem()`、`splitItem()`、`addManualItem()`、source promote 和 SIP save command 构建逻辑。循环开始时复制 dirty ID 数组，避免 React state 更新改变当前批次；每个 command 都等待 `onCommand()` 完成后再继续。

不要：

- 查询按钮或调用 `.click()`。
- 新建第二套 HTTP client。
- 在子组件里导航。
- 把 ignore/exclude 当作保存草稿。

- [ ] **Step 7: Run editor tests to verify GREEN**

Run:

```bash
cd frontend
npm test -- src/components/workbench/draftSave.test.ts src/components/review/ReviewPanel.test.tsx src/components/workbench/InspectionItemTable.test.tsx src/components/workbench/SelectedSipDetailFields.test.tsx src/components/workbench/SipInformationPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit the draft-save contracts**

```bash
git add frontend/src/components/workbench/draftSave.ts frontend/src/components/workbench/draftSave.test.ts frontend/src/components/review/ReviewPanel.tsx frontend/src/components/review/ReviewPanel.test.tsx frontend/src/components/workbench/InspectionItemTable.tsx frontend/src/components/workbench/InspectionItemTable.test.tsx frontend/src/components/workbench/SelectedSipDetailFields.tsx frontend/src/components/workbench/SelectedSipDetailFields.test.tsx frontend/src/components/workbench/SipInformationPanel.tsx frontend/src/components/workbench/SipInformationPanel.test.tsx
git commit -m "feat: expose workbench draft saves"
```

---

### Task 4: Safe Return Dialog And Latest-Version Saves

**Files:**
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

**Interfaces:**
- `InspectionWorkbench.onReset` remains `() => void`, but is called only after direct return, discard confirmation, or successful save-all.
- `InspectionWorkbench` owns refs for review/source/SIP handles and invokes `confirmMetadata()` first when metadata is dirty.
- `ProjectWorkbenchApp` owns `snapshotRef: MutableRefObject<ProjectWorkbenchView | undefined>`; `refresh()` updates it before `setSnapshot()`, and `save()` reads `snapshotRef.current.working_copy.version`.

- [ ] **Step 1: Write failing safe-return tests**

在 `InspectionWorkbench.test.tsx` 覆盖：

```ts
it("returns immediately when there are no local drafts", async () => {
  await user.click(screen.getByRole("button", { name: "回到图纸列表" }));
  expect(onReset).toHaveBeenCalledOnce();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("offers save, discard, and cancel when drafts are dirty", async () => {
  makeMetadataDirty();
  await user.click(screen.getByRole("button", { name: "回到图纸列表" }));
  expect(screen.getByRole("dialog", { name: "返回图纸列表？" })).toBeVisible();
  expect(screen.getByRole("button", { name: "保存并返回" })).toHaveFocus();
});

it("discards without sending a save command", async () => {
  makeMetadataDirty();
  await openReturnDialog();
  await user.click(screen.getByRole("button", { name: "不保存返回" }));
  expect(onSave).not.toHaveBeenCalled();
  expect(onReset).toHaveBeenCalledOnce();
});

it("stays in the workbench when saving a draft fails", async () => {
  onSave.mockRejectedValueOnce(new Error("conflict"));
  makeMetadataDirty();
  await openReturnDialog();
  await user.click(screen.getByRole("button", { name: "保存并返回" }));
  expect(onReset).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog", { name: "返回图纸列表？" })).toBeVisible();
});
```

另测 Escape/取消关闭 dialog 且不清草稿；全部保存成功后才调用 `onReset()`。

- [ ] **Step 2: Run safe-return tests to verify RED**

Run:

```bash
cd frontend
npm test -- src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL because the button still has old copy and no dialog.

- [ ] **Step 3: Implement dialog and save orchestration**

在 `InspectionWorkbench`：

- 添加 `returnDialogOpen`、`returnSaving` 和聚焦 ref。
- 点击返回时按 `localDraftDirty` 决定直接返回或开 dialog。
- `saveAndReturn()` 先保存 dirty metadata，再按固定次序调用 review、source、selected SIP handles。
- 任一 `false` 保持 dialog 打开并停止；全部成功调用 `onReset()`。
- dialog 使用 `role="dialog"`、`aria-modal="true"`、标题和说明；Escape 调用取消。
- `returnSaving` 时禁用三个决策按钮和背景编辑命令。

- [ ] **Step 4: Write failing latest-version test**

在 `ProjectWorkbenchApp.test.tsx` 模拟两个顺序 `onSave` command，第一次 save 后 `/workbench` refresh 返回 version 2，断言第二个 `saveWorkingCopy` request 使用 version 2，而不是初始 version 1。

- [ ] **Step 5: Run latest-version test to verify RED**

Run:

```bash
cd frontend
npm test -- src/components/workbench/ProjectWorkbenchApp.test.tsx
```

Expected: FAIL because `save()` closes over the render-time `snapshot`.

- [ ] **Step 6: Make refreshed snapshot version synchronously available**

在 `ProjectWorkbenchApp` 添加：

```ts
const snapshotRef = useRef<ProjectWorkbenchView>();
```

`refresh()` 在 `setSnapshot(loaded)` 前执行 `snapshotRef.current = loaded`。`save()` 读取：

```ts
const currentSnapshot = snapshotRef.current;
if (currentSnapshot === undefined) {
  throw new Error("project workbench is not loaded");
}
await saveWorkingCopy(
  postJson,
  projectId,
  operatorId,
  currentSnapshot.working_copy.version,
  command,
);
```

- [ ] **Step 7: Run safe-return and latest-version tests to verify GREEN**

Run:

```bash
cd frontend
npm test -- src/components/workbench/InspectionWorkbench.test.tsx src/components/workbench/ProjectWorkbenchApp.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit safe return**

```bash
git add frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/components/workbench/InspectionWorkbench.test.tsx frontend/src/components/workbench/ProjectWorkbenchApp.tsx frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles/workbench.css
git commit -m "feat: guard return to drawing list"
```

---

### Task 5: Deep-Link Compatibility And Integrated Verification

**Files:**
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/main.test.tsx`
- Modify: `frontend/src/app/QualityInspectionApp.test.tsx`

**Interfaces:**
- Consumes: explicit `project_id` and `operator_id` query parameters.
- Produces: valid deep links still open the workbench; returning registers/touches the project as `未命名图纸.pdf`, clears session project context, removes query routing by navigating to `/`, and displays the list.

- [ ] **Step 1: Write the failing deep-link test**

Mock `ProjectWorkbenchApp`, set:

```ts
window.history.replaceState(
  {},
  "",
  `/?project_id=${PROJECT_A}&operator_id=${OPERATOR_A}`,
);
```

断言 workbench renders；触发 `onReset` 后 registry 包含 `PROJECT_A` 和 `未命名图纸.pdf`，session current project 已清理，并请求导航到 `/`。无效或缺一参数时走 `QualityInspectionApp` list-first 路径。

- [ ] **Step 2: Run the deep-link test to verify RED**

Run:

```bash
cd frontend
npm test -- src/main.test.tsx
```

Expected: FAIL because deep-link return still calls `beginAnotherDrawing()`.

- [ ] **Step 3: Implement deep-link list return**

在 `main.tsx` 的深链分支中调用 `registerLocalDrawing()`/`touchLocalDrawing()` 和 `clearCurrentProjectId()`，然后 `window.location.assign("/")`。移除 `beginAnotherDrawing()` import；不改变深链参数校验。

- [ ] **Step 4: Run all focused tests**

Run:

```bash
cd frontend
npm test -- src/app/localDrawingRegistry.test.ts src/app/DrawingListScreen.test.tsx src/app/QualityInspectionApp.test.tsx src/app/localContext.test.ts src/components/workbench/draftSave.test.ts src/components/review/ReviewPanel.test.tsx src/components/workbench/InspectionItemTable.test.tsx src/components/workbench/SelectedSipDetailFields.test.tsx src/components/workbench/SipInformationPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx src/components/workbench/ProjectWorkbenchApp.test.tsx src/main.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Run full frontend verification**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: all tests PASS and production build exits 0.

- [ ] **Step 6: Run Chrome smoke**

启动 repo 现有 frontend/backend runtime 后，通过 Chrome 集成验证：

1. 根地址默认显示图纸列表。
2. 上传第一份 PDF，进入 processing/workbench 后返回列表。
3. 上传或打开第二份 PDF，确认两份条目同时存在。
4. 无 dirty 直接返回。
5. 制造 metadata 或检验项 dirty，验证取消、不保存返回、保存失败留在原页、保存成功返回。
6. 刷新根地址仍默认显示列表；打开列表项可恢复项目。

保存截图到 `.local/design-qa/` 只作本地证据，不 stage。

- [ ] **Step 7: Commit compatibility and verification tests**

```bash
git add frontend/src/main.tsx frontend/src/main.test.tsx frontend/src/app/QualityInspectionApp.test.tsx
git commit -m "test: cover drawing list navigation"
```

---

## Rollback

按提交逆序回滚 Task 5 → Task 4 → Task 3 → Task 2 → Task 1。回滚不删除后端项目或正式审核结果；只移除本机目录和返回保护。每一步回滚后至少运行对应 focused tests，完整回滚后运行 `cd frontend && npm test && npm run build`。
