# Unified SIP Information Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目级 `SIP基本信息` 与当前检验项 SIP 字段收敛为右侧详情区中的唯一 `SIP 信息` 面板，同时保持现有 command、draft、freeze 和 export 语义。

**Architecture:** `InspectionWorkbench` 继续拥有 selected item、项目 metadata draft、dirty 汇总和唯一 `submitCommand()`；新建 `SelectedSipDetailFields` 按 `item_id` 持有单项 SIP draft，新建 `SipInformationPanel` 只组合项目与单项 SIP 呈现。`InspectionItemTable` 退役内嵌 SIP 表单，只保留列表与 source review draft；左侧辅助浮层只保留 export 与公司记录。

**Tech Stack:** React 19、TypeScript 5.8、Vitest 3、Testing Library、Vite 6、Playwright、Chrome DevTools MCP

---

## Execution Boundary

- Selected lane: `Standard`。
- Selected plan: `docs/superpowers/plans/2026-07-27-unified-sip-information-panel.md`。
- Selection evidence: 用户提供当前工作台截图，要求两个 SIP 区域合并，选择并批准方案 B，
  随后批准
  `docs/superpowers/specs/2026-07-27-unified-sip-information-panel-design.md`。
- Validation action: `amend` frontend information hierarchy。
- Single behavior owner: `InspectionWorkbench.submitCommand()` 继续是
  `set_sip_metadata` 与 `set_sip_detail_fields` 的唯一提交入口。
- Old path to retire:
  - `InspectionWorkbench.auxiliaryPanel` 中的 `.sip-metadata-card`；
  - `InspectionItemTable` 中的 `DetailDraft`、`detailDraft()`、`dirtyItemIds` 与
    `.sip-detail-fields`；
  - `展开 SIP 与导出信息` / `收起 SIP 与导出信息` 旧文案。
- Unchanged contract:
  - `ReviewCommand`、`onSave(command)`、review command API 不变；
  - metadata 与 per-item SIP 仍是两个独立 command；
  - freeze、reviewed、saving、export 与 three-artifact 语义不变；
  - selected SIP draft 继续按 `item_id` 保留，保存失败不清除；
  - auxiliary panel 继续常驻 DOM，只通过 `hidden` 收起。
- Writer ownership and order: 同一 frontend file group 同时只允许一个 writer；完成
  production behavior 后安排一个独立只读 reviewer。
- Next verification:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
micromamba run -n qi-p0 npm test -- --run \
  src/components/workbench/SelectedSipDetailFields.test.tsx \
  src/components/workbench/SipInformationPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/ExportPanel.test.tsx
```

## Allowed Paths

- Create:
  - `frontend/src/components/workbench/SelectedSipDetailFields.tsx`
  - `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
  - `frontend/src/components/workbench/SipInformationPanel.tsx`
  - `frontend/src/components/workbench/SipInformationPanel.test.tsx`
- Modify:
  - `frontend/src/components/workbench/InspectionItemTable.tsx`
  - `frontend/src/components/workbench/InspectionItemTable.test.tsx`
  - `frontend/src/components/workbench/InspectionWorkbench.tsx`
  - `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
  - `frontend/src/components/pdf/PdfWorkspace.test.tsx`
  - `frontend/src/copy/zhCN.ts`
  - `frontend/src/styles/workbench.css`
  - `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`
- Do not modify backend files、API types、schema、export implementation、PDF rendering、
  review form、balloon commands、Harness 或无关 copy/styles。
- 执行前运行 `git status --short --branch`。保留当前两个无关 `__pycache__` 修改和
  `.superpowers/brainstorm/` 本地文件，不 stage、不删除、不覆盖。
- 每次 commit 前运行 `git status --short`，并只 stage 当前 Task 的 `Files`
  列表中明确列出的文件。

## File Responsibilities

- `SelectedSipDetailFields.tsx`: 单个 active inspection item 的 SIP detail draft、
  validation、确认、失败重试与取消。
- `SipInformationPanel.tsx`: 项目 SIP 摘要/editor 与
  `SelectedSipDetailFields` 的唯一组合面板；不直接调用 API。
- `InspectionItemTable.tsx`: 列表、筛选、分页、merge mode、pending source draft。
- `InspectionWorkbench.tsx`: selected item、metadata draft、四类 dirty state、
  command serialization、SIP panel placement。
- `PdfWorkspace.tsx`: 不修改；继续拥有 auxiliary panel toggle 和 mounted state。
- `workbench.css`: 唯一 SIP panel 的层级、间距与 responsive layout。

## Task 1: Extract Selected SIP Detail Draft Without Moving It

**Files:**

- Create: `frontend/src/components/workbench/SelectedSipDetailFields.tsx`
- Create: `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`

- [ ] **Step 1: Write RED tests for the extracted component**

创建 `SelectedSipDetailFields.test.tsx`，覆盖 payload、按 item 保存 draft、失败保留和
取消恢复：

```tsx
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { ReviewItem } from "../../api/types";
import { SelectedSipDetailFields } from "./SelectedSipDetailFields";

afterEach(cleanup);

const firstItem: ReviewItem = {
  item_id: "item-1",
  raw_text: "M6",
  item_type: "thread",
  inspection_item: "螺纹检验",
  inspection_standard: "GB/T 197",
  inspection_method: "螺纹规",
  key_dimension: "是",
  inspection_role: "检验员",
  source_page: 1,
  remarks: "原始备注",
  active: true,
};

test("提交既有 set_sip_detail_fields command 并在成功后清除 dirty", async () => {
  const onCommand = vi.fn().mockResolvedValue(true);
  const onDraftChange = vi.fn();
  render(
    <SelectedSipDetailFields
      item={firstItem}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", {
    name: "备注（可选）：M6",
  }), { target: { value: "首件需复核" } });
  expect(onDraftChange).toHaveBeenLastCalledWith(true);

  fireEvent.click(screen.getByRole("button", {
    name: "确认当前检验项 SIP",
  }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledWith({
    type: "set_sip_detail_fields",
    item_id: "item-1",
    inspection_item: "螺纹检验",
    inspection_standard: "GB/T 197",
    inspection_method: "螺纹规",
    key_dimension: "是",
    inspection_role: "检验员",
    source_page: 1,
    remarks: "首件需复核",
  }));
  expect(onDraftChange).toHaveBeenLastCalledWith(false);
});

test("切换 item 后返回仍保留失败的 draft", async () => {
  const onCommand = vi.fn().mockResolvedValue(false);
  const { rerender } = render(
    <SelectedSipDetailFields item={firstItem} onCommand={onCommand} />,
  );
  fireEvent.change(screen.getByRole("textbox", {
    name: "检验方法：M6",
  }), { target: { value: "三针法复核" } });
  fireEvent.click(screen.getByRole("button", {
    name: "确认当前检验项 SIP",
  }));
  await waitFor(() => expect(onCommand).toHaveBeenCalledOnce());

  const secondItem: ReviewItem = {
    ...firstItem,
    item_id: "item-2",
    raw_text: "M8",
  };
  rerender(
    <SelectedSipDetailFields item={secondItem} onCommand={onCommand} />,
  );
  rerender(
    <SelectedSipDetailFields item={firstItem} onCommand={onCommand} />,
  );
  expect((screen.getByRole("textbox", {
    name: "检验方法：M6",
  }) as HTMLInputElement).value).toBe("三针法复核");
});

test("取消恢复当前 working-copy baseline 且不提交 command", () => {
  const onCommand = vi.fn();
  render(
    <SelectedSipDetailFields item={firstItem} onCommand={onCommand} />,
  );
  const remarks = screen.getByRole("textbox", {
    name: "备注（可选）：M6",
  }) as HTMLTextAreaElement;
  fireEvent.change(remarks, { target: { value: "临时修改" } });
  fireEvent.click(screen.getByRole("button", {
    name: "取消当前检验项 SIP 修改",
  }));
  expect(remarks.value).toBe("原始备注");
  expect(onCommand).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the new test and confirm RED**

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
micromamba run -n qi-p0 npm test -- --run src/components/workbench/SelectedSipDetailFields.test.tsx
```

Expected: FAIL，提示 `SelectedSipDetailFields` module 不存在。

- [ ] **Step 3: Implement `SelectedSipDetailFields` with the existing contract**

创建组件，移动现有 `DetailDraft`、`detailDraft()`、per-item draft state 和 fieldset。
公开接口固定为：

```tsx
import { useEffect, useState } from "react";

import type {
  BalloonOverlay,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import { inspectionItemPresentation } from "./inspectionItemPresentation";

type SelectedSipDetailFieldsProps = {
  item?: ReviewItem;
  balloon?: BalloonOverlay;
  disabled?: boolean;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onDraftChange?: (dirty: boolean) => void;
};

type DetailDraft = {
  inspectionItem: string;
  inspectionStandard: string;
  inspectionMethod: string;
  keyDimension: string;
  inspectionRole: string;
  sourcePage: string;
  remarks: string;
};

function detailDraft(
  item?: ReviewItem,
  balloon?: BalloonOverlay,
): DetailDraft {
  return {
    inspectionItem: item?.inspection_item ?? "",
    inspectionStandard: item?.inspection_standard ?? "",
    inspectionMethod: item?.inspection_method ?? "",
    keyDimension: item?.key_dimension ?? "",
    inspectionRole: item?.inspection_role ?? "",
    sourcePage: item === undefined
      ? ""
      : inspectionItemPresentation(item, balloon).page?.toString() ?? "",
    remarks: item?.remarks ?? "",
  };
}

export function SelectedSipDetailFields({
  item,
  balloon,
  disabled = false,
  onCommand,
  onDraftChange,
}: SelectedSipDetailFieldsProps) {
  const baseline = detailDraft(item, balloon);
  const [drafts, setDrafts] = useState<Record<string, DetailDraft>>({});
  const [dirtyItemIds, setDirtyItemIds] = useState<string[]>([]);
  const draft = item === undefined
    ? baseline
    : drafts[item.item_id] ?? baseline;

  useEffect(() => {
    if (item === undefined || dirtyItemIds.includes(item.item_id)) return;
    setDrafts((current) => ({
      ...current,
      [item.item_id]: detailDraft(item, balloon),
    }));
  }, [balloon, item]);

  useEffect(() => {
    onDraftChange?.(dirtyItemIds.length > 0);
  }, [dirtyItemIds, onDraftChange]);

  if (item === undefined || !item.active) return null;

  const updateDraft = (change: Partial<DetailDraft>) => {
    setDrafts((current) => ({
      ...current,
      [item.item_id]: {
        ...(current[item.item_id] ?? baseline),
        ...change,
      },
    }));
    setDirtyItemIds((current) =>
      current.includes(item.item_id) ? current : [...current, item.item_id],
    );
  };
  const clearDirty = () => {
    setDirtyItemIds((current) =>
      current.filter((candidate) => candidate !== item.item_id),
    );
  };
  const restoreBaseline = () => {
    setDrafts((current) => ({
      ...current,
      [item.item_id]: detailDraft(item, balloon),
    }));
    clearDirty();
  };

  return (
    <fieldset className="sip-detail-fields" disabled={disabled}>
      <legend>{zhCN.inspection.selectedSip}</legend>
      {([
        ["inspectionItem", zhCN.inspection.inspectionItem],
        ["inspectionStandard", zhCN.inspection.standard],
        ["inspectionMethod", zhCN.inspection.method],
        ["keyDimension", zhCN.inspection.keyDimension],
        ["inspectionRole", zhCN.inspection.role],
      ] as const).map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            aria-label={`${label}：${item.raw_text}`}
            value={draft[key]}
            onChange={(event) => updateDraft({ [key]: event.target.value })}
          />
        </label>
      ))}
      <label>
        {zhCN.inspection.page}
        <input
          aria-label={`${zhCN.inspection.page}：${item.raw_text}`}
          type="number"
          min={1}
          value={draft.sourcePage}
          onChange={(event) => updateDraft({ sourcePage: event.target.value })}
        />
      </label>
      <label>
        {zhCN.inspection.remarks}
        <textarea
          aria-label={`${zhCN.inspection.remarks}：${item.raw_text}`}
          maxLength={2000}
          rows={3}
          value={draft.remarks}
          onChange={(event) => updateDraft({ remarks: event.target.value })}
        />
      </label>
      <div className="sip-detail-actions">
        <button
          type="button"
          disabled={disabled || [
            draft.inspectionItem,
            draft.inspectionStandard,
            draft.inspectionMethod,
            draft.keyDimension,
            draft.inspectionRole,
            draft.sourcePage,
          ].some((value) => value.trim() === "")}
          onClick={async () => {
            const succeeded = (await onCommand({
              type: "set_sip_detail_fields",
              item_id: item.item_id,
              inspection_item: draft.inspectionItem,
              inspection_standard: draft.inspectionStandard,
              inspection_method: draft.inspectionMethod,
              key_dimension: draft.keyDimension,
              inspection_role: draft.inspectionRole,
              source_page: Number(draft.sourcePage),
              remarks: draft.remarks,
            })) !== false;
            if (succeeded) clearDirty();
          }}
        >
          {zhCN.inspection.confirmSip}
        </button>
        <button type="button" disabled={disabled} onClick={restoreBaseline}>
          {zhCN.inspection.cancelSip}
        </button>
      </div>
    </fieldset>
  );
}
```

同时在 `zhCN.ts` 更新这三个文案：

```ts
selectedSip: "SIP 确认字段",
confirmSip: "确认当前检验项 SIP",
cancelSip: "取消当前检验项 SIP 修改",
```

- [ ] **Step 4: Replace the inline fieldset without changing placement**

在 `InspectionItemTable.tsx`：

- 删除 `DetailDraft`、`detailDraft()`、`drafts`、`dirtyItemIds`、
  `updateDraft()`、`clearSelectedDraft()` 和原 inline fieldset；
- 保留 `SourceDraft`、source draft state 和 source command；
- 增加本地 `selectedSipDraftDirty`，让 table 的现有 dirty callback 仍聚合两类 draft：

```tsx
import { SelectedSipDetailFields } from "./SelectedSipDetailFields";

const [selectedSipDraftDirty, setSelectedSipDraftDirty] = useState(false);

useEffect(() => {
  onDraftChange?.(selectedSipDraftDirty || dirtySourceIds.length > 0);
}, [dirtySourceIds, onDraftChange, selectedSipDraftDirty]);
```

在原 fieldset 位置始终挂载组件；选中 source 时只把当前 item 设为空，不能条件卸载
组件，否则其按 `item_id` 保存的 draft 会丢失：

```tsx
<SelectedSipDetailFields
  item={selectedSource === undefined ? selected : undefined}
  balloon={selectedSource === undefined ? selectedBalloon : undefined}
  disabled={disabled}
  onCommand={async (command) =>
    commandSucceeded(onCommand, command)
  }
  onDraftChange={setSelectedSipDraftDirty}
/>
```

把 `InspectionItemTable.test.tsx` 中三条 selected SIP 行为测试移动到新 test 文件；
保留一条退役边界测试：

```tsx
expect(screen.getByRole("group", { name: "SIP 确认字段" })).not.toBeNull();
```

- [ ] **Step 5: Run focused tests**

```bash
micromamba run -n qi-p0 npm test -- --run \
  src/components/workbench/SelectedSipDetailFields.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx
```

Expected: PASS。

- [ ] **Step 6: Commit the behavior-preserving extraction**

```bash
git add \
  frontend/src/components/workbench/SelectedSipDetailFields.tsx \
  frontend/src/components/workbench/SelectedSipDetailFields.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/copy/zhCN.ts
git commit -m "refactor: extract selected SIP detail fields"
```

## Task 2: Build The Unified SIP Information Panel

**Files:**

- Create: `frontend/src/components/workbench/SipInformationPanel.tsx`
- Create: `frontend/src/components/workbench/SipInformationPanel.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

- [ ] **Step 1: Write RED composition tests**

创建 `SipInformationPanel.test.tsx`：

```tsx
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { SipInformationPanel } from "./SipInformationPanel";

afterEach(cleanup);

const metadata = {
  material_code: "",
  material_name: "上座",
  drawing_number: "JS26032501",
  material: "SUS304",
  revision: "A1",
};

test("在唯一 SIP 区域区分项目基本信息和当前检验项", () => {
  render(
    <SipInformationPanel
      metadata={metadata}
      metadataValues={[
        ["产品名称", "上座"],
        ["图号", "JS26032501"],
      ]}
      metadataDirty={false}
      disabled={false}
      selectedItem={{
        item_id: "item-1",
        raw_text: "M6",
        item_type: "thread",
        active: true,
      }}
      onMetadataChange={vi.fn()}
      onConfirmMetadata={vi.fn()}
      onCancelMetadata={vi.fn()}
      onCommand={vi.fn()}
    />,
  );

  const panel = screen.getByRole("region", { name: "SIP 信息" });
  expect(within(panel).getByRole("heading", {
    name: "项目基本信息",
  })).not.toBeNull();
  expect(within(panel).getByRole("heading", {
    name: "当前检验项",
  })).not.toBeNull();
  expect(within(panel).getByRole("group", {
    name: "SIP 确认字段",
  })).not.toBeNull();
  expect(panel.textContent).toContain("产品名称上座");
});

test("选中待判定来源时保留项目信息并显示当前项空状态", () => {
  render(
    <SipInformationPanel
      metadata={metadata}
      metadataValues={[["产品名称", "上座"]]}
      metadataDirty={false}
      disabled={false}
      selectedSourceActive
      onMetadataChange={vi.fn()}
      onConfirmMetadata={vi.fn()}
      onCancelMetadata={vi.fn()}
      onCommand={vi.fn()}
    />,
  );
  expect(screen.getByRole("region", { name: "SIP 信息" })).not.toBeNull();
  expect(screen.getByText("当前选择的是待判定来源。")).not.toBeNull();
  expect(screen.queryByRole("group", { name: "SIP 确认字段" })).toBeNull();
});

test("项目 metadata editor 使用父级 callback 且保持 command-required validation", () => {
  const onMetadataChange = vi.fn();
  const onConfirmMetadata = vi.fn();
  const props = {
    metadataValues: [["产品名称", "上座"]] as Array<
      readonly [string, string]
    >,
    metadataDirty: true,
    disabled: false,
    onMetadataChange,
    onConfirmMetadata,
    onCancelMetadata: vi.fn(),
    onCommand: vi.fn(),
  };
  const { rerender } = render(
    <SipInformationPanel
      metadata={metadata}
      {...props}
    />,
  );
  fireEvent.click(screen.getByText("编辑项目 SIP 信息"));
  const confirm = screen.getByRole("button", {
    name: "确认项目 SIP 信息",
  });
  expect(confirm.hasAttribute("disabled")).toBe(true);

  const completeMetadata = { ...metadata, material_code: "MAT-001" };
  rerender(
    <SipInformationPanel metadata={completeMetadata} {...props} />,
  );
  fireEvent.change(screen.getByRole("textbox", { name: "产品名称" }), {
    target: { value: "新上座" },
  });
  expect(onMetadataChange).toHaveBeenCalledWith({
    ...completeMetadata,
    material_name: "新上座",
  });
  fireEvent.click(screen.getByRole("button", {
    name: "确认项目 SIP 信息",
  }));
  expect(onConfirmMetadata).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run the composition test and confirm RED**

```bash
micromamba run -n qi-p0 npm test -- --run src/components/workbench/SipInformationPanel.test.tsx
```

Expected: FAIL，提示 `SipInformationPanel` module 不存在。

- [ ] **Step 3: Implement the presentational composition**

创建 `SipInformationPanel.tsx`，接口固定为：

```tsx
import type {
  BalloonOverlay,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import { SelectedSipDetailFields } from "./SelectedSipDetailFields";

export type MetadataDraft = {
  material_code: string;
  material_name: string;
  drawing_number: string;
  material: string;
  revision: string;
};

type SipInformationPanelProps = {
  metadata: MetadataDraft;
  metadataValues: Array<readonly [string, string | undefined]>;
  metadataDirty: boolean;
  disabled: boolean;
  selectedItem?: ReviewItem;
  selectedBalloon?: BalloonOverlay;
  selectedSourceActive?: boolean;
  onMetadataChange: (metadata: MetadataDraft) => void;
  onConfirmMetadata: () => void | Promise<void>;
  onCancelMetadata: () => void;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onSelectedSipDraftChange?: (dirty: boolean) => void;
};
```

组件外层和项目区域使用以下结构；metadata field map 必须保持 exact keys：

```tsx
export function SipInformationPanel({
  metadata,
  metadataValues,
  metadataDirty,
  disabled,
  selectedItem,
  selectedBalloon,
  selectedSourceActive = false,
  onMetadataChange,
  onConfirmMetadata,
  onCancelMetadata,
  onCommand,
  onSelectedSipDraftChange,
}: SipInformationPanelProps) {
  return (
    <section
      className="sip-information-panel"
      aria-label={zhCN.workbench.sipInformation}
      role="region"
    >
      <h2>{zhCN.workbench.sipInformation}</h2>
      <section
        className="sip-project-information"
        aria-labelledby="sip-project-information-title"
      >
        <h3 id="sip-project-information-title">
          {zhCN.workbench.projectSipInformation}
        </h3>
        <dl className="sip-metadata-summary">
          {metadataValues.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd title={value}>{value || zhCN.workbench.unknown}</dd>
            </div>
          ))}
        </dl>
        <details className="sip-metadata-editor">
          <summary>{zhCN.workbench.editProjectSipInformation}</summary>
          <fieldset disabled={disabled}>
            <legend className="visually-hidden">
              {zhCN.workbench.editProjectSipInformation}
            </legend>
            {([
              ["material_code", zhCN.workbench.metadataFields.materialCode],
              ["material_name", zhCN.workbench.metadataFields.materialName],
              ["drawing_number", zhCN.workbench.metadataFields.drawingNumber],
              ["revision", zhCN.workbench.metadataFields.revision],
              ["material", zhCN.workbench.metadataFields.material],
            ] as const).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  aria-label={label}
                  value={metadata[key]}
                  placeholder={zhCN.workbench.unknown}
                  onChange={(event) =>
                    onMetadataChange({
                      ...metadata,
                      [key]: event.target.value,
                    })
                  }
                />
              </label>
            ))}
            <div className="sip-metadata-actions">
              <button
                type="button"
                disabled={Object.values(metadata).some(
                  (value) => value.trim() === "",
                )}
                onClick={onConfirmMetadata}
              >
                {zhCN.workbench.confirmProjectSipInformation}
              </button>
              <button
                type="button"
                disabled={!metadataDirty}
                onClick={onCancelMetadata}
              >
                {zhCN.workbench.cancelProjectSipInformation}
              </button>
            </div>
          </fieldset>
        </details>
      </section>
      <section
        className="sip-selected-information"
        aria-labelledby="sip-selected-information-title"
      >
        <h3 id="sip-selected-information-title">
          {zhCN.workbench.selectedSipInformation}
        </h3>
        {selectedSourceActive ? (
          <p className="sip-information-panel__empty">
            {zhCN.workbench.selectedSourceSipUnavailable}
          </p>
        ) : selectedItem === undefined ? (
          <p className="sip-information-panel__empty">
            {zhCN.workbench.selectItemForSip}
          </p>
        ) : null}
        <SelectedSipDetailFields
          item={selectedSourceActive ? undefined : selectedItem}
          balloon={selectedSourceActive ? undefined : selectedBalloon}
          disabled={disabled}
          onCommand={onCommand}
          onDraftChange={onSelectedSipDraftChange}
        />
      </section>
    </section>
  );
}
```

在 `zhCN.workbench` 增加：

```ts
sipInformation: "SIP 信息",
projectSipInformation: "项目基本信息",
selectedSipInformation: "当前检验项",
editProjectSipInformation: "编辑项目 SIP 信息",
confirmProjectSipInformation: "确认项目 SIP 信息",
cancelProjectSipInformation: "取消项目 SIP 信息修改",
selectedSourceSipUnavailable: "当前选择的是待判定来源。",
selectItemForSip: "请选择一个有效检验项以填写 SIP 信息。",
```

- [ ] **Step 4: Add focused layout CSS**

将 `.sip-metadata-card` 的共享视觉规则迁移到新面板，禁止负 margin/top：

```css
.sip-information-panel {
  display: grid;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--qi-border);
  border-radius: 8px;
  background: #ffffff;
}

.sip-information-panel > h2 {
  margin: 0;
  font-size: 15px;
}

.sip-project-information,
.sip-selected-information {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.sip-project-information h3,
.sip-selected-information h3 {
  margin: 0;
  color: #344054;
  font-size: 12px;
}

.sip-information-panel__empty {
  margin: 0;
  padding: 10px;
  border: 1px dashed #cbd5e1;
  color: var(--qi-muted);
  font-size: 11px;
  text-align: center;
}

@media (max-width: 460px) {
  .sip-metadata-summary {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run the component tests**

```bash
micromamba run -n qi-p0 npm test -- --run \
  src/components/workbench/SelectedSipDetailFields.test.tsx \
  src/components/workbench/SipInformationPanel.test.tsx
```

Expected: PASS。

- [ ] **Step 6: Commit the unified component**

```bash
git add \
  frontend/src/components/workbench/SipInformationPanel.tsx \
  frontend/src/components/workbench/SipInformationPanel.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: add unified SIP information panel"
```

## Task 3: Move SIP To The Right Detail And Retire Both Old Locations

**Files:**

- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

- [ ] **Step 1: Write RED integration tests for unique placement and independent dirty states**

在 `InspectionWorkbench.test.tsx` 把 metadata test 改为：

```tsx
const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
expect(within(sipRegion).getByRole("heading", {
  name: "项目基本信息",
})).not.toBeNull();
expect(within(sipRegion).getByRole("heading", {
  name: "当前检验项",
})).not.toBeNull();
expect(within(sipRegion).getByRole("group", {
  name: "SIP 确认字段",
})).not.toBeNull();

openAuxiliaryPanel();
const auxiliary = screen.getByRole("complementary", {
  name: "导出与处理信息",
});
expect(within(auxiliary).queryByRole("region", {
  name: "SIP基本信息",
})).toBeNull();
expect(screen.getAllByRole("region", { name: "SIP 信息" })).toHaveLength(1);
```

增加 source draft 与 selected SIP draft 不互相覆盖的测试：

```tsx
const saveStatus = within(
  screen.getByRole("region", { name: "项目摘要" }),
).getByRole("status");

fireEvent.change(screen.getByRole("textbox", {
  name: "检验方法：M6",
}), { target: { value: "三针法复核" } });
expect(saveStatus.textContent).toBe("有未保存修改");

fireEvent.click(screen.getByRole("row", { name: /待判定来源/ }));
expect(saveStatus.textContent).toBe("有未保存修改");

fireEvent.change(screen.getByRole("textbox", {
  name: "来源原文",
}), { target: { value: "技术要求：去除锐边" } });
expect(saveStatus.textContent).toBe("有未保存修改");

fireEvent.click(screen.getByRole("row", { name: /M6/ }));
expect((screen.getByRole("textbox", {
  name: "检验方法：M6",
}) as HTMLInputElement).value).toBe("三针法复核");
```

在 `InspectionItemTable.test.tsx` 添加 old-path retirement：

```tsx
expect(screen.queryByRole("group", { name: "SIP 确认字段" })).toBeNull();
expect(screen.queryByText("确认当前检验项 SIP")).toBeNull();
```

- [ ] **Step 2: Run integration tests and confirm RED**

```bash
micromamba run -n qi-p0 npm test -- --run \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL，因为 SIP 仍由 table 渲染，workbench detail 尚未组合新面板。

- [ ] **Step 3: Split dirty ownership in `InspectionWorkbench`**

把现有 `sipDraftDirty` 拆成两个状态：

```tsx
const [sourceDraftDirty, setSourceDraftDirty] = useState(false);
const [selectedSipDraftDirty, setSelectedSipDraftDirty] = useState(false);

const localDraftDirty =
  reviewDraftDirty
  || sourceDraftDirty
  || selectedSipDraftDirty
  || metadataDraftDirty;
```

`InspectionItemTable` 改为：

```tsx
<InspectionItemTable
  compact
  items={items}
  balloons={balloons}
  pendingSources={pendingSources}
  candidateNumbers={candidateNumbers}
  filter={filter}
  selectedItemId={selectedItemId}
  selectedSourceId={selectedSourceId}
  disabled={reviewCommandsDisabled}
  onSelectItem={selectItem}
  onSelectSource={selectSource}
  onCommand={submitCommand}
  onDraftChange={setSourceDraftDirty}
/>
```

在 `InspectionItemTable.tsx` 删除 `SelectedSipDetailFields` import、
`selectedSipDraftDirty` 与原 render；source dirty effect 收敛为：

```tsx
useEffect(() => {
  onDraftChange?.(dirtySourceIds.length > 0);
}, [dirtySourceIds, onDraftChange]);
```

- [ ] **Step 4: Move metadata UI and selected SIP into the detail column**

从 `InspectionWorkbench.tsx` 删除 auxiliary panel 中的 `.sip-metadata-card` JSX。
从新组件 import `MetadataDraft` 并删除 workbench 内同名 local type。保留
`metadataValues`，增加以下 callbacks：

```tsx
const confirmMetadata = async () => {
  const saved = await submitCommand({
    type: "set_sip_metadata",
    ...metadata,
  });
  if (saved) setMetadataDraftDirty(false);
};

const cancelMetadata = () => {
  setMetadata(metadataDraft(workingCopy));
  setMetadataDraftDirty(false);
};
```

在 `ReviewPanel` 后追加：

```tsx
<SipInformationPanel
  metadata={metadata}
  metadataValues={metadataValues}
  metadataDirty={metadataDraftDirty}
  disabled={reviewCommandsDisabled}
  selectedItem={selectedReviewItem}
  selectedBalloon={selectedReviewBalloon}
  selectedSourceActive={selectedSourceId !== undefined}
  onMetadataChange={(nextMetadata) => {
    setMetadata(nextMetadata);
    setMetadataDraftDirty(true);
  }}
  onConfirmMetadata={confirmMetadata}
  onCancelMetadata={cancelMetadata}
  onCommand={submitCommand}
  onSelectedSipDraftChange={setSelectedSipDraftDirty}
/>
```

保留 `metadataDraft()` 和项目摘要继续读取 `metadata`，因此用户编辑中的项目名称、
图号和版本仍即时反映在 summary。

同时把 `zhCN.workbench.asideRegion` 更新为：

```ts
asideRegion: "导出与处理信息",
```

- [ ] **Step 5: Retire old CSS selectors**

删除仅属于旧 `.sip-metadata-card` 外壳的规则：

```css
.sip-metadata-card { ... }
.sip-metadata-card h2 { ... }
```

保留并复用：

```css
.sip-metadata-summary
.sip-metadata-editor
.sip-metadata-actions
.sip-detail-fields
.sip-detail-actions
```

确保 `.inspection-review-workspace__detail` 保持自身滚动，不修改 workbench 固定高度。

- [ ] **Step 6: Run focused integration tests**

```bash
micromamba run -n qi-p0 npm test -- --run \
  src/components/workbench/SelectedSipDetailFields.test.tsx \
  src/components/workbench/SipInformationPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: PASS。

- [ ] **Step 7: Commit the placement change**

```bash
git add \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: unify SIP information in item detail"
```

## Task 4: Update Auxiliary Copy And Browser Flow

**Files:**

- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`

- [ ] **Step 1: Write RED copy and mounted-state tests**

在 `PdfWorkspace.test.tsx` 增加：

```tsx
render(
  <PdfWorkspace
    pdfDocument={null}
    candidates={[]}
    sources={[]}
    balloons={[]}
    auxiliaryPanel={<div data-testid="auxiliary-content">正式文件</div>}
  />,
);

const open = screen.getByRole("button", { name: "展开导出与处理信息" });
expect(open.getAttribute("aria-expanded")).toBe("false");
fireEvent.click(open);
expect(screen.getByRole("button", {
  name: "收起导出与处理信息",
}).getAttribute("aria-expanded")).toBe("true");
fireEvent.click(screen.getByRole("button", {
  name: "收起导出与处理信息",
}));
expect(screen.getByTestId("auxiliary-content")).not.toBeNull();
```

把 `InspectionWorkbench.test.tsx` 中所有旧按钮查询改为新文案，并继续验证 export
in-flight 收起再展开后只提交一次。

- [ ] **Step 2: Run copy-focused tests and confirm RED**

```bash
micromamba run -n qi-p0 npm test -- --run \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL，因为 `zhCN.pdf` 仍使用旧 SIP 文案。

- [ ] **Step 3: Update copy without changing `PdfWorkspace` behavior**

只修改 `zhCN.ts`：

```ts
expandAuxiliary: "展开导出与处理信息",
collapseAuxiliary: "收起导出与处理信息",
```

`PdfWorkspace.tsx` 不修改，继续读取上述 copy 并保持现有 `hidden` mounted state。

- [ ] **Step 4: Update the real E2E selectors**

在 `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`：

- `populateSipMetadata()` 不再打开辅助浮层；
- region 改为唯一 `SIP 信息`；
- summary 文案改为 `编辑项目 SIP 信息`；
- button 改为 `确认项目 SIP 信息`；
- per-item button 改为 `确认当前检验项 SIP`；
- export 阶段只在需要正式文件时点击 `展开导出与处理信息`。

实现固定为：

```ts
async function populateSipMetadata(page: Page): Promise<void> {
  const sip = page.getByRole("region", { name: "SIP 信息" });
  await sip.locator("summary")
    .filter({ hasText: "编辑项目 SIP 信息" })
    .click();
  const fields = [
    ["物料编码", "MVP-001"],
    ["产品名称", "自动化样件"],
    ["图号", "QI-MVP-001"],
    ["版本号", "A"],
    ["材质", "钢"],
  ] as const;
  for (const [label, value] of fields) {
    await sip.getByLabel(label, { exact: true }).fill(value);
  }
  await submitReviewAction(
    page,
    sip.getByRole("button", { name: "确认项目 SIP 信息" }),
  );
}
```

逐项 SIP 确认改为：

```ts
await submitReviewAction(
  page,
  sipDetails.getByRole("button", { name: "确认当前检验项 SIP" }),
);
```

- [ ] **Step 5: Run copy tests and enumerate E2E**

```bash
micromamba run -n qi-p0 npm test -- --run \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
micromamba run -n qi-p0 npm run e2e:list
```

Expected: component tests PASS；Playwright 成功列出 tests，无 config/import error。

- [ ] **Step 6: Commit copy and browser-flow updates**

```bash
git add \
  frontend/src/copy/zhCN.ts \
  frontend/src/components/pdf/PdfWorkspace.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/e2e/chinese-pdf-upload-mvp.spec.ts
git commit -m "test: align SIP browser flow with unified panel"
```

## Task 5: Full Verification, Browser Smoke, And Independent Review

**Files:**

- Modify only if a verification failure proves a defect in an allowed path.

- [ ] **Step 1: Run all focused tests**

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
micromamba run -n qi-p0 npm test -- --run \
  src/components/workbench/SelectedSipDetailFields.test.tsx \
  src/components/workbench/SipInformationPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/ExportPanel.test.tsx
```

Expected: PASS，0 failed。

- [ ] **Step 2: Run frontend full suite and production build**

```bash
micromamba run -n qi-p0 npm test -- --run
micromamba run -n qi-p0 npm run build
micromamba run -n qi-p0 npm run e2e:list
```

Expected: full Vitest suite PASS；TypeScript/Vite build PASS；Playwright list PASS。

- [ ] **Step 3: Run the closest real browser smoke**

启动仓库已有 frontend/runtime，不发明端口或账号；使用 Chrome DevTools MCP 在真实
workbench 验证：

1. `1565×796` 下右侧只存在一个 `SIP 信息` region；
2. 项目 metadata 展开、修改、取消、成功和失败重试；
3. 当前项 SIP 修改、取消、成功和失败重试；
4. 切换两个 active items 后返回，未保存 draft 仍在；
5. 选中待判定来源时项目基本信息保留，当前项显示空状态；
6. reviewed/frozen 时两个 SIP 分区均不可编辑；
7. 左侧按钮为 `展开导出与处理信息`，收起再展开后 export in-flight 或成功下载保持；
8. 正式 PDF、SIP Excel、manifest 三个真实下载仍可访问；
9. `1240px` 附近和窄屏下无横向溢出、遮挡或负定位；
10. console 无新增 error/warn。

若真实 runtime、project、认证或导出前置条件不可用，记录具体 blocker，不用
component test 冒充 browser proof。

- [ ] **Step 4: Run independent read-only review**

Reviewer 必须检查：

- verdict: `accept`、`accept with concerns` 或 `reject`；
- 两个旧 SIP 呈现位置是否完整退役；
- `InspectionWorkbench.submitCommand()` 是否仍是唯一 command owner；
- metadata 与 selected item field source 是否没有混淆；
- dirty callbacks 是否不会互相覆盖；
- 保存失败、selected source、reviewed/frozen 和 export mounted state；
- tests 是否覆盖真实截图中的分散问题，而不只检查新文案；
- exact files、tests 和 blocking/non-blocking concerns。

父 agent 必须直接复核 reviewer 的 blocking claim 和 final diff。

- [ ] **Step 5: Inspect final diff and status**

```bash
git status --short --branch
git diff origin/main...HEAD -- \
  frontend/src/components/workbench/SelectedSipDetailFields.tsx \
  frontend/src/components/workbench/SelectedSipDetailFields.test.tsx \
  frontend/src/components/workbench/SipInformationPanel.tsx \
  frontend/src/components/workbench/SipInformationPanel.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/pdf/PdfWorkspace.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css \
  frontend/e2e/chinese-pdf-upload-mvp.spec.ts
```

Expected: every changed line traces to this plan；两个无关 `__pycache__` 修改未 staged；
`.superpowers/brainstorm/` 未提交。

- [ ] **Step 6: Commit only verification-driven fixes**

如果 Step 1-4 产生必要修复：

```bash
git add \
  frontend/src/components/workbench/SelectedSipDetailFields.tsx \
  frontend/src/components/workbench/SelectedSipDetailFields.test.tsx \
  frontend/src/components/workbench/SipInformationPanel.tsx \
  frontend/src/components/workbench/SipInformationPanel.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/pdf/PdfWorkspace.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css \
  frontend/e2e/chinese-pdf-upload-mvp.spec.ts
git commit -m "fix: close unified SIP panel verification gaps"
```

如果没有 verification-driven diff，不创建空 commit。

## Completion Contract

只有同时满足以下条件才可声明完成：

- 项目 SIP 与当前项 SIP 在右侧唯一 `SIP 信息` region 中；
- 左侧辅助浮层不再包含 SIP metadata；
- `InspectionItemTable` 不再拥有 selected SIP detail draft；
- 两个 command payload 与唯一 submit path 不变；
- source、selected SIP、metadata、review dirty state 独立且汇总正确；
- focused tests、full frontend suite、build 和 `e2e:list` 实际通过；
- 可用时完成真实 Chrome smoke；不可用时明确 blocker 和未覆盖风险；
- independent reviewer 没有 unresolved blocking issue；
- task commits 只包含 allowed paths，用户已有无关改动未被触碰。
