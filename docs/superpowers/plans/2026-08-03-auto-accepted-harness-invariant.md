# Auto-Accepted Harness Invariant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让现有 current-four Harness 在 `automatic-result/3` 的自动通过语义没有完整投影到 `ReviewWorkingCopy` 与 Workbench API 时阻断 `phase://live/candidates`。

**Architecture:** 在 live project 完成 processing、人工编辑尚未开始的同一 bootstrap 窗口，采集 raw candidate、working copy 和真实 Workbench API 的 `auto_accepted` item IDs。`live_evidence_policy.validate_candidate_evidence()` 是唯一阻断 Owner：要求 automatic-result schema 为 `/3`、raw auto set 非空、三层 IDs 完全一致并属于 candidate inventory；新 run 使用 `live-run-evidence/4` 强制字段，历史 v2/v3 继续可复验。继续复用 `live-run-evidence.json` 和既有 candidate selector，不新增 phase、report、receipt 或 policy Owner。

**Tech Stack:** Python 3.11、pytest、JSON Schema 2020-12、现有 P0 Harness、FastAPI Workbench API。

## Global Constraints

- Parent plan 仍为 `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`；本文件只拥有这次回归防护的实施步骤。
- `ConfidencePolicy` 继续是 high / medium / low disposition 的唯一业务 Owner；Harness 只验证投影一致性。
- 只校验人工编辑前的 bootstrap snapshot；不得把合法的 edit / merge / split / exclude 后状态误判为回归。
- 当前正式 producer schema 必须是 `automatic-result/3`；raw auto-accepted set 必须非空。
- `live-run-evidence/4` 是新 producer version；sealed v2/v3 artifacts 不得被改写或失去 schema/policy 兼容性。
- 继续使用 `phase://live/candidates?input_set=current-four&recognition_mode=production_uncertainty`；不新增正式 run 或 receipt 类型。
- 本任务不执行 paid Provider/current-four live run；只能报告自动化 contract proof，不能生成新的 formal live receipt。

---

### Task 1: Block Auto-Acceptance Projection Drift

**Files:**
- Create: `docs/superpowers/plans/2026-08-03-auto-accepted-harness-invariant.md`
- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `.agent/harness/scripts/live_evidence_policy.py`
- Modify: `.agent/harness/scripts/live_cycle_authorization.py`
- Modify: `.agent/harness/schemas/live-run-evidence.schema.json`
- Modify: `.agent/harness/policy/gdt10d-runtime-closure.txt`
- Test: `backend/tests/contract/harness/test_live_run_contract.py`

**Interfaces:**
- Consumes: `AutomaticResult.schema_version`, top-level candidate `confidence_decision`, bootstrap `ReviewWorkingCopy.items`, and `GET /api/v1/projects/{project_id}/workbench` candidates.
- Produces: candidate evidence fields `automatic_result_schema_version`, `automatic_result_auto_accepted_item_ids`, `working_copy_auto_accepted_item_ids`, and `workbench_auto_accepted_item_ids`; `validate_candidate_evidence(order, candidates)` rejects any missing, empty, foreign, or unequal projection.

- [x] **Step 1: Write the failing contract tests**

Add valid literal projection evidence to `_sample_evidence()` and `_visual_text_candidate_evidence()`. Add a parametrized policy test that mutates each downstream set independently and expects `ValueError("auto-accepted projection is inconsistent")`. Extend `test_live_phase_outcomes_require_strong_per_sample_evidence()` so a Workbench projection mismatch produces `blocked` for `phase://live/candidates`.

```python
"automatic_result_schema_version": "automatic-result/3",
"automatic_result_auto_accepted_item_ids": [item_ids[0]],
"working_copy_auto_accepted_item_ids": [item_ids[0]],
"workbench_auto_accepted_item_ids": [item_ids[0]],
```

- [x] **Step 2: Run RED and confirm the missing policy/schema fails**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_live_run_contract.py::test_candidate_evidence_rejects_auto_accepted_projection_drift \
  backend/tests/contract/harness/test_live_run_contract.py::test_live_phase_outcomes_require_strong_per_sample_evidence -q
```

Expected: FAIL because the current candidate evidence schema rejects the new fields and the policy does not yet enforce projection equality.

- [x] **Step 3: Extend the existing evidence schema**

Require the four projection fields in `$defs.candidate_evidence`; use `const: "automatic-result/3"` and the existing `string_id_array` definition. Do not add a schema file or inventory entry.

```json
"automatic_result_schema_version": { "const": "automatic-result/3" },
"automatic_result_auto_accepted_item_ids": { "$ref": "#/$defs/string_id_array" },
"working_copy_auto_accepted_item_ids": { "$ref": "#/$defs/string_id_array" },
"workbench_auto_accepted_item_ids": { "$ref": "#/$defs/string_id_array" }
```

- [x] **Step 4: Implement the single blocking policy**

In `validate_candidate_evidence()`, parse the three ID lists with `_unique_strings()`, require a non-empty raw set, require exact equality, and require every auto-accepted ID to be present in `candidate_ids`.

```python
if (
    candidates.get("automatic_result_schema_version") != "automatic-result/3"
    or not automatic_ids
    or automatic_ids != working_ids
    or automatic_ids != workbench_ids
    or not set(automatic_ids) <= set(candidate_ids)
):
    raise ValueError(f"sample {order} auto-accepted projection is inconsistent")
```

- [x] **Step 5: Collect the three bootstrap projections**

Inside `_PREPARE_PROJECT_PROGRAM`, validate raw and working decisions with the production confidence validator and emit strict auto-accepted IDs. In `_prepare_live_project()`, fetch the real Workbench API response, require the expected `project_id`, and derive IDs only when both `review_disposition == "auto_accepted"` and `status == "auto_accepted"`; attach them to `document["candidates"]` before returning.

```python
workbench = _http_json("GET", f"/api/v1/projects/{project_id}/workbench")
document["candidates"]["workbench_auto_accepted_item_ids"] = sorted(
    candidate["item_id"]
    for candidate in workbench["candidates"]
    if candidate.get("review_disposition") == "auto_accepted"
    and candidate.get("status") == "auto_accepted"
)
```

- [x] **Step 6: Run GREEN and focused regression suites**

Refresh only the stale hashes for already committed `backend/app` files in `gdt10d-runtime-closure.txt`; do not modify those runtime files. This closes the existing working/index/HEAD identity gate required before the Harness can execute.

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_live_run_contract.py::test_candidate_evidence_rejects_auto_accepted_projection_drift \
  backend/tests/contract/harness/test_live_run_contract.py::test_live_phase_outcomes_require_strong_per_sample_evidence -q
micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_live_run_contract.py -q
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_review_working_copy.py::test_supported_bootstrap_routes_only_high_confidence_away_from_manual_review \
  backend/tests/integration/test_project_workbench_api.py::test_project_candidate_projection_exposes_backend_confidence_status -q
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py
```

Expected: all commands exit 0. The first selector test must demonstrably block after only the Workbench ID set is tampered.

- [x] **Step 7: Review, smoke test, and commit**

Run `git diff --check`, inspect the complete scoped diff, request an independent read-only reviewer, and use `auto-feature-smoke-test` with the focused Harness/API tests. A browser smoke is not applicable because no UI code or browser interaction changes; a fresh formal current-four run remains explicitly out of scope.

```bash
git add \
  docs/superpowers/plans/2026-08-03-auto-accepted-harness-invariant.md \
  .agent/harness/scripts/run-p0.py \
  .agent/harness/scripts/live_evidence_policy.py \
  .agent/harness/scripts/live_cycle_authorization.py \
  .agent/harness/schemas/live-run-evidence.schema.json \
  .agent/harness/policy/gdt10d-runtime-closure.txt \
  backend/tests/contract/harness/test_live_run_contract.py
git commit -m "test(harness): block auto-acceptance projection drift"
```

## Execution Record

- RED：projection drift selectors 为 `4 failed`；Workbench helper 缺失为 `AttributeError`。
- GREEN：v2/v3/v4 compatibility、embedded collector、projection policy 与 live selector 定向测试为 `10 passed`。
- Integration：ReviewWorkingCopy v2/v3 与 Workbench API 投影测试为 `3 passed`。
- Contract gates：receipt policy `23 passed`；`check-contracts.py` 通过；working runtime closure `96/96`。
- Full Harness suite：`339 passed, 4 failed`。四项失败均来自 repository root canonical `.env` 与既有 live-authorization guard 的冲突，不属于本次 projection invariant；本任务不扩展 scope 修改该 safety contract。
- Review：独立 `reviewer` 复审 verdict 为 `accept`，无 blocking 或 non-blocking findings。
- Smoke：无 UI/browser 变更，因此使用 focused Harness/API/integration proof；未执行 paid current-four live run，也未生成新 formal receipt。
