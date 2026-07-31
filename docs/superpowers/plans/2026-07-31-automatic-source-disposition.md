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
