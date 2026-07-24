# Merged Inspection Review Workspace Design

## Context

当前 `inspection-pane` 先展示检验项汇总和列表，再在列表下方展示独立的
`candidate-editor`。用户选择检验项后，需要在同一页面上下移动才能在列表与编辑
表单之间切换。所有 Review command 还会先进入 `pendingCommand`，最后依赖页面顶部
的“保存审核修改”统一提交。

本设计把检验项列表与当前项编辑器收敛为一个双栏审核工作区，并取消额外的顶部
保存步骤。该变化只调整 frontend executor 的布局和显式提交方式，不改变 Review
aggregate、Review command schema、working-copy version、审核状态或后端 API。

## Goals

- 在同一可视区域同时展示检验项列表和当前项编辑器。
- 切换检验项时不再引起整页纵向跳动。
- 保留列表筛选、选中、PDF 联动、合并、拆分和八类 Review command。
- 移除顶部“保存审核修改”按钮。
- 将现有“修改”改为“修改保存”，将“取消检验项修改”替换为进入编辑状态的
  “修改”。
- 让每一个明确的审核动作直接通过现有 `onSave(command)` 提交。

## Non-Goals

- 不改变后端 Review command、API route、schema 或 operation log。
- 不改变候选项、正式项、气泡要求或审核状态的业务语义。
- 不重设计 PDF workspace、SIP metadata、export 或 balloon toolbar。
- 不增加自动保存、批量后台提交、草稿恢复或新的持久化层。
- 不重写 `frontend/e2e/chinese-pdf-upload-mvp.spec.ts` 的 PDF、balloon 或 export
  流程。设计阶段该文件的未提交改动不得覆盖；implementation-plan preflight 已确认
  这些改动后来独立提交到 `6f4cd6a` 且文件恢复 clean，因此只允许把旧
  “action → 顶部 Save” helper 最小改为“action 直接提交”。

## Selected Layout

`RecognitionSummary` 继续位于审核区顶部。其下新增一个固定在当前可视高度内的
双栏工作区：

- 左栏拥有搜索、状态筛选、紧凑检验项列表和列表分页。
- 右栏拥有当前项摘要、字段表单、拆分输入和审核命令。
- 左右两栏分别使用内部滚动，不把长列表或长表单继续传递为页面级高度。
- 左栏使用紧凑的“序号 / 检验项 / 状态”信息层级；数值、公差、页码等完整信息
  继续出现在右栏当前项摘要与表单。
- 选中待判定来源时，现有来源处理 UI 保持可用，并限制在左栏内部滚动区域，不改变
  其 command 语义。
- 窄屏不能容纳双栏时，工作区回退为上下两段；不再恢复列表下方第二套
  `candidate-editor`。

## Edit State

当前检验项有两个显式状态：

1. `view`
   - 表单字段只读。
   - “修改”可用。
   - “修改保存”不可用。
2. `edit`
   - 点击“修改”后，当前项字段和拆分输入可编辑。
   - 有有效变更时，“修改保存”可用。
   - “修改保存”直接提交 `edit` command；成功后回到 `view`。

该状态机只约束已选中检验项的字段和拆分输入；合并选择与新增检验项继续使用各自
现有的显式输入和提交动作。

编辑状态下不提供“取消检验项修改”。若当前项存在未提交修改，选择其他检验项不应
静默丢弃草稿；当前选择保持不变，直到“修改保存”成功。若尚未产生字段变更，切换
检验项会直接退出当前编辑状态。

## Direct Command Submission

移除 `InspectionWorkbench` 的 `pendingCommand` 队列和顶部
`review-actions` 保存按钮。新增单一 frontend submit path：

```text
explicit local action
→ submitCommand(command)
→ existing onSave(command)
→ existing workbench refresh
→ success or failure status
```

下列动作均通过该 path 直接提交：

- 保留、排除；
- 修改保存；
- 确认候选项、拒绝候选项；
- 设为需要气泡、设为无需气泡；
- 合并、拆分、新增检验项；
- 待判定来源的添加或忽略；
- SIP detail 和 SIP metadata 的现有明确确认动作。

不存在 timer、effect 或输入事件触发的自动 POST。一个 command 提交期间，
`saving` 禁止重复命令和其他 review mutation。成功后显示现有“已保存”状态；失败
后显示“保存失败”，保留当前编辑值和 dirty state，允许用户重试。

## Component Boundaries

`InspectionWorkbench`

- 拥有单一 `saving` 和 save-status state。
- 拥有 `submitCommand()`，并把它传给现有 command producers。
- 组合新的双栏容器并阻止 dirty edit 时切换选中项。
- 不产生或解释正式 Review 业务语义。

`InspectionItemTable`

- 继续拥有搜索、筛选后的列表呈现、分页、待判定来源和 SIP detail 输入。
- 增加紧凑 master-list 呈现，不复制第二套列表状态。
- command 成功前不清除本地 dirty state。

`ReviewPanel`

- 继续拥有当前项字段 draft、合并、拆分、新增和 Review command 构造。
- 增加 `view / edit` 呈现。
- command 成功后才清除对应 draft；失败时保持可重试状态。

`zhCN` 和 `workbench.css`

- 文案只新增或替换用户已确认的“修改保存”“修改”状态文字。
- 样式只实现双栏、内部滚动、紧凑列表和响应式回退。

## Accessibility

- 双栏仍使用明确的 region、heading、table/list 和 form label。
- “修改”与“修改保存”的 accessible name 包含当前检验项原始标注。
- 提交期间使用现有 disabled 和 live status，避免重复动作。
- 只读字段使用真实 `disabled` 或 `readOnly` 状态，不仅依赖颜色表达。
- dirty edit 阻止切换时，保存状态区域应提供可读提示。

## Verification

按 TDD 顺序增加 focused coverage：

- `InspectionWorkbench.test.tsx`
  - 不再渲染“保存审核修改”。
  - 显式 Review action 直接调用 `onSave`。
  - 提交期间阻止第二个 command。
  - 失败时显示失败状态并允许重试。
  - dirty edit 时不切换当前项。
- `ReviewPanel.test.tsx`
  - 默认字段只读。
  - “修改”进入 edit。
  - “修改保存”仅在有效 dirty state 下可用并产生 `edit` command。
  - 不再渲染“取消检验项修改”。
- `InspectionItemTable.test.tsx`
  - 紧凑列表只呈现选定的信息层级。
  - 本地 dirty state 在 command 失败时不被清除。

完成 focused tests 后运行 frontend test suite 和 build。最后按
`auto-feature-smoke-test` 在真实 localhost Workbench 中验证：

1. 列表和编辑器同时出现在一个固定高度工作区。
2. 左右栏能够独立滚动，切换项目时页面不跳动。
3. “修改 → 修改保存”成功刷新当前项。
4. 保留或排除能够直接提交，不再需要顶部保存按钮。
5. 浏览器 console 没有当前变化导致的新 error。

## Execution Selection

- Selected lane: `Standard`。变化仍限于一个 frontend feature group，未改变稳定
  API/schema 或业务 Owner；但需要多组件协作、focused tests 和真实浏览器 smoke。
- Selected plan: 本设计完成书面复核后生成的 implementation plan 将成为本 UI
  refinement 的唯一 execution plan；现有七天 P0 plan 继续作为 P0 contract 和
  已有 Day/Task 事实来源，不修改其执行状态。
- Selection evidence: 当前代码中 `InspectionItemTable` 与 `ReviewPanel` 纵向分离，
  `pendingCommand` 依赖顶部“保存审核修改”；用户确认使用 A 双栏方案、双栏独立
  滚动和“先修改、再修改保存”。
- Validation action: `amend` frontend presentation and explicit-submit path；不
  replan Review aggregate 或后端 contract。
- Writer ownership and order: 主 agent 是唯一 writer；实现后使用一个只读 reviewer
  独立检查 diff、提交语义和 focused evidence。
- Next verification: 先运行新增 focused test 的 RED，随后才允许修改 production
  frontend code。

## Risks

- 直接提交改变 frontend 的交互节奏。通过沿用同一个 `onSave(command)`、
  单 command in-flight 和失败保留草稿限制风险。
- 双栏在窄 inspection pane 中可能压缩字段。通过紧凑列表和响应式单栏回退避免
  横向溢出。
- dirty edit 与列表切换可能造成误丢数据。通过阻止 dirty selection change 保证
  不静默丢弃。
