# Source Review Convergence Design

**Status:** Approved on 2026-07-24; batch-confirmation amendment approved on
2026-07-29; automatic-source-default amendment approved by user on 2026-07-31

## 2026-07-31 Automatic-Source-Default Amendment

用户明确要求移除前台“待确认来源 / 确认当前有效项”批量确认条，并将该批量动作改为
后台默认执行。本 amendment supersedes 2026-07-29 对“必须由用户二次确认、不得静默
执行”的产品选择，但保留以下边界：

- immutable `AutomaticResult.coverage` 继续保存原始 `ambiguous` source-only evidence；
- `ReviewService.create_from_raw()` 是初始 working-copy projection 的唯一 Owner，
  使用 `review-source-default/1` 将 `requires_confirmation=true`、
  `candidate_id=null` 且 source 不属于 technical requirement 的 entry 默认投影为
  `non_inspection`；technical requirement source 继续保持 pending 并阻断 freeze；
- working-copy entry 保留原 source、coordinates、原 disposition reason，并新增
  `resolution_source=system_default` 与
  `resolution_rule_version=review-source-default/1`；
- 只重算 working-copy `review_required_count`，不修改 item-set、numbering、freeze、
  balloon、SIP、reviewed result 或 export；
- frontend 删除 batch bar、inline confirmation、batch copy 与专属 CSS，不再发送
  `ignore_sources`；legacy pending source 的逐条 correction 与 public review command
  schema 暂不删除；
- 已经存在的 working copy 不通过 GET 或 frontend effect 隐式写入，使用现有
  `ignore_sources` command 做一次可审计收口。

### Amendment Execution Selection

- **Selected lane:** `Heavy`
- **Selected plan:**
  `docs/superpowers/plans/2026-07-31-automatic-source-disposition.md`
- **Selection evidence:** 该变更替换人工 source-only 决策路径，并改变 Coverage
  Ledger 到 working-copy 的 data-integrity / workflow contract。
- **Validation action:** `replan`
- **Single owner:** `ReviewService.create_from_raw()` /
  `ReviewService._review_coverage()` 拥有初始 working-copy system-default projection；
  `ReviewService.apply()` 继续独占后续人工 command mutation。
- **Old path action:** `remove` frontend batch confirmation；`preserve` public
  `promote_source` / `ignore_source(s)` schema 和 service branches，因为仍有 tests、
  existing working-copy convergence 与非 UI consumers。
- **Rollback:** 回滚 amendment code/docs commit 后恢复 frontend batch confirmation；
  第一项验证为 source-only freeze blocker regression。
- **Writer ownership and order:** 父 agent 是唯一 writer；只读 explorer/reviewer
  不修改文件。
- **Next verification:** backend bootstrap RED，再 frontend batch-bar removal RED。

## Problem Statement

当前 `source-only coverage` 没有进入检验项列表，而是在列表上方显示一套独立的
“来源待确认”卡片。用户必须通过“上一条来源 / 下一条来源”逐条处理；真实项目可能
出现 `2 / 166` 这类长队列。

这个界面不仅重复了检验项审核，还暴露了内部 Coverage Ledger 概念。更严重的是，
当前“确认保留此来源”只会清除 `requires_confirmation` 并记录
`confirmation_accepted=true`，不会创建 `ReviewItem`。正式导出只消费 active
`reviewed.items`，因此用户看到的“保留”不等于该内容进入 SIP Excel 或气泡流程。

目标是收敛为一条审核路径：

- 所有待判断来源和普通检验项都出现在同一个检验项列表；
- 来源只能被明确“添加为检验项”或“忽略，不作为检验项”；
- 添加与 Coverage Ledger 更新必须在一个后端事务内完成；
- 所有待判断来源解决前，现有 freeze Veto Gate 继续阻止冻结。

## Execution Selection

- **Selected lane:** `Heavy`
  - 本设计新增稳定 review command schema，并跨 frontend、review aggregate 和
    Coverage Ledger data-integrity boundary 改变行为。
- **Selected plan:** 本设计对应的新 implementation plan；多 PDF 设计保持暂停，
  不属于本任务。
- **Selection evidence:** 当前独立卡片发送 `resolve_confirmation`；后端仅翻转确认
  状态，而 export 只读取 `reviewed.items`。
- **Validation action:** `replan`
  - 目标和 Owner 明确，但现有命令无法原子表达“来源转检验项”。
- **Writer ownership and order:** 父 agent 是唯一 writer；backend command 与
  frontend consumer 按 TDD 顺序串行修改；reviewer 只读。
- **Next verification:** review command contract/integration tests，然后 frontend
  component tests，最后 authenticated localhost Chrome smoke。

### 2026-07-29 Batch Amendment Selection

- **Selected lane:** `Heavy`
  - 新增稳定 `ignore_sources` command schema，并跨 frontend、Review aggregate 与
    Coverage Ledger data-integrity boundary 提交批量 disposition。
- **Selected plan:** `docs/superpowers/plans/2026-07-24-source-review-convergence.md`
  的 batch-confirmation amendment。
- **Selection evidence:** 用户确认待判定来源大部分是无需纳入的识别噪声，批准保留
  当前有效项并一次性排除全部剩余 pending source。
- **Validation action:** `replan`
  - 原 spec 明确排除 batch ignore，必须原地修订，不能静默扩大 scope。
- **Current-plan boundary:** 最新用户目标临时选择本 plan；confidence-routed plan
  保持现有 commits，不在本任务继续推进，也不回滚。
- **Single owner:** `ReviewService.apply()` / `_apply_command()` 继续是唯一 mutation
  Owner；不新增 endpoint、frontend loop 或第二套 batch executor。
- **Writer ownership and order:** 父 agent 串行修改 docs → backend contract/service
  → frontend consumer；独立 reviewer 只读。
- **Next verification:** schema RED/GREEN → service atomicity RED/GREEN → frontend
  interaction RED/GREEN → focused/full tests → Chrome smoke → independent review。

## Confirmed Product Decisions

- 删除独立“来源待确认”卡片和它的上一条/下一条导航。
- 待判断来源作为特殊行进入现有检验项列表，状态显示“待判定来源”。
- 顶部“全部”计数包含待判断来源；“需人工处理”计数和筛选也包含待判断来源。
- 选择待判断来源时，图纸跳转到对应页并高亮真实来源框。
- 列表下方的同一详情区域显示来源处理表单，不新增第二个审核面板。
- “添加为检验项”必须真正创建 active `ReviewItem`。
- “忽略，不作为检验项”必须把 Coverage Ledger disposition 改为
  `non_inspection`。
- 添加为检验项时，用户必须显式选择检验类型；系统不猜测默认类型。
- 用户可在粗略检查后选择“确认当前有效项”，把所有仍待判定的 source-only
  entries 在一个事务内批量标记为 `non_inspection`。
- 批量确认必须先显示将保留的 active item 数和将排除的 pending source 数，并要求
  用户二次确认；不得静默执行。
- 批量确认只解决 pending source，不自动 freeze、生成气泡或确认 reviewed result。
- 逐条“添加为检验项”继续作为少量漏识别内容的纠错入口。
- 现有 `requires_confirmation` freeze Veto Gate 保持不变。

## Goals

1. 让用户只维护一套审核列表、筛选、分页和选择状态。
2. 消除“界面显示保留，但正式输出没有检验项”的语义错位。
3. 保证来源处理、item-set 和 coverage 在同一事务中一致更新。
4. 保留 source identity、PDF 坐标、页码和 operation audit。
5. 不影响普通 candidate 的 keep/exclude/edit/confirmation 行为。
6. 允许用户以一次显式、可审计的批量决定排除明显的非检验来源噪声。

## Non-Goals

- 不改变自动识别、OCR、Vision Advisor 或 Coverage Owner 的判定逻辑。
- 不自动批量忽略水印、公司名、标题栏或其他文本。
- 不增加模型调用或后台自动分类。
- 不改变 frozen working copy、immutable reviewed result 或已发布文件。
- 不实现 undo、批量添加、按类型批量纳入、混合 decision payload 或新的审核角色。
- 不根据文本内容自动选择要忽略的来源；本次批量操作始终覆盖当前全部 pending
  source，并由用户显式确认。
- 不推进或修改多 PDF 项目设计。
- 不改变气泡编号、碰撞、SIP 字段确认或正式导出格式。

## Current Root Cause

`CoverageEntry(disposition="ambiguous", candidate_id=None,
requires_confirmation=true)` 是 Coverage Ledger 中的待判断来源，不是
`ReviewItem`。Frontend 因此在 `CoverageReviewPanel` 中单独投影这些 entry。

当前两个按钮都发送：

```text
resolve_confirmation(item_id=observation_id, accepted=<bool>)
```

`ReviewService` 对 coverage entry 只执行：

```text
requires_confirmation = false
confirmation_accepted = accepted
```

它既不改变 `disposition`，也不创建 item。freeze 只检查未解决 confirmation，因此
“确认保留”能够解锁冻结，却不会让该来源进入 reviewed item-set。

## Alternatives Considered

### A. 只删除独立卡片，继续使用 `resolve_confirmation`

改动最小，但只是隐藏问题。“保留”仍不会创建检验项，并且没有入口处理
source-only blocker。拒绝。

### B. Frontend 连续发送现有 `add` 和 `resolve_confirmation`

无需新增 command schema，但两次请求之间存在 version conflict、网络失败和锁过期
窗口。可能出现 item 已新增但 coverage 仍待确认，或 coverage 已解决但 item 未新增。
该方案不满足原子性。拒绝。

### C. 新增显式、原子的来源审核命令

采用 `promote_source` 和 `ignore_source` 两个命令。每个命令只产生一个 working-copy
version 和一个 operation record，后端在同一事务内更新 item-set 与 coverage。
这是选定方案。

### D. Frontend 循环发送 `ignore_source`

第一条命令成功后 working-copy version 已递增，后续命令仍使用旧 snapshot version，
会产生 `review_version_conflict`。即使逐条刷新 version，也可能部分成功，不能把
326 条来源表示为一个审计决定。拒绝。

### E. 新增 `ignore_sources` 原子批量命令

继续复用现有 `POST /review/commands` 和 `ReviewService.apply()` Owner，用一个
`expected_version`、一个 transaction、一次 version increment 和一条 operation
record 提交全部 pending source disposition。任何目标重复、缺失、已处理或
candidate-backed 时整批失败。这是 2026-07-29 amendment 的选定方案。

## Backend Command Design

### `promote_source`

Request:

```json
{
  "type": "promote_source",
  "observation_id": "stable-observation-id",
  "raw_text": "M16",
  "item_type": "thread",
  "scope": "local_feature",
  "balloon_required": true,
  "page_index": 0
}
```

Validation:

- `observation_id` 必须唯一命中 working copy 中一个
  `requires_confirmation=true` 的 coverage entry；
- entry 必须是 `candidate_id=null` 的 source-only entry；
- `raw_text` 去除首尾空白后不得为空；
- `item_type`、`scope`、`balloon_required` 和 `page_index` 使用现有 manual add
  约束；
- item coordinates 必须使用服务端 coverage entry 的 coordinates，不接受客户端
  覆盖；
- item source relation 必须使用 entry 的 `source_location_id`。

Atomic effects:

1. 创建 UUID `item_id` 的 active `ReviewItem`；
2. item 保存用户确认的 `raw_text`、类型、scope、balloon requirement 和页码；
3. item 保存 coverage coordinates 和原始 `source_location_id`；
4. item `source_type="manual"`、`status="pending"`、
   `requires_confirmation=false`；
5. coverage entry 改为 `disposition="candidate"`、
   `candidate_id=item_id`、`requires_confirmation=false`、
   `confirmation_accepted=true`；
6. 重算 `review_required_count`；
7. `numbering_stale=true`；
8. 写入一个 `promote_source` operation record。

### `ignore_source`

Request:

```json
{
  "type": "ignore_source",
  "observation_id": "stable-observation-id"
}
```

Validation 与 `promote_source` 使用同一个 source-only eligibility guard。

Atomic effects:

1. 不创建 `ReviewItem`；
2. coverage entry 改为 `disposition="non_inspection"`、
   `candidate_id=null`、`requires_confirmation=false`、
   `confirmation_accepted=false`；
3. 重算 `review_required_count`；
4. numbering state 不变；
5. 写入一个 `ignore_source` operation record。

### `ignore_sources`

Request:

```json
{
  "type": "ignore_sources",
  "observation_ids": ["source-1", "source-2"]
}
```

Validation:

- `observation_ids` 至少一项、每项非空且不得重复；
- 每个 identity 必须唯一命中一个 `requires_confirmation=true`、
  `candidate_id=null` 的 source-only coverage entry；
- 必须先校验全部 identities，再更新任何 entry；
- 不接受 filter、page、文本匹配或自动分类参数，避免 frontend 提交第二套语义。

Atomic effects:

1. 所有目标 entry 改为 `disposition="non_inspection"`、
   `candidate_id=null`、`requires_confirmation=false`、
   `confirmation_accepted=false`；
2. 不创建或修改 `ReviewItem`；
3. 一次重算 `review_required_count`；
4. numbering state 不变；
5. working-copy version 只递增一次；
6. 写入一条 `ignore_sources` operation record，`target_ids` 按 request 顺序保存；
7. 任一目标无效时 item-set、coverage、version 和 operation audit 全部不写入。

### Existing Command Boundary

`resolve_confirmation` 继续处理已经存在的 candidate/item confirmation。它不再接受
`candidate_id=null` 的 source-only observation。这样旧路径不能继续制造
“accepted 但无 item”的状态。

## Frontend Design

### Unified List Projection

`InspectionWorkbench` 从 `workingCopy.coverage.entries` 与 backend-projected
`sources` 派生 pending source rows。只有以下 entry 进入列表：

```text
requires_confirmation = true
candidate_id = null
```

普通 `ReviewItem` 和 pending source 使用同一个搜索、状态筛选、分页和 table
surface。pending source row 显示：

- 编号：`—`
- 检验项：来源原文
- 类型：`原始来源`
- 数值/公差：`—`
- 页码：真实来源页
- 状态：`待判定来源`

点击该行时清除 selected item，设置 `selectedSourceId`，跳转到来源页并高亮 source
overlay。点击普通 item 时保持现有反向清除逻辑。

### Summary And Filtering

- “全部” = review items + pending source rows；
- “需人工处理” = 现有 manual-required balloons + pending source rows；
- 选择“需人工处理”时同时显示两类记录；
- 状态下拉增加“待判定来源”。

### Source Detail Editor

选中 pending source 后，检验项列表下方的详情区域替换 SIP item detail，显示：

- 原始标注：以 backend-projected source text 预填，允许人工修正；
- 检验类型：无默认值，必须人工选择；
- 范围：默认 `local_feature`；
- 需要气泡：默认是；
- 来源页码：只读；
- 主操作：`添加为检验项`；
- 次操作：`忽略，不作为检验项`。

“添加为检验项”只有在原始标注非空且已选择类型时可用。两个操作都进入现有
pending command + 显式“保存审核修改”流程；保存成功后 backend 新 working-copy
projection 使该 pending source row 消失。按钮文案不再使用“保留来源”。

### Batch Confirmation

当 `pendingSources.length > 0` 时，统一列表顶部显示一条 batch decision bar：

- 状态文案：`N 条待确认来源`；
- 主操作：`确认当前有效项`；
- 点击后显示 inline confirmation，不使用 browser-native confirm；
- confirmation 明确写出：保留当前 active item 数，并把全部 `N` 条待确认来源排除；
- warning 明确说明被排除内容不会进入 SIP，也不会生成气泡；
- 最终操作：`确认排除 N 条`；取消操作关闭 confirmation，不提交命令。

最终操作只发送一次：

```json
{
  "type": "ignore_sources",
  "observation_ids": ["当前全部 pending source observation IDs"]
}
```

成功 refresh 后 pending rows 与 batch bar 同时消失；失败时保留 confirmation、
selection 和 draft，继续显示现有保存失败状态。存在未保存 source draft 时 batch
操作 disabled，避免静默丢弃人工修改。

顶部 summary 在 pending source 存在时使用“待确认来源”并只显示 pending source
数，不再把 pending source 与生成后的 balloon `manual_required` 合并成一个数字。
pending source 清零后，该 chip 恢复现有气泡“需人工处理”语义。本 amendment 不改变
placement Owner。

### Old Path Retirement

同一实现提交中删除：

- `CoverageReviewPanel.tsx`
- `CoverageReviewPanel.test.tsx`
- `coverage-review.css`
- `InspectionWorkbench` 中的独立 panel import/render
- `zhCN.coverageReview` 文案

不得保留隐藏入口、feature flag、fallback 或第二套 source review navigation。

## Error Handling

- working-copy version conflict、锁过期、items frozen 和 save failure 继续使用现有
  review API 错误路径；
- source entry 不存在、已经处理、不是 source-only 或不再待确认时，命令失败且整个
 事务不写入；
- batch 中任一 identity 无效或重复时整批失败，不能保留部分 disposition；
- promotion 字段验证失败时不改变 item-set、coverage 或 version；
- frontend 保存失败时保留选中来源和编辑内容，显示现有“保存失败”状态；
- 未解决 source row 始终保持 freeze blocker，不能用 warning 或 UI 隐藏绕过。

## Data Integrity And Invariants

- 一个 source-only observation 最多被 promote 或 ignore 一次；
- 一个 `ignore_sources` command 只能包含唯一 observation identities；
- batch mutation 前必须完成全量 eligibility validation；
- promoted item 与 coverage entry 共享同一 source identity 和服务端坐标；
- promote 后 coverage disposition 是 `candidate`，并指向新 item identity；
- ignore 后 coverage disposition 是 `non_inspection`，且没有 candidate identity；
- `review_required_count` 必须等于仍为 `requires_confirmation=true` 的 coverage
  entry 数量；
- 未处理 source-only entry 继续阻止 freeze；
- 只有 active items 进入 reviewed result 和正式 export。

## Allowed Paths

Backend:

- `backend/app/review/schemas.py`
- `backend/app/review/service.py`
- `backend/tests/contract/test_review_schema.py`
- `backend/tests/integration/test_review_operations.py`
- `backend/tests/integration/test_review_freeze.py`

Frontend:

- `frontend/src/api/types.ts`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/components/workbench/RecognitionSummary.tsx`
- `frontend/src/components/workbench/RecognitionSummary.test.tsx`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/components/review/CoverageReviewPanel.tsx`（删除）
- `frontend/src/components/review/CoverageReviewPanel.test.tsx`（删除）
- `frontend/src/styles/coverage-review.css`（删除）
- `frontend/src/styles/workbench.css`

Plan and durable contract projection:

- 本 spec 对应的新 implementation plan
- `docs/contracts/MAIN_CONTRACT_MATRIX.md`（只在 plan 明确要求时细化 `REV-004`）

不得修改 processing、OCR、Provider、balloon、export、多 PDF 或数据库 migration
文件。

## TDD And Verification

### Backend RED/GREEN

1. Contract test：`promote_source` 与 `ignore_source` schema 接受合法 payload、拒绝
   多余或缺失字段。
2. Integration test：promote 原子创建 active item、复用服务端 coordinates/source、
   更新 coverage、计数和 `numbering_stale`。
3. Integration test：ignore 不创建 item，更新 `non_inspection` 和计数，编号状态不变。
4. Failure test：已处理、candidate-backed 或不存在的 observation 不得改变
   working copy。
5. Regression test：旧 `resolve_confirmation` 不再解决 source-only entry；普通 item
   confirmation 保持通过。
6. Freeze test：任一 pending source 仍阻止 freeze，promote/ignore 后只在其他 blocker
   也清零时允许继续。

### Frontend RED/GREEN

1. pending source 出现在检验项 table，独立“来源待确认”region 不存在。
2. source row selection 跳页并高亮来源；item selection 仍正确。
3. “需人工处理”和“全部”计数、筛选包含 pending source。
4. promotion editor 强制选择类型，并生成正确 `promote_source` command。
5. ignore 生成正确 `ignore_source` command。
6. 保存失败保留 source draft；保存成功由新 projection 移除该行。
7. 普通 item table、SIP detail、分页和 finalized read-only regression 保持通过。
8. batch confirmation 只发送一个 `ignore_sources` command，并包含全部 pending
   observation IDs。
9. batch cancel 不发送命令；失败保留 confirmation；成功 projection 移除全部
   pending rows。
10. backend batch success 只递增一次 version、只写一条 operation record；任一无效
    target 时验证 working copy 与 audit 零写入。

### Required Checks

```text
pytest backend/tests/contract/test_review_schema.py -q
pytest backend/tests/integration/test_review_operations.py -q
pytest backend/tests/integration/test_review_freeze.py -q
cd frontend && npm test -- --run src/components/workbench/RecognitionSummary.test.tsx
cd frontend && npm test -- --run src/components/workbench/InspectionItemTable.test.tsx
cd frontend && npm test -- --run src/components/workbench/InspectionWorkbench.test.tsx
cd frontend && npm run build
```

最后使用现有 localhost runtime 和一个真实 pending-source working copy 执行 Chrome
smoke：

1. “来源待确认”独立卡片不存在；
2. pending source row 可在统一列表中找到并选择；
3. 选择后真实来源框高亮并跳到正确页；
4. promote/ignore 进入显式保存流程；
5. 保存后 row 与待处理计数同步更新；
6. freeze blocker 与 backend working-copy projection 一致。

## Rollback

本设计不需要 migration。若 batch amendment 引入回归，只回滚 amendment
implementation commit，恢复逐条 `promote_source` / `ignore_source` 路径；不得回滚
已经完成的 unified source review convergence，也不得恢复 `CoverageReviewPanel`。

发生 rollback 后第一项验证是：

```text
pytest backend/tests/integration/test_review_freeze.py::test_source_only_confirmation_blocks_freeze -q
```

它只证明旧 freeze safety boundary 恢复，不代表旧“保留来源”语义正确。
