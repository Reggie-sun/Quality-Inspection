# Inspection Item Information Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除详情区内重复的检验项原文展示，并把“合并重复项”改为列表侧、可预览、可重试的显式批量流程。

**Architecture:** `InspectionWorkbench` 继续拥有 selected item、dirty guard 和唯一 `submitCommand()`；共享 presentation helper 统一生成编号、类型、页码和状态；`InspectionItemTable` 拥有 merge mode 与跨分页 selection；`MergeInspectionItemsPreview` 只拥有合并预览草稿；`ReviewPanel` 仅保留单项详情与 review draft。现有 `ReviewCommand`、API、working-copy aggregate 和后端 merge 语义保持不变。

**Tech Stack:** React 19、TypeScript 5.8、Vitest 3、Testing Library、Vite 6、Playwright、Chrome DevTools MCP

---

## Execution Boundary

- Selected lane: `Standard`。
- Single behavior owner: `InspectionWorkbench.submitCommand()` 仍是所有 review mutation 的唯一提交路径。
- Old path to retire:
  - `ReviewPanel.selectedIds`；
  - `ReviewPanel.toggleSelected()`；
  - `ReviewPanel.mergeSelected()`；
  - `.review-merge-selector` UI 与 CSS；
  - `SelectedInspectionItemSummary` 组件、调用点和样式。
- Unchanged contract:
  - `ReviewCommand` 中 `{ type: "merge"; item_ids: string[]; raw_text: string }` 不变；
  - `onSave(command): Promise<void>` 不变；
  - active/excluded、dirty draft、review lock、at-most-once submit 语义不变；
  - 列表 display number 仍优先使用 formal balloon number，其次使用现有 `candidateNumbers`。
- Focused verification:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
npm test -- --run \
  src/components/workbench/inspectionItemPresentation.test.ts \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/MergeInspectionItemsPreview.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

- Allowed implementation paths:
  - `frontend/src/components/workbench/inspectionItemPresentation.ts`
  - `frontend/src/components/workbench/inspectionItemPresentation.test.ts`
  - `frontend/src/components/workbench/MergeInspectionItemsPreview.tsx`
  - `frontend/src/components/workbench/MergeInspectionItemsPreview.test.tsx`
  - `frontend/src/components/workbench/InspectionItemTable.tsx`
  - `frontend/src/components/workbench/InspectionItemTable.test.tsx`
  - `frontend/src/components/workbench/InspectionWorkbench.tsx`
  - `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
  - `frontend/src/components/review/ReviewPanel.tsx`
  - `frontend/src/components/review/ReviewPanel.test.tsx`
  - `frontend/src/copy/zhCN.ts`
  - `frontend/src/styles/workbench.css`
- Do not edit backend files, API types, schema, e2e fixtures, export flow, PDF workspace, SIP metadata, balloon commands, or unrelated copy/styles.
- Before every commit, inspect `git status --short` and stage only the files listed in that task.

## Task 1: Centralize Detail Presentation Metadata

**Files:**

- Create: `frontend/src/components/workbench/inspectionItemPresentation.ts`
- Create: `frontend/src/components/workbench/inspectionItemPresentation.test.ts`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`

### Step 1: Write the failing presentation tests

- [ ] Add focused tests for type, status, page, and number precedence:

```ts
import { describe, expect, test } from "vitest";

import {
  inspectionItemPresentation,
  inspectionItemTypeLabel,
} from "./inspectionItemPresentation";

describe("inspectionItemPresentation", () => {
  test("正式气泡编号优先于候选编号", () => {
    expect(inspectionItemPresentation(
      {
        item_id: "item-1",
        item_type: "linear_dimension",
        raw_text: "48",
        page_index: 1,
        status: "kept",
        active: true,
      },
      {
        id: "balloon-1",
        itemId: "item-1",
        center: [20, 30],
        number: 9,
        status: "active",
      },
      2,
    )).toMatchObject({
      displayNumber: 9,
      numberKind: "formal",
      page: 2,
      status: "confirmed",
    });
  });

  test("无气泡时复用候选编号且未知类型使用安全占位", () => {
    expect(inspectionItemPresentation(
      { item_id: "item-2", raw_text: "85", active: true },
      undefined,
      4,
    )).toMatchObject({
      displayNumber: 4,
      numberKind: "candidate",
      typeLabel: "—",
    });
    expect(inspectionItemTypeLabel({
      item_id: "item-3",
      coarse_type: "future_type",
      raw_text: "X",
      active: true,
    })).toBe("—");
  });
});
```

- [ ] Run the test and confirm RED because the module does not exist:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
npm test -- --run src/components/workbench/inspectionItemPresentation.test.ts
```

Expected: FAIL with module resolution error.

### Step 2: Add the single presentation helper

- [ ] Move the current `typeLabel()`, `sourcePage()`, `itemStatus()` logic and their label maps from `InspectionItemTable.tsx` into the new helper.
- [ ] Export one stable view model:

```ts
export type InspectionItemPresentation = {
  displayNumber?: number;
  numberKind: "formal" | "candidate" | "empty";
  numberLabel: string;
  typeLabel: string;
  page?: number;
  pageLabel: string;
  status: ItemStatus;
  statusLabel: string;
};

export function inspectionItemPresentation(
  item: ReviewItem,
  balloon?: BalloonOverlay,
  candidateNumber?: number,
): InspectionItemPresentation {
  const displayNumber = balloon?.number ?? candidateNumber;
  const page = inspectionItemSourcePage(item, balloon);
  const status = inspectionItemStatus(item, balloon);
  const numberKind = balloon !== undefined
    ? "formal"
    : candidateNumber !== undefined
      ? "candidate"
      : "empty";

  return {
    displayNumber,
    numberKind,
    numberLabel: balloon !== undefined
      ? zhCN.inspection.formalNumber(balloon.number)
      : candidateNumber !== undefined
        ? zhCN.inspection.candidateNumber(candidateNumber)
        : zhCN.inspection.noNumber,
    typeLabel: inspectionItemTypeLabel(item),
    page,
    pageLabel: page === undefined
      ? zhCN.workbench.unknown
      : zhCN.inspection.sourcePage(page),
    status,
    statusLabel: INSPECTION_ITEM_STATUS_LABELS[status],
  };
}
```

- [ ] Replace local list calculations in `InspectionItemTable.tsx` with this helper. Keep collision text and source-only row behavior local to the table.
- [ ] Do not add a new numbering fallback based on array index.

### Step 3: Verify and commit

- [ ] Run:

```bash
npm test -- --run \
  src/components/workbench/inspectionItemPresentation.test.ts \
  src/components/workbench/InspectionItemTable.test.tsx
```

Expected: PASS.

- [ ] Commit only this task:

```bash
git add \
  frontend/src/components/workbench/inspectionItemPresentation.ts \
  frontend/src/components/workbench/inspectionItemPresentation.test.ts \
  frontend/src/components/workbench/InspectionItemTable.tsx
git commit -m "refactor: centralize inspection item presentation"
```

## Task 2: Replace Repeated Summary With One Detail Header

**Files:**

- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

### Step 1: Write RED tests for the approved hierarchy

- [ ] Replace the `SelectedInspectionItemSummary` tests with workbench/header assertions:

```ts
const detail = within(workspace).getByRole("article", {
  name: "检验项 9 · 螺纹",
});

expect(within(detail).getByRole("heading", {
  name: "检验项 9 · 螺纹",
})).not.toBeNull();
expect(within(detail).getByText("已确认")).not.toBeNull();
expect(within(detail).getByText("气泡 9")).not.toBeNull();
expect(within(detail).getByText("第 1 页")).not.toBeNull();
expect(within(workspace).queryByRole("region", {
  name: "所选检验项",
})).toBeNull();
```

- [ ] Add a `ReviewPanel.test.tsx` case proving the heading does not repeat `raw_text`:

```ts
render(
  <ReviewPanel
    items={[item]}
    onCommand={vi.fn()}
    selectedItemId={item.item_id}
    selectedItemPresentation={{
      displayNumber: 2,
      numberKind: "candidate",
      numberLabel: "候选序号 2",
      typeLabel: "线性尺寸",
      page: 1,
      pageLabel: "第 1 页",
      status: "pending",
      statusLabel: "待审核",
    }}
  />,
);

expect(screen.getByRole("heading", {
  name: "检验项 2 · 线性尺寸",
})).not.toBeNull();
expect(screen.queryByRole("heading", { name: "48" })).toBeNull();
expect(screen.getAllByDisplayValue("48")).toHaveLength(1);
```

- [ ] Run RED:

```bash
npm test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL because the new prop/header is absent and the old summary still renders.

### Step 2: Pass the selected presentation from the owner

- [ ] In `InspectionWorkbench.tsx`, derive metadata from the already selected item:

```ts
const selectedItemPresentation = selectedReviewItem === undefined
  ? undefined
  : inspectionItemPresentation(
      selectedReviewItem,
      selectedReviewBalloon,
      candidateNumbers.get(selectedReviewItem.item_id),
    );
```

- [ ] Pass `selectedItemPresentation` to `ReviewPanel`.
- [ ] Delete the `SelectedInspectionItemSummary` render block and import.
- [ ] Delete the `SelectedInspectionItemSummary` export, prop type, and tests from `InspectionItemTable`.

### Step 3: Render one identity header

- [ ] Add this prop without changing review command props:

```ts
type ReviewPanelProps = {
  // existing props
  selectedItemPresentation?: InspectionItemPresentation;
};
```

- [ ] Replace `<h3>{selectedItem.raw_text}</h3>` with a semantic header:

```tsx
<header className="review-selected-item__header">
  <div>
    <h3>
      {zhCN.review.itemHeading(
        selectedItemPresentation?.displayNumber,
        selectedItemPresentation?.typeLabel ?? zhCN.workbench.unknown,
      )}
    </h3>
    <p>
      <span>{selectedItemPresentation?.numberLabel}</span>
      <span>{selectedItemPresentation?.pageLabel}</span>
    </p>
  </div>
  <span className={`geometry-state geometry-state--${
    selectedItemPresentation?.status ?? "pending"
  }`}>
    {selectedItemPresentation?.statusLabel}
  </span>
</header>
```

- [ ] The article accessible name must use the new heading, not `raw_text`.
- [ ] Reuse `zhCN.workbench.unknown` for absent number/page; do not invent `0` or page 1.
- [ ] Remove `.selected-inspection-summary*` styles and convert the old `h3` header rules to `.review-selected-item__header`.

### Step 4: Verify and commit

- [ ] Run the three focused suites from Step 1.
- [ ] Confirm no old summary symbol remains:

```bash
rg -n "SelectedInspectionItemSummary|selected-inspection-summary" \
  frontend/src
```

Expected: no matches.

- [ ] Commit:

```bash
git add \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: clarify inspection item detail hierarchy"
```

## Task 3: Group Drawing Source and Parsed Result

**Files:**

- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

### Step 1: Add failing semantic-group tests

- [ ] Add assertions scoped by group:

```ts
const drawingSource = screen.getByRole("group", { name: "图纸原文" });
const parsedResult = screen.getByRole("group", { name: "解析结果" });

expect(within(drawingSource).getByRole("textbox", {
  name: "原始标注：48",
})).not.toBeNull();
expect(within(parsedResult).getByRole("textbox", {
  name: "基本尺寸：48",
})).not.toBeNull();
expect(within(parsedResult).getByRole("textbox", {
  name: "上公差：48",
})).not.toBeNull();
expect(within(drawingSource).queryByText("基本尺寸")).toBeNull();
```

- [ ] Cover a coarse/complex item so coordinates, coarse type, and confirmation stay in `图纸原文`.
- [ ] Run:

```bash
npm test -- --run src/components/review/ReviewPanel.test.tsx
```

Expected: FAIL because the current inputs are not grouped.

### Step 2: Introduce semantic fieldsets

- [ ] Add copy keys `drawingSource: "图纸原文"` and `parsedResult: "解析结果"`.
- [ ] Wrap raw text and complex source fields in:

```tsx
<fieldset className="review-field-group review-field-group--source">
  <legend>{zhCN.review.drawingSource}</legend>
  {/* raw_text and existing complex source fields */}
</fieldset>
```

- [ ] Wrap typed core fields in:

```tsx
<fieldset className="review-field-group review-field-group--parsed">
  <legend>{zhCN.review.parsedResult}</legend>
  {/* existing coreFieldsFor(selectedItem.item_type) */}
</fieldset>
```

- [ ] Preserve existing `aria-label`, disabled state, view/edit state, validation, field parsing, save action, and dirty signatures.
- [ ] Do not move split/add/manual-item commands into these groups.

### Step 3: Verify regressions and commit

- [ ] Run:

```bash
npm test -- --run src/components/review/ReviewPanel.test.tsx
```

Expected: all current view/edit, save failure, split, add, and draft synchronization tests PASS.

- [ ] Commit:

```bash
git add \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: group source and parsed inspection fields"
```

## Task 4: Build the Deterministic Merge Preview

**Files:**

- Create: `frontend/src/components/workbench/MergeInspectionItemsPreview.tsx`
- Create: `frontend/src/components/workbench/MergeInspectionItemsPreview.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

### Step 1: Write RED tests for preview suggestion and draft ownership

- [ ] Test the exact deterministic rule:

```ts
expect(suggestMergedRawText([" 48 ", "48"])).toBe("48");
expect(suggestMergedRawText(["⌀10", " ±0.1 "])).toBe("⌀10 ±0.1");
expect(suggestMergedRawText(["A", "", "A", "B"])).toBe("A B");
```

- [ ] Render the component and test:
  - all source values are visible;
  - default merged raw text is editable;
  - `返回修改` does not submit;
  - `确认合并 2 项` submits the current draft once;
  - `submitting` disables duplicate confirmation;
  - focus moves to the preview heading on mount.

- [ ] Run:

```bash
npm test -- --run \
  src/components/workbench/MergeInspectionItemsPreview.test.tsx
```

Expected: FAIL because the component does not exist.

### Step 2: Implement a presentation-only preview

- [ ] Use this boundary:

```ts
type MergeInspectionItemsPreviewProps = {
  items: ReviewItem[];
  draftRawText: string;
  submitting: boolean;
  onDraftRawTextChange: (value: string) => void;
  onBack: () => void;
  onCancel: () => void;
  onConfirm: () => void;
};
```

- [ ] Export this pure function from the same file:

```ts
export function suggestMergedRawText(rawTexts: string[]): string {
  return [...new Set(rawTexts.map((value) => value.trim()).filter(Boolean))]
    .join(" ");
}
```

- [ ] Render:
  - heading `合并预览` with `tabIndex={-1}` and a ref;
  - source item list;
  - editable `合并后的原始标注`;
  - existing type labels for context only, without adding an `item_type` field to the command;
  - explanatory text `合并不是数值相加`;
  - `返回修改`, `取消`, and `确认合并 N 项`.
- [ ] Keep API submission outside this component.

### Step 3: Verify and commit

- [ ] Run the preview suite and `npm run build`.
- [ ] Commit:

```bash
git add \
  frontend/src/components/workbench/MergeInspectionItemsPreview.tsx \
  frontend/src/components/workbench/MergeInspectionItemsPreview.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: add inspection merge preview"
```

## Task 5: Move Merge Selection Into the List

**Files:**

- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

### Step 1: Write RED list-mode tests

- [ ] Add tests covering:
  - default mode has no merge checkboxes;
  - `合并重复项` calls `onBeginMerge()` and enters selection mode only when it returns `true`;
  - only active item rows have checkboxes;
  - fewer than two items keeps `下一步` disabled;
  - selection remains after changing to page 2 and back;
  - search/filter changes do not delete already selected IDs;
  - Escape and `取消` exit mode and clear selection;
  - `下一步` opens preview with the deterministic default;
  - `返回修改` keeps selection;
  - explicit failure retains selection and edited preview;
  - success clears mode, selection, and preview;
  - each confirm click calls `onMergeItems(itemIds, rawText)` once.

- [ ] Use more than `PAGE_SIZE` active items for the cross-page case:

```ts
const items = Array.from({ length: 51 }, (_, index) => ({
  item_id: `item-${index + 1}`,
  item_type: "linear_dimension" as const,
  raw_text: `检验项 ${index + 1}`,
  active: true,
}));
```

- [ ] Run:

```bash
npm test -- --run \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/review/ReviewPanel.test.tsx
```

Expected: FAIL because the table has no merge props/mode and `ReviewPanel` still renders the old selector.

### Step 2: Add explicit list-owned merge state

- [ ] Extend only the table boundary:

```ts
type InspectionItemTableProps = {
  // existing props
  onBeginMerge?: () => boolean;
  onMergeItems?: (
    itemIds: string[],
    rawText: string,
  ) => Promise<boolean>;
};

type MergeStep = "idle" | "select" | "preview";
```

- [ ] Store selection by `item_id`, not row index:

```ts
const [mergeStep, setMergeStep] = useState<MergeStep>("idle");
const [mergeItemIds, setMergeItemIds] = useState<string[]>([]);
const [mergedRawText, setMergedRawText] = useState("");
const [mergeSubmitting, setMergeSubmitting] = useState(false);
```

- [ ] When entering merge mode:

```ts
if (onBeginMerge?.() === false) return;
setMergeStep("select");
setMergeItemIds([]);
```

- [ ] Derive selected items from the full `items` prop, preserving item order and excluding inactive items:

```ts
const mergeItems = items.filter(
  (item) => item.active && mergeItemIds.includes(item.item_id),
);
```

- [ ] Do not clear `mergeItemIds` in filter/page effects.
- [ ] Checkboxes must stop row click propagation and use accessible names containing display number, raw text, and type.
- [ ] On `下一步`, set `mergedRawText(suggestMergedRawText(...))`, then render `MergeInspectionItemsPreview`.
- [ ] On confirm:

```ts
if (mergeSubmitting || mergeItems.length < 2 || mergedRawText.trim() === "") {
  return;
}
setMergeSubmitting(true);
try {
  const succeeded = await onMergeItems?.(
    mergeItems.map((item) => item.item_id),
    mergedRawText.trim(),
  );
  if (succeeded === true) resetMergeMode();
} finally {
  setMergeSubmitting(false);
}
```

- [ ] On failure, do not change `mergeStep`, `mergeItemIds`, or `mergedRawText`.

### Step 3: Retire the old detail-owned merge path

- [ ] Delete from `ReviewPanel.tsx`:
  - `selectedIds`;
  - `activeItems` usage that exists only for merge selection;
  - `toggleSelected`;
  - `mergeSelected`;
  - `<details className="review-merge-selector">`.
- [ ] Keep `activeItems` if still needed by draft synchronization; do not delete shared behavior accidentally.
- [ ] Move the existing eight-command contract assertion so merge is triggered through `InspectionWorkbench`/`InspectionItemTable`, while `ReviewPanel.test.tsx` continues to cover the seven commands it still owns.
- [ ] Delete `.review-merge-selector*` CSS.

### Step 4: Verify and commit

- [ ] Run:

```bash
npm test -- --run \
  src/components/workbench/MergeInspectionItemsPreview.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/review/ReviewPanel.test.tsx
```

- [ ] Confirm the retired symbols are gone:

```bash
rg -n "review-merge-selector|mergeSelected|toggleSelected|selectedIds" \
  frontend/src/components/review \
  frontend/src/styles/workbench.css
```

Expected: no matches.

- [ ] Commit:

```bash
git add \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: move merge flow into inspection list"
```

## Task 6: Connect Dirty Guard, Submit, and Merged-Item Selection

**Files:**

- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`

### Step 1: Write RED orchestration tests

- [ ] Add a dirty-guard case:
  1. select an item;
  2. enter edit mode and change `raw_text`;
  3. click `合并重复项`;
  4. assert merge checkboxes do not render;
  5. assert save status is `请先修改保存当前检验项`;
  6. assert the review draft remains unchanged.

- [ ] Add at-most-once coverage with a deferred `onSave`:

```ts
fireEvent.click(confirmMerge);
fireEvent.click(confirmMerge);
expect(onSave).toHaveBeenCalledTimes(1);
expect(onSave).toHaveBeenCalledWith({
  type: "merge",
  item_ids: ["item-1", "item-2"],
  raw_text: "⌀10 ±0.1",
});
```

- [ ] Add success reconciliation:
  - initial active IDs are `item-1`, `item-2`;
  - `onSave` causes rerender with both inactive plus one new active `merged-1`;
  - after resolve, `merged-1` is selected and its detail heading is visible.
- [ ] Add safe fallback:
  - refresh exposes zero or two new active IDs;
  - merge mode exits after command success;
  - no guessed item is selected.
- [ ] Add failure/retry:
  - first `onSave` rejects;
  - preview draft and item selection remain;
  - retry submits the same command once more;
  - save status reflects failure before retry.

- [ ] Run:

```bash
npm test -- --run src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL because the workbench does not expose merge orchestration.

### Step 2: Add the one workbench merge handler

- [ ] Keep a current items snapshot without introducing another submit path:

```ts
const latestItemsRef = useRef(items);
latestItemsRef.current = items;
```

- [ ] Add the dirty entry guard:

```ts
const beginMerge = (): boolean => {
  if (reviewDraftDirty) {
    setSelectionBlocked(true);
    return false;
  }
  setSelectionBlocked(false);
  return true;
};
```

- [ ] Add the submit adapter:

```ts
const mergeItems = async (
  itemIds: string[],
  rawText: string,
): Promise<boolean> => {
  const activeIdsBefore = new Set(
    latestItemsRef.current
      .filter((item) => item.active)
      .map((item) => item.item_id),
  );
  const succeeded = await submitCommand({
    type: "merge",
    item_ids: itemIds,
    raw_text: rawText,
  });
  if (!succeeded) return false;

  const newActiveItems = latestItemsRef.current.filter(
    (item) => item.active && !activeIdsBefore.has(item.item_id),
  );
  if (newActiveItems.length === 1) {
    selectItem(newActiveItems[0].item_id);
  } else if (selectedItemId !== undefined) {
    const selectionStillActive = latestItemsRef.current.some(
      (item) => item.active && item.item_id === selectedItemId,
    );
    if (!selectionStillActive) setSelectedItemId(undefined);
  }
  return true;
};
```

- [ ] Pass `onBeginMerge={beginMerge}` and `onMergeItems={mergeItems}` to `InspectionItemTable`.
- [ ] Continue passing `onCommand={submitCommand}` for SIP/source actions.
- [ ] Do not identify the new item by array position, raw-text equality, or assumed backend ID.

### Step 3: Verify and commit

- [ ] Run:

```bash
npm test -- --run \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx
```

Expected: PASS, including failure retry and at-most-once tests.

- [ ] Commit:

```bash
git add \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx
git commit -m "feat: orchestrate inspection item merge"
```

## Task 7: Finish Responsive and Accessibility Behavior

**Files:**

- Modify: `frontend/src/components/workbench/MergeInspectionItemsPreview.tsx`
- Modify: `frontend/src/components/workbench/MergeInspectionItemsPreview.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/styles/workbench.css`

### Step 1: Add focused accessibility assertions

- [ ] Assert:
  - selected-count text has `role="status"`;
  - count changes are visible without color;
  - checkbox names contain number, `raw_text`, and type;
  - preview heading receives focus;
  - Escape cancels selection mode but does not call a command;
  - header, `图纸原文`, and `解析结果` form a valid heading/group hierarchy;
  - all action buttons keep explicit accessible names.

- [ ] Run the three component suites and confirm RED for missing details.

### Step 2: Apply minimal layout CSS

- [ ] Keep `.inspection-review-workspace` as the existing fixed-height two-column grid.
- [ ] Keep list and detail as independent internal scroll containers.
- [ ] Style only these new classes:
  - `.inspection-list-merge-toolbar`;
  - `.inspection-list-merge-status`;
  - `.inspection-merge-row-checkbox`;
  - `.merge-inspection-preview`;
  - `.merge-inspection-preview__sources`;
  - `.review-selected-item__header`;
  - `.review-field-group`.
- [ ] At `max-width: 820px`, preserve the existing stacked workspace behavior.
- [ ] At `max-width: 620px`, stack preview actions and detail metadata without horizontal overflow.
- [ ] Use existing CSS variables and button patterns; do not introduce a second palette.

### Step 3: Run focused verification and commit

- [ ] Run:

```bash
npm test -- --run \
  src/components/workbench/MergeInspectionItemsPreview.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/review/ReviewPanel.test.tsx
npm run build
```

- [ ] Commit:

```bash
git add \
  frontend/src/components/workbench/MergeInspectionItemsPreview.tsx \
  frontend/src/components/workbench/MergeInspectionItemsPreview.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/styles/workbench.css
git commit -m "fix: finish merge accessibility and layout"
```

## Task 8: Full Verification, Browser Smoke, and Independent Review

**Files:**

- Verify only; no planned production file changes.

### Step 1: Run the complete automated checks

- [ ] Run focused suites:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
npm test -- --run \
  src/components/workbench/inspectionItemPresentation.test.ts \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/MergeInspectionItemsPreview.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

- [ ] Run the full frontend suite:

```bash
npm test -- --run
```

- [ ] Run production build:

```bash
npm run build
```

- [ ] Confirm Playwright discovery remains valid:

```bash
npm run e2e:list
```

Expected: all commands exit `0`.

### Step 2: Run Chrome smoke at the approved viewport

- [ ] Start the existing frontend/backend runtime using only repository-proven commands and environment values. Do not invent accounts, ports, or credentials.
- [ ] Set viewport to `1565×796`.
- [ ] Verify:
  1. list and detail remain in one bounded work area;
  2. right detail shows `检验项 {number} · {type}` and exactly one editable `raw_text`;
  3. status, balloon/candidate number, and real page remain visible;
  4. dirty edit blocks entering merge mode without clearing the draft;
  5. merge selection survives filter and pagination changes;
  6. `48 + 48` previews `48`;
  7. `⌀10 + ±0.1` previews `⌀10 ±0.1`;
  8. cancel, back, failure retry, and success paths match the specification;
  9. keyboard focus reaches toolbar, checkboxes, preview, back, cancel, and confirm;
  10. browser console has no new error or warning.
- [ ] Capture screenshots for normal detail, merge selection, and merge preview in the current task evidence location if the runtime/harness already provides one. Do not create a new evidence convention.

### Step 3: Obtain independent read-only review

- [ ] Use one `reviewer` agent after all behavior changes are complete.
- [ ] Reviewer scope:
  - the changed frontend files in this plan;
  - approved design spec;
  - final diff and focused/full test output.
- [ ] Reviewer must check:
  - the three-value duplication is actually removed;
  - `ReviewPanel` no longer owns merge;
  - no alternate command submit path exists;
  - dirty guard and at-most-once behavior are preserved;
  - merge failure retains state;
  - success selection uses unique active-ID delta only;
  - no API/schema/backend behavior changed;
  - responsive/accessibility behavior matches the approved design.
- [ ] Parent verifies every blocking claim directly before changing code.

### Step 4: Final diff and repository-state audit

- [ ] Run:

```bash
git status --short
git diff --check
git diff 70c0bc1 -- \
  frontend/src/components/workbench \
  frontend/src/components/review \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
```

- [ ] Confirm unrelated pre-existing dirty files remain untouched and unstaged.
- [ ] Confirm no implementation artifact contains placeholders:

```bash
rg -n "TODO|TBD|FIXME|PLACEHOLDER|later|not implemented" \
  frontend/src/components/workbench/inspectionItemPresentation.ts \
  frontend/src/components/workbench/MergeInspectionItemsPreview.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/review/ReviewPanel.tsx
```

Expected: no new placeholder matches.
- [ ] If reviewer fixes were required, rerun the focused tests, full suite, build, and relevant Chrome smoke before the final delivery.

## Completion Contract

The feature is complete only when:

- The old summary and detail-owned merge selector are absent from source and DOM.
- The right-side `raw_text` appears only as the editable `图纸原文` field.
- The detail heading uses existing display number plus item type, never an array index.
- Merge selection is list-owned, active-only, cross-page, cancelable, previewed, and retryable.
- The merge command still uses the existing `ReviewCommand` shape and unique submit path.
- Dirty drafts block merge entry, a pending command cannot double-submit, failure retains state, and success does not guess a new item ID.
- Focused tests, full frontend tests, production build, `e2e:list`, Chrome smoke, and independent review all complete with recorded results.
- Only task-related files are committed; unrelated working-tree changes remain preserved.
