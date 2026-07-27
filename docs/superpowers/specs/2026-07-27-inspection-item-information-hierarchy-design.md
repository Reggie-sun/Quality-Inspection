# Inspection Item Information Hierarchy Design

## Context

当前双栏审核工作区已经把检验项列表和编辑器放在同一可视区域，但所选项的
`raw_text` 至少重复出现在三个位置：

- 左侧检验项列表；
- 右侧 `SelectedInspectionItemSummary` 的“检验项”字段；
- `ReviewPanel` 的卡片标题；
- `ReviewPanel` 的“原始标注”输入框。

这些位置没有形成新的信息层级，用户看到多个相同的 `48`、`85` 时无法判断它们
是否代表不同数据。与此同时，“选择需要合并的检验项”是一个影响多条记录的批量
操作，却长期占据单项详情区顶部，混淆了列表操作和详情编辑的职责。

本设计在不改变 Review command schema、working-copy aggregate 或后端 API 的前提
下，重新定义列表、详情标题、图纸原文、解析结果和合并操作的展示职责。

## Goals

- 消除所选检验项在右侧详情区内无意义的 `raw_text` 重复。
- 让列表、详情标题和表单字段分别承担导航、对象身份和数据核对职责。
- 将合并检验项改为列表侧的显式批量模式。
- 在提交合并前展示并允许修改合并结果。
- 保留现有 dirty-draft、at-most-once submit、失败重试和审核锁边界。
- 保持当前双栏工作区、内部滚动和窄屏响应式行为。

## Non-Goals

- 不改变 Review command type、API route、schema、operation log 或后端 merge 语义。
- 不改变 `raw_text`、基本尺寸、公差、气泡编号或状态字段的业务含义。
- 不重设计 PDF workspace、SIP metadata、balloon toolbar 或 export flow。
- 不引入自动合并、模型判断、相似度推荐或新的持久化草稿层。
- 不建立第二套检验项编号算法。
- 不改变当前 P0 对 active、excluded、candidate 或 source-only item 的正式语义。

## Selected Direction

用户批准方案 A：主从分工清晰。

```text
左侧列表
  raw_text + item type + status
        │
        └── 选中项
              ↓
右侧详情标题
  检验项编号 + item type + status
  气泡编号 + 页码
              ↓
右侧表单
  图纸原文：raw_text
  解析结果：数量 / 基本尺寸 / 上公差 / 下公差
```

同一个 `raw_text` 可以同时出现在左侧列表和右侧“图纸原文”字段，因为两个位置
承担不同职责：

- 列表中的值用于快速定位和切换；
- 表单中的值用于核对和修改图纸原文。

右侧不再通过摘要或标题额外复制该值。

## Information Hierarchy

### Master List

左侧紧凑列表继续显示：

- 现有 display number；
- `raw_text`；
- item type；
- status。

列表不增加基本尺寸、公差等详情字段。所选行继续通过背景、边框和
`aria-selected` 表达选择状态。

### Detail Header

移除独立的 `SelectedInspectionItemSummary` 呈现。其有用信息收敛到一个详情
header：

- 主标题：`检验项 {display number} · {item type}`；
- 状态：右侧 status badge；
- 辅助信息：`气泡 {number}`、`第 {page} 页`，不存在时显示现有 unknown copy。

header 不显示 `raw_text`。详情编号必须复用 `InspectionWorkbench` 已经持有的
formal balloon number 或 `candidateNumbers` 结果，并通过明确 prop 传给
`ReviewPanel`。不得在 `ReviewPanel` 内按数组下标重新编号。

### Detail Form

字段表单分成两个视觉和语义分组：

1. `图纸原文`
   - 原始标注；
   - complex item 已有 coordinates 等来源相关字段。
2. `解析结果`
   - 数量；
   - 基本尺寸；
   - 上公差；
   - 下公差；
   - item type 对应的其他现有 core fields。

默认 view 状态继续只读；点击“修改”后才进入 edit。“修改保存”、保留、排除、
候选确认和气泡要求等现有命令语义保持不变。

## Merge Workflow

### Entry

移除 `ReviewPanel` 顶部长期显示的“选择需要合并的检验项”折叠区。列表工具栏新增
次要按钮：

`合并重复项`

按钮附近提供可读说明：

`仅用于同一检验要求被重复识别，或一条标注被拆成多项的情况。`

当前存在未保存 review draft 时，进入合并模式必须被现有 dirty selection guard
阻止，并显示明确提示；不得清除当前草稿。

### Selection Mode

点击“合并重复项”后，列表进入显式 multi-select mode：

- 普通单选标识切换为 checkbox；
- 只允许选择 active inspection items；
- 顶部显示 `已选择 N 项`；
- 少于两项时“下一步”disabled；
- “取消”退出合并模式并清除本次 merge selection；
- 列表筛选、分页和内部滚动继续可用，已选项不能因分页而丢失。

合并选择只属于本次 merge mode，不复用当前单项 selection state。

### Preview

选择至少两项并点击“下一步”后展示合并预览：

- 展示所有来源 `raw_text`；
- 展示可编辑的“合并后的原始标注”；
- 展示或选择现有 item type；
- 显示“合并不是数值相加”的说明；
- 提供“返回修改”和“确认合并 N 项”。

默认 merged `raw_text` 使用以下确定性规则：

1. 对每个来源值执行 trim；
2. 移除完全相同的重复值，保留首次出现顺序；
3. 使用一个空格连接剩余值。

示例：

```text
48 + 48       → 48
⌀10 + ±0.1   → ⌀10 ±0.1
```

用户可以在确认前修改该结果。本规则只生成 frontend preview draft，不改变后端
merge contract。

### Submission

确认动作继续走唯一 submit path：

```text
merge preview
→ submitCommand({
    type: "merge",
    item_ids,
    raw_text
  })
→ existing onSave(command)
→ workbench refresh
```

一次确认只允许产生一次 `POST /review/commands`。

成功后：

- 清除 merge selection 和 preview draft；
- 退出 merge mode；
- 从刷新后的 working copy 识别并选中新生成的 merged item；
- 详情回到 view 状态。

失败后：

- 保留 merge selection；
- 保留用户编辑过的 merged `raw_text`；
- 保持预览可见；
- 显示保存失败状态并允许直接重试。

## Component Ownership

### `InspectionWorkbench`

- 继续拥有 `candidateNumbers`、selected item、dirty selection guard 和
  `submitCommand()`。
- 生成唯一的 selected item display metadata，并传给详情 header。
- 协调 merge success 后的新 item selection。
- 不重新解释后端 merge 业务语义。

### `InspectionItemTable`

- 拥有 merge mode、跨分页 checkbox selection 和 merge toolbar。
- 进入预览前提供所选 active item IDs 与来源值。
- 默认状态不渲染 merge checkbox。
- 不创建第二套 command submit path。

### `ReviewPanel`

- 移除 merge selector 和 `selectedIds`。
- 使用父级传入的 display number、page、balloon 和 status 构造单一详情 header。
- 继续拥有单项 review draft、view/edit 状态、拆分、新增和现有单项命令。

### Merge Preview

预览可以是 `InspectionItemTable` 的局部子组件，或一个职责单一的
`MergeInspectionItemsPreview`。它只拥有：

- preview draft；
- 来源展示；
- 返回、取消和确认交互。

它不直接调用 API，只通过现有 `onCommand`/`submitCommand` 提交。

## Error Handling

- merge command in-flight 时禁用重复确认和其他 review mutation。
- backend rejection、stale working copy 或网络失败不得清除 merge draft。
- refresh 成功但新 item 无法唯一识别时，退出 merge mode但保持当前合法 selection，
  并显示通用提交成功状态；不得猜测 item ID。
- startup blocker 和 lock blocker 继续 fail-closed。
- 普通 command error 继续允许原地重试，不得重新引入 `error → permanent busy`。

## Accessibility

- “合并重复项”使用真实 button。
- merge mode checkbox 的 accessible name 包含列表序号、`raw_text` 和 item type。
- `已选择 N 项` 使用可读状态区域；数量变化不只依赖颜色。
- 预览打开后 focus 移到预览 heading。
- Escape 或“取消”退出 merge mode，且不会改变 inspection data。
- “确认合并 N 项”的 accessible name 包含选择数量。
- header、`图纸原文` 和 `解析结果` 使用明确 heading/fieldset/legend 层级。
- status 继续通过文字和 badge 表达，不仅依赖颜色。

## Verification

按 TDD 顺序增加 focused coverage。

### `InspectionWorkbench.test.tsx`

- 详情 header 使用 display number + item type，而不是 `raw_text`。
- 不再渲染独立“所选检验项摘要”。
- formal number、candidate number、page 和 status 正确传入详情。
- dirty review draft 阻止进入 merge mode。
- merge command 保持 at-most-once。
- success refresh 后选择新 merged item；无法唯一识别时不猜测。

### `InspectionItemTable.test.tsx`

- 默认状态没有 merge checkbox。
- 点击“合并重复项”进入 multi-select mode。
- 少于两项时“下一步”disabled。
- selection 跨分页保留，取消后清空。
- inactive/excluded item 不可进入 merge selection。
- `48 + 48` preview 为 `48`。
- `⌀10 + ±0.1` preview 为 `⌀10 ±0.1`。
- 用户可以编辑 preview `raw_text`。
- merge failure 保留 selection 和 preview draft。
- merge success 清除本地状态。

### `ReviewPanel.test.tsx`

- 不再渲染 merge selector。
- 不再以 `raw_text` 作为 card heading。
- `图纸原文` 与 `解析结果` 分组正确。
- 现有 view/edit、修改保存、失败重试、拆分和新增行为不回归。

### Full Verification

- frontend focused tests；
- frontend full test suite；
- production build；
- `e2e:list`；
- Chrome smoke at `1565×796`：
  - 列表与详情保持同一固定高度工作区；
  - 同一 `raw_text` 不再在右侧重复展示；
  - merge mode、跨分页选择、预览、取消、成功和失败重试；
  - 键盘进入、选择、返回和确认；
  - console 无新增 error/warn。

## Execution Selection

- Selected lane: `Standard`。变化只涉及 frontend presentation 和已有 command
  producer ownership，不改变稳定 API/schema；但跨
  `InspectionWorkbench`、`InspectionItemTable`、`ReviewPanel`、copy、CSS 和 tests。
- Selected plan: 本设计批准并提交后生成的 implementation plan 是本 UI refinement
  的唯一 execution plan。
- Selection evidence: 用户确认详情主信息采用“序号＋类型”，选择方案 A，并批准
  将 merge 移到列表工具栏的三步批量流程。
- Validation action: `amend` 当前 frontend presentation 和 merge producer；
  backend contract 保持不变。
- Writer ownership and order: 实现期间同一 file group 只有一个 writer；核心行为
  变更完成后需要独立只读 reviewer。
- Next verification: implementation plan 先定义 RED tests 和 exact allowed paths，
  再开始 production edit。

## Risks

- 新 merged item 的识别依赖 refresh 前后 working-copy 差异。计划必须定义唯一识别
  失败时的安全回退，不得按数组位置猜测。
- 跨分页 multi-select 可能因为 filter/page 变化丢失选择。selection 必须按
  `item_id` 持有，并在退出 merge mode 时统一清理。
- 去重规则可能隐藏用户希望保留的重复文本，因此 preview 必须可编辑，且只对完全
  相同的 trimmed string 去重。
- 移除 summary 后可能丢失气泡、页码或状态可见性。详情 header 必须在删除旧组件前
  覆盖这些信息，并由 focused tests 锁定。
