# Optional Material And Formal Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让未标注材质不再阻断正式文件流程，并让旧项目与正式文件面板只暴露真实待处理动作。

**Architecture:** `ReviewService` 继续作为 SIP 确认和 coverage disposition 的唯一 Owner。Transport 保持五字段形状，新增四字段 required 子集；旧 working copy 在 projection、apply 和 freeze 边界复用现有 `_review_coverage` 规则归一化，frontend 只消费归一化结果并展示精确 blocker。

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, React, TypeScript, Vitest, Testing Library, pytest

## Global Constraints

- Selected lane: `Heavy`。
- Selected plan: `docs/superpowers/plans/2026-08-01-optional-material-and-formal-readiness.md`，依据用户于 2026-08-01 选择“材质可选”。
- Validation action: `replan`，因为稳定 API/schema 与跨模块 data-integrity boundary 发生改变。
- Writer ownership and order: 当前父 agent 是唯一 writer；所有现有子代理均已完成且无文件 ownership overlap。
- Unchanged contract: `set_sip_metadata`、reviewed result、manifest 和 SIP Excel 继续包含五个 metadata key；真实人工审核、气泡选择、freeze、confirm 与 atomic export 顺序不变。
- Old path to replace: 五字段全部非空校验，以及仅在 working copy 创建时执行 coverage default disposition 的路径。
- In-session approved UI prerequisite: 用户此前要求“进入检验项审核”必须产生可见反馈；该选中、聚焦和滚动交接已独立提交为 `7c3e000`，本计划在其上继续，不重复纳入当前 commit，也不改变 command 或 review owner。
- Rollback: 回退本次提交；rollback 后第一项验证为 `make check-contracts`。
- Next verification: 先运行新增 focused tests，确认因当前生产行为缺失而失败。

---

### Task 1: Optional Material Contract

**Files:**
- Modify: `backend/app/review/schemas.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/app/exports/service.py`
- Test: `backend/tests/integration/test_review_freeze.py`
- Test: `backend/tests/integration/test_review_operations.py`
- Test: `backend/tests/integration/test_result_layers.py`
- Test: `backend/tests/integration/test_export_consistency.py`
- Modify: `backend/tests/contract/snapshots/api-v1.openapi.json`
- Modify: `frontend/src/api/generated.ts`

**Interfaces:**
- Produces: `SIP_REQUIRED_METADATA_FIELDS: tuple[str, ...]` and `normalize_sip_metadata(metadata: dict[str, Any]) -> dict[str, Any]`。
- Preserves: `SIP_METADATA_FIELDS` 的五字段精确集合。

- [x] **Step 1: Write failing backend tests**

新增断言：`material: ""` 可通过 command/freeze/export，缺少 key、额外 key、空的四个 required 字段仍失败，`material: "none"` 归一化为空字符串。

- [x] **Step 2: Run tests to verify RED**

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_review_freeze.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_export_consistency.py -q
```

Expected: 空材质被现有 `NonBlankText` 或五字段非空校验拒绝。

- [x] **Step 3: Implement the minimal contract change**

保持 `material` key 必须存在且类型为字符串，只从 required nonblank 子集移除；在 command、working snapshot 与 export consumer 共用 normalization，避免 `none` 进入正式结果。

- [x] **Step 4: Regenerate and verify contract artifacts**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_openapi_contract.py backend/tests/contract/test_openapi_breaking_gate.py -q
cd frontend && npm run api:generate && npm run api:check
```

Expected: snapshot 与 generated client 一致，只有 `SetSipMetadata.material` 的 `minLength` 约束放宽，字段仍 required。

### Task 2: Legacy Coverage Convergence

**Files:**
- Modify: `backend/app/review/service.py`
- Modify: `backend/app/projects/router.py`
- Modify: `backend/app/review/router.py`
- Test: `backend/tests/integration/test_review_working_copy.py`
- Test: `backend/tests/integration/test_review_operations.py`
- Test: `backend/tests/integration/test_review_freeze.py`
- Test: `backend/tests/integration/test_project_workbench_api.py`

**Interfaces:**
- Produces: `ReviewService.normalized_coverage(raw_coverage, technical_requirements) -> dict[str, Any]`。
- Consumes: 现有 `_review_coverage` 与 `review-source-default/1`，不引入新 disposition 规则。

- [x] **Step 1: Write failing legacy projection/apply/freeze tests**

用历史 fixture 证明无 candidate、非技术要求来源从 manual count 移除并在下一次 apply/freeze 持久化；技术要求来源仍保留待确认。

- [x] **Step 2: Run tests to verify RED**

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_review_freeze.py backend/tests/integration/test_project_workbench_api.py -q
```

Expected: 历史 working copy 仍报告或阻断 source-only pending coverage。

- [x] **Step 3: Reuse the single Owner rule at all live boundaries**

`create_from_raw`、`apply`、`freeze_items`、project workbench 与 review working-copy projection 调用同一个 normalization；freeze 成功时随冻结原子持久化 coverage，失败时不产生独立写入。

- [x] **Step 4: Run focused backend tests to GREEN**

重复 Step 2 命令，Expected: PASS。

### Task 3: Exact Frontend Readiness

**Files:**
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/SipInformationPanel.tsx`
- Modify: `frontend/src/components/workbench/ExportPanel.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Test: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Test: `frontend/src/components/workbench/SipInformationPanel.test.tsx`
- Test: `frontend/src/components/workbench/ExportPanel.test.tsx`

**Interfaces:**
- Produces: `ExportPanel` props `pendingReviewCount` and `pendingBalloonDecisionCount`。
- Preserves: `canFinalize` 和 `onConfirmReview` 的原有按钮门禁与执行顺序。

- [x] **Step 1: Write failing UI tests**

覆盖材质为空仍可确认、已确认空材质不被 suggestion 回填、材质标为可选、四字段完整即 metadata confirmed，以及正式面板只统计真实 item。技术要求入口的焦点交接由 prerequisite commit `7c3e000` 独立覆盖。

- [x] **Step 2: Run tests to verify RED**

```bash
cd frontend && npm test -- --run src/components/workbench/SipInformationPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx src/components/workbench/ExportPanel.test.tsx
```

Expected: 当前全字段非空门禁和“尚未审核”文案使新增断言失败。

- [x] **Step 3: Implement minimal UI projection**

拆分 all/required metadata fields；保存按钮只检查四个 required 字段；材质 label/placeholder 明示可选；ExportPanel 只新增 blocker 文案，不修改 `canExport`。

- [x] **Step 4: Run focused frontend tests to GREEN**

重复 Step 2 命令，Expected: PASS。

### Task 4: Full Verification, Review And Commit

**Files:**
- Modify: `.agent/bug-memory.md` only if the existing concurrent entry remains attributable and non-overlapping; otherwise do not stage it.
- Review: all task-scoped changed files.

**Interfaces:**
- Consumes: Tasks 1–3 的稳定代码与测试。
- Produces: 单一 scoped commit 和当前 runtime 证据。

- [x] **Step 1: Run contract, backend, frontend and build gates**

```bash
make check-contracts
micromamba run -n qi-p0 pytest backend/tests -q
cd frontend && npm test -- --run && npm run build
```

- [x] **Step 2: Run targeted live API and Chrome smoke**

对当前 project workbench GET 验证材质为空投影、manual count 不含旧 106 条来源，并在用户现有页面确认正式文件状态显示真实 `13/4` blocker。

- [x] **Step 3: Independent review**

Reviewer 检查 stable shape、required/optional 边界、技术要求来源保护、freeze 原子性、按钮门禁未放宽和测试真实 failure mode。

- [x] **Step 4: Inspect and commit only scoped files**

```bash
git diff --check
git status --short
git add <本计划明确列出的实际修改文件>
git commit -m "fix(workbench): clarify formal readiness"
```

不得 stage 或覆盖无关 `.agent/bug-memory.md` 改动。
