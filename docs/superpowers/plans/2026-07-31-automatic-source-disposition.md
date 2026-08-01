# Automatic Source Disposition Implementation Plan

## Goal

将“确认当前有效项并排除全部待确认来源”从 frontend 人工 batch action 收敛为
backend working-copy bootstrap 默认行为，同时保留 immutable raw coverage 和可追溯
system-default rule provenance。

## Contract

- Selected lane: `Heavy`
- Spec:
  `docs/superpowers/specs/2026-07-24-source-review-convergence-design.md`
  的 `2026-07-31 Automatic-Source-Default Amendment`
- Stable contract:
  `docs/contracts/MAIN_CONTRACT_MATRIX.md` 的 `CAND-005`、`REV-004`
- Owner before:
  `ReviewService.apply()` 只在 frontend 发送 `ignore_sources` 后提交 source disposition
- Owner after:
  `ReviewService._review_coverage()` 在初始 working-copy projection 中提交
  `review-source-default/1`，但排除 technical requirement source；
  `ReviewService.apply()` 保留后续人工 override Owner
- Old path:
  remove frontend batch bar/state/copy/CSS；preserve public source command schema 和
  service branches
- Unchanged:
  raw automatic evidence、candidate/item confirmation、legacy pending-source correction
  command contract、numbering、freeze、balloon、SIP、reviewed result、export
- Rollback:
  revert this amendment implementation；第一项验证：
  `test_source_only_confirmation_blocks_freeze`

## Allowed Paths

- `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- `docs/superpowers/specs/2026-07-24-source-review-convergence-design.md`
- `docs/superpowers/plans/2026-07-31-automatic-source-disposition.md`
- `backend/app/review/service.py`
- `backend/tests/integration/test_review_working_copy.py`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/styles/workbench.css`
- `frontend/e2e/inspection-list-compact-style.spec.ts`
- `design-qa.md`

## Task 1 — Backend RED/GREEN

1. 在 `test_review_working_copy.py` 新增真实 bootstrap regression：
   source-only pending 自动成为 `non_inspection`，candidate-linked pending 保持待审核，
   technical requirement source 保持待审核且继续阻断 freeze，raw coverage 不变，并保存
   exact rule provenance。
2. 运行单测并确认旧实现因 source-only 仍为 pending 而 RED。
3. 在 `_review_coverage()` 实现一个版本化 system-default projection。
4. 运行 focused working-copy、freeze 和 review-operation tests。

## Task 2 — Frontend RED/GREEN

1. 将既有 batch-confirmation component test 改为：即使收到 legacy pending source，
   也不渲染“待确认来源”bar 或“确认当前有效项”按钮，source row/correction seam 保持。
2. 运行 focused test 并确认旧实现 RED。
3. 删除 batch state/render、专属 copy/CSS 和只测试该 bar 的 E2E fixture/assertions。
4. 运行 `InspectionItemTable`、`InspectionWorkbench`、`RecognitionSummary` focused
   suites 和 frontend build。

## Task 3 — Runtime Convergence And Smoke

1. 在真实项目上验证当前 working copy、pending source count 和保存状态。
2. 使用现有 `ignore_sources` command 一次性收口该既有 working copy；不得通过 GET、
   frontend effect 或直接数据库更新。
3. Chrome 验证 batch bar/button 为 0、检验项三列无横向滚动、console/network 正常。
4. API 验证 pending source count 为 0、operation audit/version 只增加一次，且没有触发
   freeze/generate/finalize。

## Task 4 — Review And Commit

1. 运行：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
micromamba run -n qi-p0 npm --prefix frontend run build
```

2. 独立 reviewer 检查 raw/working separation、system-default provenance、public command
   preservation、frontend old-path removal 和 runtime proof。
3. `git diff --check`，只 stage allowed paths，提交本 amendment。

## 2026-08-01 Numeric Source Visibility Amendment

### Goal And Boundary

- Selected lane: `Standard`
- Problem boundary: 黄色“待判来源”列表混入纯文字 technical requirement 来源，造成重复且低价值的人工审核噪声。
- Single Owner: `InspectionWorkbench` 的 `pendingSources` 可见列表投影。
- Old path to replace: 所有 unresolved source-only coverage 都直接进入黄色列表。
- New path: 黄色列表只展示 `rawText` 含 ASCII 数字的 unresolved source-only coverage。
- Unchanged contract: backend coverage、`manual_review_count`、technical requirement 审核、freeze、编号、气泡、SIP、public command/API 均保持不变；纯文字来源不删除，只从该列表隐藏。
- Rollback: revert 本 amendment 的前端投影过滤；第一项验证为 focused `InspectionWorkbench` regression test。

### Allowed Paths

- `.agent/bug-memory.md`
- `docs/superpowers/plans/2026-07-31-automatic-source-disposition.md`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`

### Verification

1. RED/GREEN regression：含数字来源可见，纯文字来源不在黄色列表，纯文字 technical requirement 仍在其 Owner 面板可见。
2. 运行 `InspectionWorkbench`、`InspectionItemTable`、`RecognitionSummary` focused suites。
3. 运行 frontend build。
4. 使用 Chrome MCP 做当前可达 runtime smoke；若截图项目不属于当前 runtime，明确记录 runtime identity blocker，不以其他项目冒充。
5. 独立 reviewer 检查可见性过滤没有改变 backend truth 或 freeze contract。

## 2026-08-01 Source Editor Right-Pane Amendment

### Selection

- Selected lane: `Standard`
- Selected plan: 本 plan 的 source-editor right-pane amendment
- Selection evidence: 单一 frontend review workspace，但需要组件联动、Chrome smoke 和视觉 QA；不改变稳定 API/schema、runtime config 或 backend workflow。
- Validation action: `amend`
- Writer ownership and order: 父 agent 为唯一 writer；无并发 writer。
- Next verification: 先新增“来源表单只在右侧 detail pane”回归并确认旧实现 RED。

### Goal And Boundary

- Problem boundary: 左侧列表只保留 row；选中待判来源时，来源编辑表单显示在右侧 detail pane。
- Single Owner after: `InspectionWorkbench` 负责决定右侧渲染 `ReviewPanel` 或 source editor；`InspectionItemTable` 只负责列表、分页和选择。
- Old path to retire: `InspectionItemTable` 内联渲染完整 source editor。
- Unchanged contract: `promote_source` / `ignore_source` command payload、source draft/save/return gate、数字来源过滤、technical requirement Owner、backend coverage、freeze、编号、气泡和 SIP 均保持不变。
- Rollback: 回退 right-pane composition 并恢复 table inline editor；第一项验证为本 amendment 的 focused regression test。

### Allowed Paths

- `.agent/bug-memory.md`
- `docs/superpowers/plans/2026-07-31-automatic-source-disposition.md`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/components/workbench/SourceReviewPanel.tsx`
- `frontend/src/styles/workbench.css`
- `design-qa.md`

### Required Checks

1. TDD RED/GREEN：左侧 list 容器不含 source editor；右侧 detail 容器包含并保持既有 source commands/draft behavior。
2. `InspectionItemTable`、`InspectionWorkbench`、`RecognitionSummary` focused suites。
3. frontend production build 与 `git diff --check`。
4. Chrome MCP 在同一来源选中状态验证左右 pane、无横向溢出、console error/warning 为 0。
5. 独立 reviewer 检查旧 inline path 已退役且 draft/save seams 未分叉。

### Execution Evidence

- TDD: 旧 inline owner 与 stale source selection 均先得到 focused RED，再完成 GREEN。
- Focused suites: `RecognitionSummary`、`InspectionItemTable`、`InspectionWorkbench` 共 `68/68` 通过。
- Production build: passed；仅有既有 Vite large-chunk warning。
- Independent reviewer: `accept with concerns`；无 code blocker，唯一 concern 为 Chrome visual QA 未完成。
- Chrome MCP: 两次 `list_pages` 均返回 `Transport closed`；左右 pane、overflow 与 console runtime proof 保持 `blocked`。

## 2026-08-01 Source-Disposition Residual Test Amendment

### Selection

- Selected lane: 继续沿用本 plan 的 `Heavy` contract-convergence lane。
- Validation action: `amend`；只收敛被现行 automatic-source-default contract supersede 的 integration expectations。
- Problem boundary: 完整 backend suite 中 4 个 symbol-recognition case 仍期待初始 working copy 保留 source-only pending，并继续执行旧的逐条 `promote_source` / `ignore_source` 流程。
- Single Owner: `ReviewService._review_coverage()` 继续拥有初始 working-copy system-default projection；本 amendment 只修测试契约，不改 production Owner。
- Old path to retire: visual no-detection 与 revision-marker integration test 对新 working copy 的手工 pending-source resolution 期待。
- Unchanged contract: immutable raw coverage、advisor evidence、technical requirement exemption、legacy pending-source public commands、numbering、freeze、balloon、SIP、reviewed result 与 export 均保持不变。
- Writer ownership and order: 父 agent 为唯一 writer；只读 debugger 独立核对根因，完成后由只读 reviewer 复核。
- Next verification: 将 4 个既有 RED case 改为锁定 raw/working separation、exact system-default provenance 与 settled source command rejection，再运行完整 `make test-backend`。

### Allowed Paths

- `.agent/bug-memory.md`
- `docs/superpowers/plans/2026-07-31-automatic-source-disposition.md`
- `backend/tests/integration/test_symbol_recognition_pipeline.py`

### Required Checks

1. 4 个 residual case 对新 working copy 断言 `non_inspection`、`requires_confirmation=false`、`resolution_source=system_default` 和 `resolution_rule_version=review-source-default/1`，同时证明 raw coverage 不变。
2. `promote_source` / `ignore_source` 不得把已由 system default 收口的 entry 当作 legacy pending target；legacy command behavior 继续由 `test_review_operations.py` 的真实 command tests 覆盖。
3. 运行完整 `make test-backend`、`git diff --check`，并由独立 reviewer 检查没有修改 production semantics。

### Execution Evidence

- RED: 隔离 PostgreSQL 上的完整 suite 为 `1599 passed / 4 failed`；失败仅为本 amendment 指定的 4 个 stale parametrized cases。
- Root cause: 旧 case 早于 approved automatic-source-default amendment，错误地把新 working copy 的 system-default settled entry 当作 legacy pending source；production Owner 行为未回退。
- Focused GREEN: 4 个更新后的 case 为 `4 passed / 19 deselected`。
- Full GREEN: fresh `make test-backend` 为 `1607 passed / 4 warnings`，并清理 test container/network。
- Smoke: tests-only contract convergence 未改变 API、backend runtime behavior 或 UI；`auto-feature-smoke-test` 的额外 API/Chrome smoke 不适用。
- Independent reviewer: `accept`；无 blocking issue、non-blocking concern 或建议项。
