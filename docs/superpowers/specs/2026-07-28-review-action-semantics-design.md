# Review Action Semantics Design

## Status

- Date: 2026-07-28
- Status: Direction approved; written specification pending user review
- Selected approach: 方案 A，按业务语义分组并常驻显示后果说明；点击“排除”后使用
  行内确认避免误操作。
- Scope: frontend presentation、local confirmation state、copy、focused tests。

## Context

当前所选检验项的操作栏把“排除”和“设为无需气泡”呈现为同一级按钮，但没有解释
两者对正式 SIP 和图纸气泡的不同影响：

- “排除”表示该条不再作为正式检验项，不进入 SIP，也不生成图纸气泡；
- “设为无需气泡”仍保留为正式检验项并进入 SIP，只是不生成图纸气泡。

用户只能从按钮名称猜测后果，容易把“不需要图纸编号”误操作成“不作为检验项”。
本设计只补足前端信息层级和防误操作反馈，不改变既有 command、backend schema、
reviewed result、freeze、export 或 numbering 语义。

## Goals

- 用户第一次看到操作栏时即可理解“排除”和“无需气泡”的区别。
- “排除”在真正提交前明确展示其对 SIP 和气泡的后果。
- 高频的“需要气泡 / 无需气泡”切换保持一次点击完成。
- 保持现有 `ReviewPanel` command producer 和父级保存流程不变。

## Non-Goals

- 不改变 `exclude` 或 `set_balloon_required` 的 backend 行为。
- 不新增 toast、全局 banner、跨页面 onboarding 或偏好设置。
- 不为“保留”“修改”“候选项确认”“拆分”等现有操作增加确认步骤。
- 不改变 SIP 字段必填规则、编号 stale 规则、freeze 或 export gate。
- 不重构 `ReviewPanel` 的其他表单或拆分布局。

## Information Architecture

`review-command-rail` 保持位于所选检验项表单右侧，但内部按钮按三个语义分区排列：

1. `检验结论`
   - `保留`
   - `排除`
2. `内容调整`
   - `修改`
   - `修改保存`
   - `确认候选项`
   - `拒绝候选项`
3. `气泡标记`
   - `设为需要气泡`
   - `设为无需气泡`

“检验结论”和“气泡标记”分区使用可读标题表达两组操作不是同一维度。原有按钮
顺序在各自分区内保持不变。

### Persistent Helper Copy

说明文字必须紧贴产生歧义的按钮，不放在页面顶部或依赖悬浮提示：

- `排除` 下方：`不进入 SIP，也不生成气泡`
- `设为无需气泡` 下方：`仍进入 SIP，仅不生成图纸气泡`

说明始终可见，不只在 hover、focus 或首次访问时出现。它们是解释性文案，不替代
按钮的 accessible name。

## Exclude Confirmation

第一次点击当前检验项的“排除”时，不立即发送 command，而是在“检验结论”分区内
显示行内确认块：

- 标题：`确认排除这条检验项？`
- 后果：`排除后不会进入正式 SIP，也不会生成图纸气泡。原始识别记录仍保留。`
- 操作：`取消`、`确认排除`

只有点击“确认排除”才调用现有：

```text
onCommand({
  type: "exclude",
  item_id: selectedItem.item_id
})
```

点击“取消”只关闭确认块，不提交 command。切换所选检验项时清除待确认状态，避免把
上一条的确认意图带到下一条。提交期间使用 local pending state 禁止重复确认；父级
进入 `disabled` 状态时，确认按钮同步禁用。

“设为无需气泡”继续直接发送现有 `set_balloon_required` command，不增加确认步骤。

## Component Ownership

### `ReviewPanel`

- 继续拥有所有检验项操作按钮和现有 `onCommand` producer。
- 新增只服务于行内确认的 local UI state，以当前 `item_id` 标识待确认项。
- 新增只覆盖 `exclude` await 周期的 local pending state，防止重复 command。
- 在 selection 变化或确认/取消后清理该 state。
- 不复制 working copy，不推断 SIP/export 状态，不成为业务语义 Owner。

### `zhCN`

- 拥有新分区标题、两条常驻说明和排除确认文案。
- 业务后果文案必须与现有 backend/export 语义一致，不创建新的状态名称。

### `workbench.css`

- 只负责现有 command rail 内的分区、说明和确认块布局。
- 不改变页面级 grid、右侧详情宽度或 responsive breakpoint。

## Interaction And Error Behavior

- 点击“确认排除”后等待现有 `onCommand` 结果，并沿用父级 saving/disabled 行为。
- `onCommand` 明确返回 `false` 时保留确认块，允许用户在父级错误反馈后重试；不得在
  `ReviewPanel` 伪造成功。
- `onCommand` 成功或没有显式返回失败时关闭确认块，working-copy refresh 决定最终
  按钮和条目状态。
- 如果用户在确认前切换条目，确认意图直接作废，不自动提交。
- frozen、reviewed、saving 或 busy 等现有 disabled 状态继续阻止所有相关操作。

## Accessibility

- 三个操作分区使用 `fieldset` 和 `legend`，或等价的可访问分组结构。
- 行内确认块使用 `role="alertdialog"`，并通过 `aria-labelledby` 和
  `aria-describedby` 关联标题与后果说明。
- 打开确认块后，把焦点移动到“取消”或“确认排除”；关闭后把焦点返回“排除”按钮。
- `Escape` 在尚未提交时关闭确认块且不提交；提交 pending 期间不撤销已发送 command。
- 不只依赖红色、图标、hover 或 disabled 状态表达危险性。
- 现有按 item 原文构造的按钮 `aria-label` 保持不变。

## Responsive Layout

- 宽屏下维持当前右侧竖向 command rail。
- 窄屏下沿用现有 breakpoint 将 command rail 收敛到表单下方。
- 分区标题、说明和确认块允许自然换行，不设置固定高度。
- 不使用 tooltip 作为唯一说明，也不通过负 margin 或固定截图坐标压缩空间。

## Verification

### Focused Component Tests

`ReviewPanel.test.tsx` 覆盖：

- “排除”和“无需气泡”的后果说明始终可见；
- 操作按钮位于正确的可访问分组；
- 首次点击“排除”不发送 command；
- 点击“取消”不发送 command并关闭确认块；
- 点击“确认排除”只发送一次现有 `exclude` payload；
- command 明确失败时保留确认块，并允许单次重试；
- 切换 selected item 清除上一条的确认状态；
- `Escape` 关闭确认块；
- “设为无需气泡”仍一次点击发送现有 payload；
- disabled 状态下不能确认排除。

### Static And Build Checks

```bash
cd /home/reggie/vscode_folder/Quality_Inspection/frontend
npm test -- --run src/components/review/ReviewPanel.test.tsx
npm run build
```

### Browser Smoke

在真实 workbench 中验证：

- 宽屏和窄屏均能看到两条常驻说明；
- 点击“排除”只打开行内确认，不立即改变条目；
- 取消、确认、切换条目和键盘 `Escape` 行为正确；
- “无需气泡”仍直接生效，条目继续保留在 SIP；
- 确认块不会遮挡 SIP 表单、检验项列表或页面滚动。

## Workflow Selection

- Selected lane: `Lite`
- Selected plan: 尚未创建；用户已批准方案 A，书面 spec 审阅后进入 implementation
  plan。
- Selection evidence: 变更限于单个 frontend 操作栏及其 copy/style/test，不改变稳定
  API、schema、runtime configuration、权限或跨模块 data-integrity boundary。
- Validation action: focused `ReviewPanel` tests、frontend build、真实 workbench browser
  smoke。
- Writer ownership and order: 单一 frontend writer；先测试，再实现，再执行 focused
  review。现有已完成 reviewer agents 不拥有本任务文件。
- Next verification: 用户审阅本 spec 后，为上述四个 frontend 文件创建 implementation
  plan。
