# Merged Inspection Review Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把检验项列表和当前项编辑器合并为固定高度的双栏审核工作区，移除额外的“保存审核修改”，并用“修改 → 修改保存”及其他明确动作直接提交现有 Review command。

**Architecture:** `InspectionWorkbench` 继续是 frontend composition 和提交状态的单一 Owner，但把 `pendingCommand + 顶部 Save` 替换为串行 `submitCommand(command)`。`InspectionItemTable` 作为左侧 compact master list，`ReviewPanel` 作为右侧 detail editor；两栏独立滚动，backend Review aggregate、command schema、working-copy version 和 `saveWorkingCopy()` 保持不变。

**Tech Stack:** React 19、TypeScript、Vitest、Testing Library、Vite、Chrome DevTools MCP。

---

## Execution Contract

- **Selected lane:** `Standard`
  - 只修改一个 frontend feature group，不改变稳定 API/schema、认证、数据迁移或业务
    Owner；但涉及多个相关 component、显式提交节奏和真实 browser smoke。
- **Selected spec:**
  `docs/superpowers/specs/2026-07-24-merged-inspection-review-workspace-design.md`
- **Selection evidence:**
  - 当前 `InspectionItemTable` 与 `candidate-editor/ReviewPanel` 纵向分离；
  - 当前 `pendingCommand` 依赖顶部“保存审核修改”；
  - 用户已确认 A 双栏、双栏独立滚动和“先修改、再修改保存”。
- **Validation action:** `amend`
  - retirement 只针对 frontend 的独立 pending/save path；
  - `REV-003` 的 durable contract 保持：working copy versioned、显式用户动作、
    `expected_version/operator_id`、Save 不等于确认、无 autosave。
- **Single owner:** `InspectionWorkbench.submitCommand()` 只拥有 frontend 提交串行化和
  状态展示；正式 mutation 仍由 backend Review aggregate 提交。
- **Old path to remove:**
  - `InspectionWorkbench.pendingCommand`；
  - `queueCommand()`；
  - 顶部“保存审核修改”按钮；
  - `candidate-editor` 第二套纵向 wrapper；
  - `ReviewPanel` 的“取消检验项修改”按钮和 reset path。
- **Unchanged contracts:**
  - `ReviewCommand` payload 和 API route；
  - `saveWorkingCopy()` 的 version/operator headers；
  - 单 editor lease、optimistic version conflict、freeze/confirm；
  - PDF/list selection identity、source-only command、SIP、balloon 和 export 语义；
  - 输入变化本身绝不 POST，只有明确按钮动作提交。
- **Allowed paths:**
  - `frontend/src/components/review/ReviewPanel.tsx`
  - `frontend/src/components/review/ReviewPanel.test.tsx`
  - `frontend/src/components/workbench/InspectionWorkbench.tsx`
  - `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
  - `frontend/src/components/workbench/InspectionItemTable.tsx`
  - `frontend/src/components/workbench/InspectionItemTable.test.tsx`
  - `frontend/src/components/workbench/FreezeReviewButton.test.tsx`
  - `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`
  - `frontend/src/copy/zhCN.ts`
  - `frontend/src/styles/workbench.css`
- **Protected dirty files:**
  - 不修改 `.env.example`、`.gitignore`、`AGENTS.md`、`compose.yaml`；
  - 不清理 `.local/`、`.superpowers/`、`__pycache__/` 或 `frontend/test-results/`。
- **E2E ownership delta:** design 阶段未提交的
  `frontend/e2e/chinese-pdf-upload-mvp.spec.ts` 已由相邻工作独立提交到
  `6f4cd6a`，当前 preflight 为 clean。允许只把
  `saveQueuedReviewCommand()` 改成“action click + response waits”，否则测试会继续
  查找已移除的按钮；不得改变 PDF、balloon 或 export assertions。
- **Writer ownership and order:** 任何时刻只有一个 writer，严格按 Task 1 → 4
  串行；reviewer 只读，Task 5 才进入。
- **Focused verification command:**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/FreezeReviewButton.test.tsx \
  src/features/review/saveWorkingCopy.test.ts
micromamba run -n qi-p0 npm --prefix frontend run build
```

- **Rollback:** 每个 task 只 revert 自己的 commit。Task 4 layout commit 若回滚，
  Task 1～3 的 direct-submit 与 edit-state commits 仍可独立运行。实际发生 rollback
  后第一项验证：

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionWorkbench.test.tsx
```

## File Structure

### Review Detail

- `frontend/src/components/review/ReviewPanel.tsx`
  - 拥有已选项 `view/edit` state、字段 draft 和 Review command 构造；
  - command 返回 `false` 时保留 draft，返回 `true/void` 时完成本地清理。
- `frontend/src/components/review/ReviewPanel.test.tsx`
  - 证明默认只读、“修改 → 修改保存”、失败保留和八类命令。

### Workbench Composition

- `frontend/src/components/workbench/InspectionWorkbench.tsx`
  - 拥有唯一 `submitCommand()`、单 in-flight guard、save status 和双栏 composition；
  - dirty detail 阻止静默切换选中项。
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
  - 证明没有顶部 Save、明确动作直接提交、重复提交阻断、失败和 dirty selection。
- `frontend/src/components/workbench/FreezeReviewButton.test.tsx`
  - 保持真实 `ProjectWorkbenchApp` API mutation、错误和 freeze ordering regression。

### Master List

- `frontend/src/components/workbench/InspectionItemTable.tsx`
  - 增加 compact master-list projection；
  - source/SIP command 成功后才清 dirty。
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
  - 证明 compact columns 和失败保留 source/SIP draft。

### Copy And Layout

- `frontend/src/copy/zhCN.ts`
  - 提供“修改保存”“请先保存当前检验项修改”和合并工作区 accessible name。
- `frontend/src/styles/workbench.css`
  - 提供双栏固定高度、左右独立 overflow、compact grid 和窄屏回退；
  - 删除不再有 consumer 的 `candidate-editor` 样式。

## Task 0: Check Mature Master-Detail Interaction References

**Files:**
- Read only: 当前 spec、plan 和 frontend components
- No local file modifications

- [ ] **Step 1: Invoke `github-oss-fusion` in read-only mode**

搜索成熟 React master-detail editor 的以下三个行为，不复制大段实现：

```text
1. fixed-height master/detail panes with independent overflow
2. explicit edit mode with save disabled until dirty
3. failed async command keeps local draft retryable
```

只接受与本 spec 一致的小型模式：CSS grid/overflow 结构、button state 测试方式或
async success boolean。不得新增 dependency、state library、router 或通用表单框架。

- [ ] **Step 2: Record the bounded fusion decision**

执行进度中记录：

```text
Repositories inspected: record the exact owner/repository names returned by the search
Fused: record the exact small patterns used; write "none" when no pattern is adopted
Skipped: dependencies, architecture changes, copied implementation
Local validation target: Task 1 RED
```

Expected: 研究不修改 workspace；若没有优于现有 repository pattern 的做法，明确
记录 `Fused: none` 并继续 Task 1。

## Task 1: Add Explicit View/Edit State To ReviewPanel

**Files:**
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/copy/zhCN.ts`

- [ ] **Step 1: Write the failing edit-state tests**

在 `ReviewPanel.test.tsx` 加入 `waitFor` import，并新增：

```tsx
test("已选检验项默认只读，修改后由修改保存显式提交", async () => {
  const onCommand = vi.fn().mockResolvedValue(true);
  render(
    <ReviewPanel
      items={[{
        item_id: "edit-item",
        item_type: "linear_dimension",
        raw_text: "50",
        nominal: "50",
        active: true,
      }]}
      onCommand={onCommand}
      selectedItemId="edit-item"
    />,
  );

  const rawText = screen.getByRole("textbox", { name: "原始标注：50" });
  const startEdit = screen.getByRole("button", { name: "修改检验项：50" });
  const saveEdit = screen.getByRole("button", {
    name: "修改保存检验项：50",
  });
  expect(rawText.hasAttribute("disabled")).toBe(true);
  expect(saveEdit.hasAttribute("disabled")).toBe(true);

  fireEvent.click(startEdit);
  expect(rawText.hasAttribute("disabled")).toBe(false);
  fireEvent.change(rawText, { target: { value: "50.0" } });
  expect(saveEdit.hasAttribute("disabled")).toBe(false);
  expect(onCommand).not.toHaveBeenCalled();

  fireEvent.click(saveEdit);
  await waitFor(() => expect(onCommand).toHaveBeenCalledWith({
    type: "edit",
    item_id: "edit-item",
    fields: { raw_text: "50.0", nominal: "50" },
  }));
  expect(rawText.hasAttribute("disabled")).toBe(true);
  expect(screen.queryByText("取消检验项修改")).toBeNull();
});

test("修改保存失败时保留编辑状态和草稿", async () => {
  const onCommand = vi.fn().mockResolvedValue(false);
  render(
    <ReviewPanel
      items={[{
        item_id: "retry-item",
        item_type: "linear_dimension",
        raw_text: "50",
        nominal: "50",
        active: true,
      }]}
      onCommand={onCommand}
      selectedItemId="retry-item"
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "修改检验项：50" }));
  const rawText = screen.getByRole("textbox", { name: "原始标注：50" });
  fireEvent.change(rawText, { target: { value: "50 retry" } });
  fireEvent.click(screen.getByRole("button", {
    name: "修改保存检验项：50",
  }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledOnce());
  expect((rawText as HTMLInputElement).value).toBe("50 retry");
  expect(rawText.hasAttribute("disabled")).toBe(false);
});
```

同时更新现有 `P0-UI-006` test：

```tsx
fireEvent.click(screen.getByRole("button", { name: "修改检验项：M6" }));
fireEvent.change(screen.getByLabelText("拆分内容：M6"), {
  target: { value: "M6|深10" },
});
fireEvent.click(screen.getByRole("button", { name: "拆分检验项：M6" }));

fireEvent.click(screen.getByRole("button", {
  name: "修改检验项：10 ±0.02",
}));
fireEvent.change(screen.getByLabelText("原始标注：10 ±0.02"), {
  target: { value: "12.50 +0.03" },
});
fireEvent.change(screen.getByLabelText("基本尺寸：10 ±0.02"), {
  target: { value: "12.50" },
});
fireEvent.change(screen.getByLabelText("上公差：10 ±0.02"), {
  target: { value: "0.03" },
});
fireEvent.click(screen.getByRole("button", {
  name: "修改保存检验项：10 ±0.02",
}));

fireEvent.click(screen.getByRole("button", {
  name: "修改检验项：Ra 3.2",
}));
fireEvent.change(screen.getByLabelText("原始标注：Ra 3.2"), {
  target: { value: "Ra 1.6" },
});
fireEvent.change(screen.getByLabelText("坐标：Ra 3.2"), {
  target: { value: "11,12,13,14" },
});
fireEvent.change(screen.getByLabelText("粗分类：Ra 3.2"), {
  target: { value: "weld" },
});
fireEvent.click(screen.getByLabelText("需要人工确认：Ra 3.2"));
fireEvent.click(screen.getByRole("button", {
  name: "修改保存检验项：Ra 3.2",
}));
```

保留对八类 command type 的完整断言。

该 `P0-UI-006` test 改为 `async`，在读取 `onCommand.mock.calls` 前等待两个 async
edit command：

```tsx
await waitFor(() => {
  expect(
    onCommand.mock.calls
      .map(([command]) => command)
      .filter((command) => command.type === "edit"),
  ).toHaveLength(2);
});
const commands = onCommand.mock.calls.map(([command]) => command);
```

把“未来 item_type 安全降级”test 的 command 部分改为：

```tsx
fireEvent.click(screen.getByRole("button", {
  name: "修改检验项：新型标注",
}));
fireEvent.change(screen.getByRole("textbox", {
  name: "原始标注：新型标注",
}), {
  target: { value: "新型标注（修改）" },
});
fireEvent.click(screen.getByRole("button", {
  name: "修改保存检验项：新型标注",
}));
expect(onCommand).toHaveBeenCalledWith({
  type: "edit",
  item_id: "future-item",
  fields: { raw_text: "新型标注（修改）" },
});
```

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx
```

Expected: FAIL，因为字段仍默认可编辑、“修改保存”不存在，旧 cancel action 仍存在。

- [ ] **Step 3: Add the command outcome contract and edit state**

在 `ReviewPanel.tsx` 把 callback type 改为：

```tsx
type CommandOutcome = boolean | void;

type ReviewPanelProps = {
  items: ReviewItem[];
  onCommand: (
    command: ReviewCommand,
  ) => CommandOutcome | Promise<CommandOutcome>;
  disabled?: boolean;
  selectedItemId?: string;
  onSelectItem?: (itemId: string) => void;
  pageIndex?: number;
  onDraftChange?: (dirty: boolean) => void;
};
```

在 component state 中加入：

```tsx
const [editingItemId, setEditingItemId] = useState<string>();
const isEditingSelected = selectedItem?.item_id === editingItemId;
const selectedItemDirty = selectedItem !== undefined
  && dirtyItemIds.includes(selectedItem.item_id);

useEffect(() => {
  setEditingItemId(undefined);
}, [selectedItemId]);
```

把所有已选项字段的 `disabled={disabled}` 改为：

```tsx
disabled={disabled || !isEditingSelected}
```

complex fieldset 和 split input 使用相同条件。合并 selector 和 manual-add fieldset
不受 `isEditingSelected` 约束。

- [ ] **Step 4: Replace cancel with modify and make edit-save outcome-aware**

在 `zhCN.review` 中保留：

```tsx
edit: "修改",
editSave: "修改保存",
```

删除不再有 consumer 的：

```tsx
cancelEdit: "取消检验项修改",
```

把 `editItem()` 改为 async，并只在 handler 没有返回 `false` 时清 dirty：

```tsx
const commandSucceeded = async (
  command: ReviewCommand,
): Promise<boolean> => (await onCommand(command)) !== false;

const finishSavedEdit = (itemId: string) => {
  clearItemDirty(itemId);
  setEditingItemId(undefined);
};

const editItem = async (item: ReviewItem) => {
  const fields: Record<string, unknown> = {
    raw_text: rawTexts[item.item_id] ?? item.raw_text,
  };
  if (item.coarse_type !== undefined) {
    const coordinates = parseCoordinates(complexCoordinates[item.item_id] ?? "");
    if (coordinates === null) return;
    const saved = await commandSucceeded({
      type: "edit",
      item_id: item.item_id,
      fields: {
        ...fields,
        coordinates,
        coarse_type: coarseTypes[item.item_id] ?? item.coarse_type,
        requires_confirmation:
          confirmationFields[item.item_id] ?? item.requires_confirmation ?? false,
      },
    });
    if (saved) finishSavedEdit(item.item_id);
    return;
  }
  for (const field of coreFieldsFor(item.item_type)) {
    const value = coreValues[item.item_id]?.[field.key] ?? "";
    if (value.trim() === "" && item[field.key] === undefined) continue;
    const parsed = parseCoreValue(field, value);
    if (!parsed.valid) return;
    fields[field.key] = parsed.value;
  }
  const saved = await commandSucceeded({
    type: "edit",
    item_id: item.item_id,
    fields,
  });
  if (saved) finishSavedEdit(item.item_id);
};
```

操作栏中的两个按钮改为：

```tsx
<button
  type="button"
  className="review-command-rail__primary"
  aria-label={zhCN.review.actionForItem(
    zhCN.review.editSave,
    selectedItem.raw_text,
  )}
  disabled={disabled || !isEditingSelected || !selectedItemDirty}
  onClick={() => void editItem(selectedItem)}
>
  {zhCN.review.editSave}
</button>
<button
  type="button"
  className="review-command-rail__secondary"
  aria-label={zhCN.review.actionForItem(
    zhCN.review.edit,
    selectedItem.raw_text,
  )}
  disabled={disabled || isEditingSelected}
  onClick={() => setEditingItemId(selectedItem.item_id)}
>
  {zhCN.review.edit}
</button>
```

删除 `resetItemDraft()`。把 manual add 和 split 的本地 reset 移到
`await commandSucceeded(...)` 为 `true` 之后：

```tsx
const addManualItem = async () => {
  const coordinates = parseCoordinates(manualCoordinates);
  if (manualRawText.trim() === "" || coordinates === null) return;
  const saved = await commandSucceeded({
    type: "add",
    raw_text: manualRawText,
    item_type: manualType,
    coordinates,
    scope: manualScope,
    balloon_required: manualBalloonRequired,
    page_index: pageIndex,
  });
  if (saved) resetManualItem();
};

const splitItem = async (item: ReviewItem) => {
  const parts = (splitTexts[item.item_id] ?? "")
    .split("|")
    .map((rawText) => rawText.trim())
    .filter(Boolean)
    .map((raw_text) => ({ raw_text }));
  if (parts.length < 2 || item.item_type === undefined) return;
  const saved = await commandSucceeded({
    type: "split",
    item_id: item.item_id,
    parts,
  });
  if (!saved) return;
  setSplitTexts((current) => ({ ...current, [item.item_id]: "" }));
  setDirtySplitIds((current) =>
    current.filter((candidate) => candidate !== item.item_id),
  );
};
```

对应 button 使用：

```tsx
onClick={() => void addManualItem()}
onClick={() => void splitItem(selectedItem)}
```

handler 返回 `false` 时保留输入。

- [ ] **Step 5: Run GREEN**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx
```

Expected: all `ReviewPanel` tests PASS，八类 command coverage 保持。

- [ ] **Step 6: Commit Task 1**

```bash
git add \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/copy/zhCN.ts
git diff --cached --check
git commit -m "feat: add explicit inspection edit mode"
```

## Task 2: Submit Explicit Review Actions Directly

**Files:**
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/FreezeReviewButton.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`

- [ ] **Step 1: Replace the pending-Save tests with direct-submit RED tests**

在 `InspectionWorkbench.test.tsx` 用以下测试替换
`keeps one pending command stable until explicit Save`：

```tsx
test("明确审核动作直接提交且不渲染额外保存按钮", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[]}
      sources={[]}
      balloons={[]}
      items={[{
        item_id: "i1",
        item_type: "thread",
        raw_text: "M6",
        balloon_required: true,
        active: true,
      }]}
      onSave={onSave}
    />,
  );

  expect(screen.queryByRole("button", { name: "保存审核修改" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "保留检验项：M6" }));

  await waitFor(() => expect(onSave).toHaveBeenCalledWith({
    type: "keep",
    item_id: "i1",
  }));
  expect(within(
    screen.getByRole("region", { name: "项目摘要" }),
  ).getByRole("status").textContent).toBe("已保存");
});
```

用以下测试替换 `submits Save only once while the request is in flight`：

```tsx
test("审核命令请求期间阻止第二个明确动作", async () => {
  let resolveSave!: () => void;
  const onSave = vi.fn(() => new Promise<void>((resolve) => {
    resolveSave = resolve;
  }));
  render(
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[]}
      sources={[]}
      balloons={[]}
      items={[{
        item_id: "i1",
        item_type: "thread",
        raw_text: "M6",
        balloon_required: true,
        active: true,
      }]}
      onSave={onSave}
    />,
  );

  const keep = screen.getByRole("button", { name: "保留检验项：M6" });
  const exclude = screen.getByRole("button", { name: "排除检验项：M6" });
  fireEvent.click(keep);
  fireEvent.click(exclude);

  expect(onSave).toHaveBeenCalledOnce();
  expect(exclude.hasAttribute("disabled")).toBe(true);
  resolveSave();
  await waitFor(() => expect(exclude.hasAttribute("disabled")).toBe(false));
});
```

更新同文件的 metadata、source promote 和 blank-source tests：点击各自的明确
“确认 SIP 信息”或“添加为检验项”后直接 `waitFor(onSave)`，删除对
“保存审核修改”的点击和断言。

把首个“本地草稿立即显示未保存”test 改成无 autosave regression：

```tsx
fireEvent.click(screen.getByRole("button", { name: "修改检验项：M6" }));
fireEvent.change(screen.getByRole("textbox", { name: "原始标注：M6" }), {
  target: { value: "M8" },
});
expect(saveStatus.textContent).toBe("有未保存修改");
expect(onSave).not.toHaveBeenCalled();
fireEvent.click(screen.getByRole("button", {
  name: "修改保存检验项：M6",
}));
await waitFor(() => expect(onSave).toHaveBeenCalledWith({
  type: "edit",
  item_id: "i1",
  fields: {
    raw_text: "M8",
  },
}));
```

“外部操作反馈”test 改为断言不存在空的审核操作 region：

```tsx
expect(within(summary).getByRole("status").textContent)
  .toBe("审核修改已提交");
expect(screen.queryByRole("region", { name: "审核流程操作" })).toBeNull();
```

有 `workingCopy/onFreeze/onGenerate/onConfirm` 的 action-label test 使用：

```tsx
expect(actionLabels).toEqual([
  "冻结检验项",
  "生成气泡",
  "确认审核结果",
  "生成正式文件",
]);
```

更新 `FreezeReviewButton.test.tsx`：

- 点击“保留”后直接等待 `/review/commands`；
- 409 test 点击“保留”后直接等待“保存失败”；
- 删除两处“保存审核修改”点击；
- 保持 version/operator body、freeze/generate/confirm ordering 断言。

把 `frontend/e2e/chinese-pdf-upload-mvp.spec.ts` 的 helper 改为：

```tsx
import { expect, test, type Locator, type Page } from "@playwright/test";

async function submitReviewAction(
  page: Page,
  action: Locator,
): Promise<void> {
  const commandResponse = page.waitForResponse(
    (response) => (
      response.request().method() === "POST"
      && response.url().includes("/review/commands")
    ),
    { timeout: 60_000 },
  );
  const refreshedWorkbench = page.waitForResponse(
    (response) => (
      response.request().method() === "GET"
      && response.url().endsWith("/workbench")
    ),
    { timeout: 60_000 },
  );
  await expect(action).toBeEnabled();
  await action.click();
  expect((await commandResponse).ok(), "审核命令响应必须成功").toBe(true);
  expect((await refreshedWorkbench).ok(), "审核命令后的工作台刷新必须成功")
    .toBe(true);
}
```

把现有五个“先 click，再 `saveQueuedReviewCommand(page)`”调用改为一次：

```tsx
await submitReviewAction(page, ignore);
await submitReviewAction(page, acceptConfirmation);
await submitReviewAction(page, requireBalloon);
await submitReviewAction(
  page,
  sipDetails.getByRole("button", { name: "确认所选 SIP 字段" }),
);
await submitReviewAction(
  page,
  metadata.getByRole("button", { name: "确认 SIP 信息" }),
);
```

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/FreezeReviewButton.test.tsx
```

Expected: FAIL，因为顶部按钮仍存在，明确 action 只 queue command 而不调用
`onSave`。

- [ ] **Step 3: Replace pendingCommand with a single serialized submitter**

在 `InspectionWorkbench.tsx` import `useRef`：

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
```

删除：

```tsx
const [pendingCommand, setPendingCommand] = useState<ReviewCommand>();
```

加入：

```tsx
const savingRef = useRef(false);

const submitCommand = async (command: ReviewCommand): Promise<boolean> => {
  if (savingRef.current || busy || reviewImmutable) return false;
  savingRef.current = true;
  setSaving(true);
  setSaveState(zhCN.workbench.saving);
  try {
    await onSave(command);
    setSaveState(zhCN.workbench.saved);
    return true;
  } catch {
    setSaveState(zhCN.workbench.saveFailed);
    return false;
  } finally {
    savingRef.current = false;
    setSaving(false);
  }
};
```

删除 `queueCommand()` 和 `save()`。`displayedSaveState` 只根据
`saving / saveFailed / localDraftDirty / saved` 计算：

```tsx
const displayedSaveState = saving
  ? zhCN.workbench.saving
  : saveState === zhCN.workbench.saveFailed
    ? zhCN.workbench.saveFailed
    : localDraftDirty
      ? zhCN.workbench.pending
      : zhCN.workbench.saved;
```

- [ ] **Step 4: Wire every explicit producer to submitCommand**

只在 `workingCopy/onFreeze/onGenerate/onConfirm` 都存在时渲染
`<section className="review-actions">` 和 `FreezeReviewButton`，删除其中：

```tsx
<button className="primary-action">
  {zhCN.workbench.save}
</button>
```

条件结构为：

```tsx
{workingCopy === undefined
  || onFreeze === undefined
  || onGenerate === undefined
  || onConfirm === undefined
  ? null
  : (
    <section className="review-actions" aria-label="审核流程操作">
      <FreezeReviewButton
        workingCopy={workingCopy}
        balloons={balloons}
        balloonBlockers={balloonBlockers}
        busy={busy || saving || finalized || localDraftDirty}
        onFreeze={onFreeze}
        onGenerate={onGenerate}
        onConfirm={onConfirm}
      />
    </section>
  )}
```

把以下 props 改为：

```tsx
<InspectionItemTable
  ...
  disabled={saving || busy || reviewImmutable}
  onCommand={submitCommand}
/>
<ReviewPanel
  ...
  disabled={saving || busy || reviewImmutable}
  onCommand={submitCommand}
/>
```

`FreezeReviewButton.busy` 使用：

```tsx
busy={busy || saving || finalized || localDraftDirty}
```

metadata confirmation 只在成功后清 dirty：

```tsx
onClick={() => {
  void (async () => {
    const saved = await submitCommand({
      type: "set_sip_metadata",
      ...metadata,
    });
    if (saved) setMetadataDraftDirty(false);
  })();
}}
```

删除 `zhCN.workbench.save`，保留 `saving/saved/saveFailed/pending` 状态文案。

- [ ] **Step 5: Run GREEN and direct-save regression**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/FreezeReviewButton.test.tsx \
  src/features/review/saveWorkingCopy.test.ts
micromamba run -n qi-p0 npm --prefix frontend run e2e:list
```

Expected: zero failures；`saveWorkingCopy()` 仍携带
`expected_version/operator_id`，input change 不调用 API，Playwright 成功列出测试且
没有 TypeScript/locator helper error。

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  frontend/e2e/chinese-pdf-upload-mvp.spec.ts \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/FreezeReviewButton.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/copy/zhCN.ts
git diff --cached --check
git commit -m "feat: submit review actions directly"
```

## Task 3: Preserve Failed Drafts And Block Dirty Selection Changes

**Files:**
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/copy/zhCN.ts`

- [ ] **Step 1: Write failed-command and dirty-selection RED tests**

在 `InspectionItemTable.test.tsx` 新增：

```tsx
test("来源 command 返回失败时保留 dirty 草稿", async () => {
  const onCommand = vi.fn().mockResolvedValue(false);
  const onDraftChange = vi.fn();
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-retry",
        sourceId: "source-retry",
        rawText: "去毛刺",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="all"
      selectedSourceId="source-retry"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
    target: { value: "去除全部毛刺" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
    target: { value: "general_requirement" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledOnce());
  expect((screen.getByRole("textbox", {
    name: "原始标注",
  }) as HTMLInputElement).value).toBe("去除全部毛刺");
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
});
```

在 `InspectionWorkbench.test.tsx` 新增：

```tsx
test("当前项有未保存修改时阻止静默切换", () => {
  render(
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[]}
      sources={[]}
      balloons={[]}
      items={[
        {
          item_id: "first",
          item_type: "linear_dimension",
          raw_text: "10",
          nominal: "10",
          active: true,
        },
        {
          item_id: "second",
          item_type: "linear_dimension",
          raw_text: "20",
          nominal: "20",
          active: true,
        },
      ]}
      onSave={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "修改检验项：10" }));
  fireEvent.change(screen.getByRole("textbox", { name: "原始标注：10" }), {
    target: { value: "10.0" },
  });
  fireEvent.click(screen.getByRole("row", { name: /20/ }));

  expect(screen.getByRole("article", { name: "10" })).not.toBeNull();
  expect(within(
    screen.getByRole("region", { name: "项目摘要" }),
  ).getByRole("status").textContent).toBe("请先修改保存当前检验项");
});
```

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL，因为 source/SIP command 在提交前清 dirty，选中项没有 dirty guard。

- [ ] **Step 3: Make InspectionItemTable command cleanup outcome-aware**

在 props 中使用：

```tsx
type CommandOutcome = boolean | void;

onCommand?: (
  command: ReviewCommand,
) => CommandOutcome | Promise<CommandOutcome>;
```

加入：

```tsx
const commandSucceeded = async (
  command: ReviewCommand,
): Promise<boolean> => {
  if (onCommand === undefined) return false;
  return (await onCommand(command)) !== false;
};
```

source promote 示例：

```tsx
onClick={() => {
  if (
    selectedSourceDraft.itemType === ""
    || selectedSource.pageIndex === undefined
  ) return;
  void (async () => {
    const saved = await commandSucceeded({
      type: "promote_source",
      observation_id: selectedSource.observationId,
      raw_text: selectedSourceDraft.rawText,
      item_type: selectedSourceDraft.itemType,
      scope: selectedSourceDraft.scope,
      balloon_required: selectedSourceDraft.balloonRequired,
      page_index: selectedSource.pageIndex,
    });
    if (saved) clearSelectedSourceDirty();
  })();
}}
```

`ignore_source` 使用：

```tsx
onClick={() => {
  void (async () => {
    const saved = await commandSucceeded({
      type: "ignore_source",
      observation_id: selectedSource.observationId,
    });
    if (saved) clearSelectedSourceDirty();
  })();
}}
```

`set_sip_detail_fields` 使用：

```tsx
onClick={() => {
  void (async () => {
    const saved = await commandSucceeded({
      type: "set_sip_detail_fields",
      item_id: selected.item_id,
      inspection_item: draft.inspectionItem,
      inspection_standard: draft.inspectionStandard,
      inspection_method: draft.inspectionMethod,
      key_dimension: draft.keyDimension,
      inspection_role: draft.inspectionRole,
      source_page: Number(draft.sourcePage),
      remarks: draft.remarks,
    });
    if (saved) clearSelectedDraft();
  })();
}}
```

删除两个 handler 在 command 前执行的 clear。SIP cancel 仍只恢复本地 baseline，
不提交。

- [ ] **Step 4: Add a dirty selection guard and live notice**

在 `zhCN.workbench` 增加：

```tsx
finishCurrentEdit: "请先修改保存当前检验项",
```

在 `InspectionWorkbench` 加入：

```tsx
const [selectionBlocked, setSelectionBlocked] = useState(false);

useEffect(() => {
  if (!reviewDraftDirty) setSelectionBlocked(false);
}, [reviewDraftDirty]);
```

让 `selectItem()` 返回 boolean：

```tsx
const selectItem = (itemId: string): boolean => {
  if (reviewDraftDirty && itemId !== selectedItemId) {
    setSelectionBlocked(true);
    return false;
  }
  setSelectionBlocked(false);
  setSelectedItemId(itemId);
  setSelectedSourceId(undefined);
  const item = items.find((candidate) => candidate.item_id === itemId);
  const balloon = balloons.find(
    (candidate) =>
      candidate.status !== "deleted" && candidate.itemId === itemId,
  );
  setSelectedBalloonId(balloon?.id);
  setPageIndex(item?.page_index ?? balloon?.pageIndex ?? pageIndex);
  return true;
};
```

`selectSource()` 使用：

```tsx
const selectSource = (sourceId: string): boolean => {
  if (reviewDraftDirty && sourceId !== selectedSourceId) {
    setSelectionBlocked(true);
    return false;
  }
  setSelectionBlocked(false);
  setSelectedItemId(undefined);
  setSelectedSourceId(sourceId);
  setSelectedBalloonId(undefined);
  const source = sources.find((candidate) => candidate.id === sourceId);
  setPageIndex(source?.pageIndex ?? pageIndex);
  return true;
};
```

PDF balloon callback 先执行：

```tsx
if (!selectItem(itemId)) return;
setSelectedBalloonId(balloonId);
```

保存状态优先显示：

```tsx
const displayedSaveState = selectionBlocked
  ? zhCN.workbench.finishCurrentEdit
  : saving
    ? zhCN.workbench.saving
    : saveState === zhCN.workbench.saveFailed
      ? zhCN.workbench.saveFailed
      : localDraftDirty
        ? zhCN.workbench.pending
        : zhCN.workbench.saved;
```

- [ ] **Step 5: Run GREEN**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/review/ReviewPanel.test.tsx
```

Expected: zero failures；failed submit 保留 local draft，成功 submit 才清 dirty。

- [ ] **Step 6: Commit Task 3**

```bash
git add \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/copy/zhCN.ts
git diff --cached --check
git commit -m "fix: preserve failed review drafts"
```

## Task 4: Merge The Master List And Detail Editor

**Files:**
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

- [ ] **Step 1: Write compact-list and merged-workspace RED tests**

在 `InspectionItemTable.test.tsx` 新增：

```tsx
test("compact master list 只保留序号检验项和状态三列", () => {
  render(
    <InspectionItemTable
      items={[{
        item_id: "compact-item",
        item_type: "linear_dimension",
        raw_text: "50",
        nominal: "50",
        page_index: 0,
        active: true,
      }]}
      balloons={[]}
      filter="all"
      selectedItemId="compact-item"
      compact
      onSelectItem={vi.fn()}
    />,
  );

  const table = screen.getByRole("table", { name: "检验项列表" });
  expect(within(table).getAllByRole("columnheader")
    .map((header) => header.textContent)).toEqual([
    "序号",
    "检验项",
    "状态",
  ]);
  expect(within(table).getByRole("row", { name: /50/ })
    .querySelectorAll("[role='cell']")).toHaveLength(3);
});
```

在 `InspectionWorkbench.test.tsx` 新增：

```tsx
test("列表与当前项编辑器位于同一个双栏工作区", () => {
  render(
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[]}
      sources={[]}
      balloons={[]}
      items={[{
        item_id: "merged-item",
        item_type: "linear_dimension",
        raw_text: "50",
        nominal: "50",
        active: true,
      }]}
      onSave={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  const workspace = screen.getByRole("group", {
    name: "检验项列表与编辑",
  });
  expect(workspace.querySelector(".inspection-review-workspace__list"))
    .not.toBeNull();
  expect(workspace.querySelector(".inspection-review-workspace__detail"))
    .not.toBeNull();
  expect(within(workspace).getByRole("table", {
    name: "检验项列表",
  })).not.toBeNull();
  expect(within(workspace).getByRole("article", {
    name: "50",
  })).not.toBeNull();
  expect(document.querySelector(".candidate-editor")).toBeNull();
});
```

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL，因为 `compact` prop、合并工作区和三列表头不存在。

- [ ] **Step 3: Add compact rendering without duplicating list state**

在 `InspectionItemTableProps` 加入：

```tsx
compact?: boolean;
```

读取 prop 后设置 section class：

```tsx
<section
  className={[
    "inspection-table-section",
    compact ? "inspection-table-section--compact" : "",
  ].filter(Boolean).join(" ")}
  aria-label={zhCN.inspection.region}
>
```

head 中只在非 compact 时输出 value/page：

```tsx
<span role="columnheader">{zhCN.inspection.number}</span>
<span role="columnheader">{zhCN.inspection.item}</span>
{compact ? null : (
  <span role="columnheader">{zhCN.inspection.value}</span>
)}
{compact ? null : (
  <span role="columnheader">{zhCN.inspection.page}</span>
)}
<span role="columnheader">{zhCN.inspection.status}</span>
```

item row 的 value/page cells 改为：

```tsx
{compact ? null : (
  <span role="cell">
    <strong>{item.nominal ?? item.raw_text}</strong>
    <small>{tolerance(item)}</small>
  </span>
)}
{compact ? null : (
  <span role="cell">
    {pageNumber === undefined
      ? zhCN.workbench.unknown
      : zhCN.inspection.sourcePage(pageNumber)}
  </span>
)}
```

source row 的 value/page cells 改为：

```tsx
{compact ? null : (
  <span role="cell">{zhCN.workbench.unknown}</span>
)}
{compact ? null : (
  <span role="cell">
    {source.pageIndex === undefined
      ? zhCN.workbench.unknown
      : zhCN.inspection.sourcePage(source.pageIndex + 1)}
  </span>
)}
```

筛选、分页、selection、source editor 和 SIP detail state 不复制也不迁移。

- [ ] **Step 4: Compose one master-detail workspace**

在 `zhCN.workbench` 增加：

```tsx
mergedReviewWorkspace: "检验项列表与编辑",
```

在 `InspectionWorkbench` 中保留 `RecognitionSummary`，用以下结构替换独立
`SelectedInspectionItemSummary`、`InspectionItemTable` 和
`details.candidate-editor`：

```tsx
<div
  className="inspection-review-workspace"
  role="group"
  aria-label={zhCN.workbench.mergedReviewWorkspace}
>
  <div className="inspection-review-workspace__list">
    <InspectionItemTable
      items={items}
      balloons={balloons}
      pendingSources={pendingSources}
      candidateNumbers={candidateNumbers}
      filter={filter}
      selectedItemId={selectedItemId}
      selectedSourceId={selectedSourceId}
      disabled={saving || busy || reviewImmutable}
      compact
      onSelectItem={selectItem}
      onSelectSource={selectSource}
      onCommand={submitCommand}
      onDraftChange={setSipDraftDirty}
    />
  </div>
  <div className="inspection-review-workspace__detail">
    {selectedReviewItem === undefined ? null : (
      <SelectedInspectionItemSummary
        item={selectedReviewItem}
        balloon={selectedReviewBalloon}
        candidateNumber={candidateNumbers.get(selectedReviewItem.item_id)}
      />
    )}
    <ReviewPanel
      items={items}
      disabled={saving || busy || reviewImmutable}
      selectedItemId={selectedItemId}
      onSelectItem={selectItem}
      pageIndex={pageIndex}
      onCommand={submitCommand}
      onDraftChange={setReviewDraftDirty}
    />
  </div>
</div>
```

`BalloonToolbar` 保留在该 workspace 之后，不改变 command 或 Owner。

- [ ] **Step 5: Add fixed-height independent scrolling and responsive fallback**

在 `workbench.css` 加入：

```css
.workbench-layout {
  grid-template-columns:
    minmax(0, 1.6fr)
    minmax(560px, 1fr);
}

.inspection-pane {
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: calc(100vh - 248px);
  max-height: none;
  overflow: hidden;
}

.inspection-review-workspace {
  display: grid;
  grid-template-columns: minmax(190px, 0.78fr) minmax(330px, 1.22fr);
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--qi-border);
  border-radius: 7px;
  background: #ffffff;
}

.inspection-review-workspace__list,
.inspection-review-workspace__detail {
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

.inspection-review-workspace__list {
  padding: 8px;
  border-right: 1px solid var(--qi-border);
}

.inspection-review-workspace__detail {
  display: grid;
  gap: 8px;
  align-content: start;
  padding: 8px;
}

.inspection-table-section--compact .inspection-table__head,
.inspection-table-section--compact .inspection-table__row {
  grid-template-columns: 34px minmax(90px, 1fr) minmax(72px, 0.75fr);
}

.inspection-table-section--compact .inspection-table__body {
  max-height: none;
}

@media (max-width: 1240px) {
  .inspection-review-workspace {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(240px, 1fr) minmax(280px, 1fr);
  }

  .inspection-review-workspace__list {
    border-right: 0;
    border-bottom: 1px solid var(--qi-border);
  }
}

@media (max-width: 820px) {
  .inspection-pane {
    height: auto;
    overflow: visible;
  }

  .inspection-review-workspace {
    grid-template-rows: auto auto;
    height: auto;
  }

  .inspection-review-workspace__list,
  .inspection-review-workspace__detail {
    max-height: 520px;
  }
}
```

删除 `.candidate-editor` 的所有 selectors；保留 `.primary-action`，因为
`ExportPanel` 仍使用。

- [ ] **Step 6: Run GREEN, full frontend tests and build**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/FreezeReviewButton.test.tsx
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e:list
```

Expected: zero test failures，TypeScript/Vite build PASS，无新的 warning/error。

- [ ] **Step 7: Commit Task 4**

```bash
git add \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git diff --cached --check
git commit -m "style: merge inspection list and editor"
```

## Task 5: Verify Runtime Behavior And Review The Final Diff

**Files:**
- Read only: all Task 1～4 changed files
- No planned production edits

- [ ] **Step 1: Verify exact diff and protected files**

Run:

```bash
git status --short
git diff HEAD~4 -- \
  frontend/e2e/chinese-pdf-upload-mvp.spec.ts \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/FreezeReviewButton.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git diff --check HEAD~4..HEAD
```

Expected: 只有 allowed paths；protected dirty files 没有被本 task stage/commit。

- [ ] **Step 2: Run the focused contract and full frontend gate**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/FreezeReviewButton.test.tsx \
  src/features/review/saveWorkingCopy.test.ts
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e:list
```

Expected: zero failures；`P0-UI-006` 八类 command 与 `P0-UI-007`
version/operator/no-autosave core contract 保持，E2E helper 不再查找已移除按钮。

- [ ] **Step 3: Invoke `auto-feature-smoke-test` and verify runtime identity**

先确认当前 localhost runtime 是当前 source state：

```bash
docker compose ps frontend api
curl --fail --silent --show-error http://127.0.0.1:3000/ >/dev/null
git rev-parse HEAD
```

若 `127.0.0.1:3000` 不是当前 source runtime，检查 `docker compose ps` 和现有
source-mounted dev runtime；不得把旧 container 页面作为当前证据。runtime 不可用时
报告 `Chrome MCP smoke: blocked`，不得伪造 PASS。

- [ ] **Step 4: Run Chrome MCP at the production viewport**

使用 Chrome DevTools MCP 打开 `http://127.0.0.1:3000`，viewport
`1565 × 796`。复用现有 editing project，不强制重新上传 PDF。验证：

1. 页面不存在“保存审核修改”按钮；
2. “检验项列表”和当前项 editor 同时位于“检验项列表与编辑”工作区；
3. 左栏滚动时右栏位置不变，右栏滚动时左栏 selection 不变；
4. 切换无 dirty 项不改变页面纵向位置；
5. 默认字段只读，点击“修改”后可输入；
6. 输入变化不触发 network command；
7. 点击“修改保存”产生一次 `/review/commands`，成功后回到只读；
8. 点击“保留”或“排除”直接产生一次 command，无第二次 Save；
9. dirty edit 时点击另一行仍保留当前项并显示“请先修改保存当前检验项”；
10. console 没有本 change 导致的新 error。

保存一张包含左侧 list、右侧 editor 和 action rail 的当前截图。API verification
不适用，因为 backend contract 未改变；Chrome network entry 负责证明 command
request。

- [ ] **Step 5: Run an independent read-only reviewer**

Reviewer prompt 必须明确：

```text
Role: reviewer
Scope: Task 1-4 exact frontend diff and focused/runtime evidence
Authority: read-only
Boundaries: do not modify files, plans, status, commits, staging, runtime data
Nested delegation: do not spawn, request, or coordinate subagents
Rule conflicts: obey higher-priority rules; stop and report any conflict
Check:
- selected A layout and independent overflow are real
- no second candidate editor or top save remains
- explicit actions preserve REV-003 version/operator/no-autosave contract
- failed commands retain drafts and one in-flight command is enforced
- dirty selection cannot silently lose edits
- tests cover the real interaction instead of only labels/classes
Output:
- verdict: accept / accept with concerns / reject
- blocking issues
- non-blocking concerns
- exact file/test evidence
- recommended minimal follow-up
Verification: list commands inspected/run, or why not possible
```

Parent 必须直接复核 blocking claim，不能把 reviewer summary 当作已验证事实。

- [ ] **Step 6: Resolve only reproduced blockers with a new RED/GREEN cycle**

只在 reviewer 返回 `reject` 或 blocking concern 且父 agent 复现后执行：

- edit-state finding → 先加 failing case 到 `ReviewPanel.test.tsx`，再改
  `ReviewPanel.tsx`；
- direct-submit/selection finding → 先加 failing case 到
  `InspectionWorkbench.test.tsx`，再改 `InspectionWorkbench.tsx`；
- compact/source finding → 先加 failing case 到
  `InspectionItemTable.test.tsx`，再改 `InspectionItemTable.tsx`；
- visual-only finding → 在同 viewport 复现，只改 `workbench.css`。

运行单个新 test 观察 RED，最小修复后重跑 Step 2 和 Step 4。只 stage 对应
test/production pair，并提交：

```bash
# ReviewPanel finding
git add \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/components/review/ReviewPanel.tsx

# InspectionWorkbench finding
git add \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx

# InspectionItemTable finding
git add \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx

# Visual-only finding
git add frontend/src/styles/workbench.css

git diff --cached --check
git commit -m "fix: address merged review workspace finding"
```

只执行与 reproduced finding 匹配的一个 `git add` block，不把四个 block 一起执行。

- [ ] **Step 7: Invoke `superpowers:verification-before-completion`**

用 fresh command output 复核：

```bash
git status --short --branch
git log -5 --oneline
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
```

只有 full frontend tests、build、Chrome smoke 和 reviewer blocker closure 都有当前
证据时，才可以报告 implementation complete。final 必须分别报告：

- changed files/behavior；
- focused/full tests；
- build；
- API verification: not applicable；
- Chrome MCP smoke；
- reviewer verdict；
- protected dirty files 未处理；
- remaining risk/blocker。
