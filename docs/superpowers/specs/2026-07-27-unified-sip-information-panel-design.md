# Unified SIP Information Panel Design

## Status

- Date: 2026-07-27
- Status: Approved
- Selected approach: 方案 B，将项目级 `SIP基本信息` 与当前检验项
  `SIP 确认` 收敛到右侧详情区中的唯一 SIP 信息面板。
- Scope: frontend presentation、draft ownership 拆分、现有 command producer 接线与
  focused verification。

## Context

当前工作台把两类 SIP 信息分散在两个空间：

- PDF 图纸上的左侧辅助浮层显示项目级 `SIP基本信息`、正式文件和公司处理记录；
- 右侧检验项列表下方显示 `所选检验项 SIP 确认`。

这使用户需要在图纸浮层和检验区之间来回核对，也容易把项目级字段与单个检验项字段
误解为两套互不相关的 SIP 流程。两类表单已经共享
`InspectionWorkbench.submitCommand()`，但视觉结构没有体现这一点。

本设计只收敛前端信息架构。它不改变 SIP 数据模型、review command、后端 API、
freeze/export 顺序或正式文件语义。

## Goals

- 在右侧当前检验项详情中提供唯一的 `SIP 信息` 面板。
- 在同一面板内明确区分“项目基本信息”和“当前检验项”。
- 删除左侧辅助浮层中的 `SIP基本信息`，避免同一 SIP 工作流跨两侧呈现。
- 保持现有 metadata、per-item SIP detail、dirty guard、失败重试和只读状态语义。
- 保持正式文件与公司处理记录位于左侧辅助浮层，且不改变 export 状态生命周期。

## Non-Goals

- 不改变 `ReviewCommand`、API type、backend schema 或 persistence。
- 不合并 `set_sip_metadata` 与 `set_sip_detail_fields` 为一个 command。
- 不改变正式文件生成条件、freeze、balloon、manifest 或 reviewed result 语义。
- 不重构检验项审核表单、合并重复项、待判定来源或 PDF workspace。
- 不增加 tab、wizard、第二套 submit path 或新的 runtime configuration。

## Information Architecture

### Right Detail Area

右侧 `inspection-review-workspace__detail` 保持当前检验项审核内容，并在其后呈现一个
`SIP 信息` 面板。该面板包含两个清晰的语义分区。

#### Project Information

“项目基本信息”显示现有项目级 SIP 摘要：

- 产品名称；
- 图号；
- 版本；
- 材质；
- 单位；
- 检验标准；
- 检验人员角色；
- 审核人员角色。

摘要继续对缺失值显示现有占位符 `—`。现有 `编辑 SIP 信息` 折叠编辑器改名为
`编辑项目 SIP 信息`，并继续编辑 command 所要求的：

- 物料编码；
- 产品名称；
- 图号；
- 版本；
- 材质。

“检验标准”和“检验人员角色”继续来自当前选中检验项；其他可编辑字段继续来自
`workingCopy.sip_metadata`。两个来源必须在代码中保持明确，不得为了视觉合并而
创建复制数据或新的业务 Owner。

#### Selected Inspection Item

“当前检验项”继续显示现有字段：

- 检验项目；
- 检验标准；
- 检验方法；
- 关键尺寸；
- 检验角色；
- 页码；
- 备注。

当前检验项存在且 active 时才显示该分区。选中待判定来源或没有合法检验项时，显示
明确空状态，不渲染可提交的单项 SIP 表单。

确认按钮文案改为 `确认当前检验项 SIP`，取消行为保持不变。

### Left Auxiliary Panel

左侧辅助浮层只保留：

1. 正式文件；
2. 公司处理记录。

PDF 控件按钮从 `展开 SIP 与导出信息` / `收起 SIP 与导出信息` 改为
`展开导出与处理信息` / `收起导出与处理信息`。

辅助浮层继续保持挂载并通过现有 `hidden` 状态开关显示，确保 export in-flight、
失败状态和三份下载不会因收起而丢失。

## Component Ownership

### `InspectionWorkbench`

- 继续拥有 selected item、project metadata draft、metadata dirty state、
  `reviewCommandsDisabled` 和唯一 `submitCommand()`。
- 组合新的 `SipInformationPanel`，并把它渲染到
  `inspection-review-workspace__detail`。
- 将 source review draft dirty 与 selected SIP detail draft dirty 分开接收，再与
  review draft、metadata draft 一起汇总为 `localDraftDirty`。
- 从 `auxiliaryPanel` 移除 metadata UI，只保留 export 与 company log。

### `SipInformationPanel`

新增一个职责单一的呈现组件，负责：

- 组合项目基本信息摘要与现有 metadata editor；
- 组合当前检验项 SIP detail fields；
- 根据 selected item/source 状态显示表单或空状态；
- 通过父级传入的唯一 `onCommand` 提交现有 command。

它不调用 API，不解释 freeze/export 语义，也不复制 selected item 或 working copy
状态。

### `SelectedSipDetailFields`

从 `InspectionItemTable` 提取当前检验项 SIP 表单及其 per-item draft：

- draft 继续按 `item_id` 保存；
- 切换检验项后再返回，未保存 draft 继续存在；
- 成功后清除该 item 的 dirty state；
- 失败后保留 draft 与 dirty state；
- 取消恢复该 item 当前 working-copy baseline。

该组件只通过现有 `set_sip_detail_fields` command 提交，不新增 API consumer。

### `InspectionItemTable`

- 继续拥有列表、筛选、分页、merge mode 和待判定来源 review draft。
- 不再渲染 `sip-detail-fields`。
- `onDraftChange` 只报告自身仍拥有的 source/list draft，不得因 SIP 表单移出后把
  另一组件仍为 dirty 的状态覆盖为 false。

### `PdfWorkspace` And `ExportPanel`

- `PdfWorkspace` 只更新辅助浮层按钮文案，不改变 toggle 或挂载行为。
- `ExportPanel` 不做逻辑修改；正式文件生成、错误处理和下载保持现状。

## Data Flow

项目级保存路径保持：

```text
SipInformationPanel
→ InspectionWorkbench.submitCommand({
    type: "set_sip_metadata",
    ...
  })
→ onSave(command)
→ ProjectWorkbenchApp.save()
→ saveWorkingCopy()
→ existing review command API
→ working-copy refresh
```

当前检验项保存路径保持：

```text
SelectedSipDetailFields
→ SipInformationPanel
→ InspectionWorkbench.submitCommand({
    type: "set_sip_detail_fields",
    item_id,
    ...
  })
→ onSave(command)
→ existing review command API
→ working-copy refresh
```

两个 command 继续串行经过 `savingRef` 和 `reviewCommandsDisabled`。视觉合并不得把
两次业务提交伪装成一次原子提交。

## Draft And Selection Behavior

- project metadata、selected SIP detail、source review 和 review form 分别报告
  dirty state；`InspectionWorkbench` 使用 OR 汇总，任一 dirty 即阻止 freeze。
- selected SIP detail draft 使用 `item_id` 作为 key，不按数组位置或当前页持有。
- 切换到另一个 active item 时，SIP 面板同步显示对应 item；返回原 item 时恢复其
  未保存 draft。
- 现有 selection guard 继续保护未保存 review draft。selected SIP detail 和 source
  draft 继续按稳定 ID 保留，因此切换 selection 不得清除尚未保存的 draft。
- working-copy version 更新时，只刷新没有本地 dirty draft 的 baseline。

## Error And Read-Only States

- `set_sip_metadata` 或 `set_sip_detail_fields` 保存失败后，保持用户输入、dirty
  state 和可重试按钮。
- `saving`、`busy`、frozen 或 reviewed 时，项目与当前项 SIP 控件使用现有
  `reviewCommandsDisabled` 禁用。
- selected item inactive、缺失或当前选中待判定来源时，不允许构造
  `set_sip_detail_fields`。
- export error 不进入 SIP draft 状态；SIP command error 不清除 export 状态。
- 不使用 warning 或静态说明绕过 blocking/fatal 状态。

## Accessibility

- 唯一外层区域使用 `region`，accessible name 为 `SIP 信息`。
- “项目基本信息”和“当前检验项”使用 heading 或 fieldset/legend 表达层级。
- metadata editor 使用原生 `details/summary`，summary 文案为
  `编辑项目 SIP 信息`。
- 当前检验项字段的 accessible name 继续包含字段标签和当前 item identity。
- 空状态使用可读文本，不只依赖隐藏、颜色或 disabled 状态。
- 辅助浮层按钮的 `aria-expanded`、`aria-controls` 与键盘行为保持不变。

## Responsive Layout

- 宽屏下，SIP 面板位于右侧详情列并使用该列完整宽度。
- `max-width: 1240px` 的列表/详情上下布局下，SIP 面板跟随详情内容自然排列。
- `max-width: 820px` 的单栏工作台下，不创建横向固定宽度或新的页面级滚动锁。
- metadata 摘要保留两列紧凑布局；空间不足时允许现有响应式规则收敛为单列。
- 不使用负 margin、负 top 或固定截图坐标修正对齐。

## Verification

### Focused Component Tests

`InspectionWorkbench.test.tsx`：

- 左侧辅助浮层不再包含 `SIP基本信息`；
- 右侧详情存在唯一 `SIP 信息` 区域；
- 项目 metadata command payload 保持不变；
- selected item/source 切换显示正确分区；
- 各类 dirty state 独立汇总，不互相覆盖；
- reviewed/frozen 状态禁用两个 SIP 编辑区。

`SelectedSipDetailFields.test.tsx`：

- 按 item ID 保留 draft；
- 确认提交现有 `set_sip_detail_fields` payload；
- 成功清除、失败保留、取消恢复 baseline；
- 缺失/inactive item 不产生 command。

`InspectionItemTable.test.tsx`：

- 不再渲染当前检验项 SIP fieldset；
- source review draft、列表、筛选、分页与 merge mode 不回归。

`PdfWorkspace.test.tsx`：

- 新按钮文案与 `aria-expanded` 正确；
- 收起/展开继续保持辅助内容挂载。

`ExportPanel.test.tsx`：

- 三产物、失败重试和原子 export 状态保持现状。

### Full Verification

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
npm test -- --run \
  src/components/workbench/SelectedSipDetailFields.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/ExportPanel.test.tsx
npm test -- --run
npm run build
npm run e2e:list
```

随后使用 Chrome 在真实 workbench 验证：

- 右侧只出现一个 `SIP 信息` 区域；
- 项目 metadata 编辑、取消、成功和失败重试；
- 切换检验项后当前项 SIP 内容同步且 draft 不丢失；
- 待判定来源、reviewed 和 frozen 状态；
- 左侧辅助浮层新文案、收起再展开、正式文件和三份下载保持；
- `1565×796`、`1240px` 附近和窄屏布局；
- console 无新增 error/warn。

## Execution Selection

- Selected lane: `Standard`。改动只涉及 frontend presentation 和现有 command
  producer 接线，不改变稳定 API/schema；但跨 workbench、list、PDF auxiliary、
  copy、styles 和 tests，并需要 browser smoke。
- Selected plan: 本设计批准并提交后生成的唯一 implementation plan。
- Selection evidence: 用户指出截图中的两个 SIP 区域也需要合并，并批准方案 B。
- Validation action: `amend` frontend information hierarchy；backend、export 和
  review command contract 保持不变。
- Writer ownership and order: implementation 期间同一 frontend file group 只有
  一个 writer；核心行为完成后需要独立只读 reviewer。
- Next verification: implementation plan 先定义 RED tests、exact allowed paths 和
  focused command，再开始 production edit。

## Risks

- metadata 摘要混合项目级字段和当前 item 的只读字段；小标题和 source mapping 必须
  明确，不能因视觉合并改变字段 Owner。
- `InspectionItemTable` 当前把 selected SIP 与 source draft 合并成一个 dirty
  callback；提取时必须拆开，否则一个组件报告 false 可能覆盖另一组件的 true。
- 把 SIP 面板移到详情列会增加垂直内容；必须依赖现有详情列滚动，而不是扩张整个
  workbench 高度。
- 新组件提取可能破坏 per-item draft 恢复、保存失败重试或 current item baseline
  refresh，focused tests 必须先锁定这些行为。

## Rollback

若 implementation 引入不可接受的布局或 draft 回归，回退新增
`SipInformationPanel` / `SelectedSipDetailFields` 接线，恢复：

- metadata UI 位于 `auxiliaryPanel`；
- selected SIP fieldset 位于 `InspectionItemTable`；
- 原辅助浮层按钮文案。

rollback 后第一项验证是运行现有
`InspectionItemTable.test.tsx`、`InspectionWorkbench.test.tsx` 和
`PdfWorkspace.test.tsx`，确认原路径恢复且 export 状态未受影响。
