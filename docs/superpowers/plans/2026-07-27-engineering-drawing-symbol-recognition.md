# Engineering Drawing Symbol Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不新增第二条 candidate/result path 的前提下，让 current source 中与 native text 相邻的工程图 vector symbols 进入稳定 visual observations，经 bounded Qwen Advisor 和确定性本地 validator 投影为可审核 candidate、reference/non-inspection 或 actionable ambiguity，并在 D7-T3 前用 sanitized fixture 与 sealed current-PDF live evidence 证明没有静默漏检。

**Architecture:** `PageInventory` 以 additive `VisualObservation` 保存确定性的局部视觉事实；`candidate_snapshot_from_inventory()` 保留现有 text seeds，并把 visual IDs 加入 Coverage Ledger；现有 `CandidateAdvisor` 仍是唯一 Vision integration Owner，通过一个统一的每页 16-call scheduler 先处理 visual batches、再处理 text-review routes；Qwen 只返回 `visual-symbol-review/1` allowlisted detections，本地 validator 才能修改 candidate/coverage；working copy、source-review commands、frontend workbench 和 immutable result path 全部复用现有实现。

**Tech Stack:** Python 3.11、PyMuPDF 1.25+、Pydantic、JSON Schema、FastAPI、Celery、SQLAlchemy、OpenAI-compatible Qwen API、pytest、React 19、TypeScript 5.8、Vitest、Playwright、Chrome DevTools MCP、P0 Harness

---

## Status And Execution Boundary

- Design source:
  `docs/superpowers/specs/2026-07-27-engineering-drawing-symbol-recognition-design.md`。
- Design status: 用户已在 `2026-07-27` 批准继续写 implementation plan。
- Plan status: **approved subordinate implementation detail**。本文件不是第二份
  current plan；task ordering、scope 和 execution authorization 仍只来自下述唯一
  current plan。
- Current implementation plan 仍是
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`。
- Selected lane: `Heavy`，因为本变更修改 `PDF-007`、candidate recall/coverage、
  Provider schema、failure veto、frontend source projection 和 final live receipt。
- Current ordering: 已验证的 D7-T2 manual-balloon residual 保持完成；本能力必须作为
  同一 current plan 的 D7-T2 in-place closure amendment，在 D7-T3 final receipt
  之前完成。
- Activation gate: Task 0 已由 commit `994cbe4` 把 selection、task order、allowed
  paths、rollback 和 focused gate 原地写入 current plan。用户于 `2026-07-27`
  进一步批准的 Option A contract clarification 已激活；下一步是 Task 1 / `SR-1`，
  不得重复 Task 0、先做 production edit 或先调用 live Provider。
- Live-label gate: approved manifest bytes、bbox 和 quality-owner verdict 必须在任何
  production GREEN 前冻结；label totals 和 per-family counts 由 staging 从 manifest
  bytes 机械派生，Quality Owner 只确认 200% overlay 与
  `unlabeled_target_count=0`。允许先写 sanitized fixture RED；未 seal 时必须停在
  RED，不能通过猜测 label 或用 synthetic evidence 继续。
- `.agent/EXECUTION_STATUS.md` 在本计划写作时不存在。执行者不得为绕过这一事实而
  发明 status；如后续由其他批准任务创建，只记录已经验证的结果。
- 若执行时存在与本计划无关的未提交改动，必须保护这些改动并逐文件 stage around
  them；不得使用 `git add .`，不得覆盖、清理或把它们带入 task commit。

## Problem Boundary

### Single Owner

`backend/app/candidates/advisor.py::CandidateAdvisor` 是唯一 Vision integration
Owner，也是唯一可在本地 validator 通过后写 automatic raw candidate/coverage 的
组件。既有 Review aggregate 仍只执行 Quality Owner 显式
`promote_source` / `ignore_source` working-copy commands；该人工 override 不建立第二个
automatic Vision Owner。

`backend/app/candidates/symbol_review.py` 是纯 contract/validation/projection helper：
它可以返回 immutable decisions，但不得持久化、创建 `AutomaticResult`、修改
working copy 或调用 Provider。该拆分用于避免已经约 700 行的 `advisor.py` 继续
膨胀，不建立第二个 Advisor。

### Old Paths

- Preserve:
  `backend/app/processing/automatic_result.py::candidate_snapshot_from_inventory()`
  的 deterministic text candidate path。
- Preserve:
  `CandidateAdvisor` 现有 `text_review` route、text cache 和 fail-closed Provider
  policy。
- Replace:
  `_route_objects()` 中“按排序取每页前 16 个并静默跳过剩余 route”的局部预算逻辑，
  改为同一 Owner 内的 unified scheduler。
- New inside existing Owner:
  `visual_symbol` route、visual batch crop、strict response schema 和 local projection。
- Forbidden:
  second candidate writer、second result path、bridge、shadow、dual-write、fallback、
  feature flag、full-page Vision、global drawing clustering、Provider-owned disposition。

### Unchanged Contracts

- `CandidateType` 不新增 `counterbore`、roughness、GD&T 或 revision enum。
- `CoarseType` 不新增 symbol kind；roughness/GD&T 继续使用既有四字段
  `CoarseCandidate`。
- `raw_text` 保留 source bytes 的文字语义；canonical `Φ/深/⌴/∥/⊥/⏥` 只进入
  `normalized_text`，或进入既有 coarse `raw_text` 的受控图形转写。
- `Φ` 不等于 `hole`；`feature_kind` 保持 `unknown` 并要求人工确认。
- Coverage Ledger 仍是唯一 completeness Veto Gate。
- `ReviewService.create_from_raw()`、existing promote/ignore commands、freeze、
  balloon、confirm 和 export 顺序不变。
- qualifying `revision_marker` 的 automatic Owner decision 固定为
  `non_inspection + candidate_id=null + requires_confirmation=true`。只有 Quality
  Owner 显式执行既有 `promote_source` 并提供全部 manual fields 后才可创建 manual
  item；`ignore_source` 确认 non-inspection。Provider、validator、automatic
  processing 和 frontend inference 均不得调用或模拟该 override。
- 已有 `AutomaticResult`、working copy 和 reviewed result 不原地补写；current source
  用新 project upload 产生新 result。
- fixture tests 必须 `external_calls=0`；live Provider call 只能发生在已 seal 的
  current-source run。

### Fixed Failure Semantics

| Failure | Required result |
| --- | --- |
| Unknown vector opcode、NaN/Inf 或无法 canonicalize 的 style | visual proposal blocking；不调用 Provider |
| 单个 padded observation 超过 crop 限制 | `visual_crop_oversize`；无 `AutomaticResult`/working copy |
| visual batches 每页超过 16 | `symbol_route_budget_exhausted`；不得截断后成功 |
| Provider unavailable、request、root schema 或 cache/audit failure | 现有 `vision_provider_call_failed` / `candidate_advisor` fail-closed path |
| detection source/bbox/duplicate/projection invalid | 原 candidate bytes 不变；该 visual observation 变为 actionable `ambiguous`，只保存脱敏 rejection code |
| visual observation 没有 detection | `ambiguous + requires_confirmation=true + visual_no_detection` |
| text-review routes 超过 visual 后的剩余 slots | 保留现有 object，不写假 provenance；不是 visual success |
| visual coverage 缺 source/coordinates/disposition 或出现重复 primary disposition | `coverage_blocking`；无 formal result |

## OSS Research Decision

本计划已按 `github-oss-fusion` 做 license-safe 调研，只吸收结构和测试思想，不复制
外部实现：

- PyMuPDF:
  官方 `Page.get_drawings()`/drawing path contract 与 upstream drawing tests 证明
  vector geometry 应按 path item、style、close-path 和 bbox 做 deterministic
  serialization；`cluster_drawings()` 面向 tables/charts，不能作为本任务的全局
  symbol detector。融合：golden canonical bytes、close-path/style/non-finite
  regressions。跳过：任何 upstream source copy；当前 dependency 的 AGPL/commercial
  license 边界不因本任务扩大。
- Docling:
  `StandardPdfPipeline` 和 threaded pipeline tests 展示了 stage-specific failure
  envelope、bounded queues/batches、options identity 与 repeated-run equivalence。
  融合：visual proposal / scheduling / provider / projection 分阶段失败，batch
  identity 进入 cache，重复运行比较 exact output。跳过：引入 Docling、PyTorch、
  layout/OCR pipeline 或第二套 document owner。
- Deepdoctection 仅作为额外架构对照阅读；它是广义 Document AI pipeline，不适合
  current P0 的窄 symbol lane，因此不引入 dependency、component graph 或 annotation
  owner。

## Final File Map

### Create

- `backend/app/pdf/visual_observations.py`
- `backend/app/candidates/symbol_review.py`
- `backend/app/providers/visual_symbol_review.schema.json`
- `backend/tests/helpers/__init__.py`
- `backend/tests/helpers/symbol_fixture.py`
- `backend/tests/unit/pdf/test_visual_observations.py`
- `backend/tests/unit/candidates/test_symbol_advisor.py`
- `backend/tests/contract/test_qwen_symbol_provider.py`
- `backend/tests/integration/test_symbol_recognition_pipeline.py`
- `backend/tests/e2e/test_symbol_recognition.py`
- `.agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json`
- `.agent/harness/schemas/visual-symbol-eval.schema.json`
- `.agent/harness/schemas/visual-symbol-annotation-verdict.schema.json`
- `.agent/harness/scripts/stage-symbol-eval.py`
- `.agent/harness/scripts/symbol_eval.py`
- `backend/tests/contract/harness/test_symbol_eval_contract.py`

### Modify

- `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
- `.agent/harness/contracts/p0-contracts.json`（generated）
- `.agent/harness/contracts/global-contract-bindings.json`（generated）
- `.agent/harness/policy/provider-call-policy.yaml`
- `.agent/harness/policy/p0-acceptance-policy.yaml`
- `.agent/harness/schemas/live-run-evidence.schema.json`
- `.agent/harness/scripts/check-contracts.py`
- `.agent/harness/scripts/generate-receipt.py`
- `.agent/harness/scripts/live_evidence_policy.py`
- `.agent/harness/scripts/run-p0.py`
- `.agent/harness/scripts/run-provider-contracts.py`
- `backend/tests/contract/harness/test_contract_architecture.py`
- `backend/tests/contract/harness/test_live_run_contract.py`
- `backend/app/pdf/schemas.py`
- `backend/app/pdf/inventory.py`
- `backend/app/processing/automatic_result.py`
- `backend/app/candidates/advisor.py`
- `backend/app/candidates/coverage.py`
- `backend/app/providers/base.py`
- `backend/app/providers/qwen_vl.py`
- `backend/app/processing/runtime_recognition.py`
- `backend/app/processing/pipeline.py`
- `backend/app/processing/tasks.py`
- `backend/app/review/service.py`
- `backend/app/projects/router.py`
- `backend/tests/contract/test_provider_call_records.py`
- `backend/tests/integration/test_error_records.py`
- `backend/tests/integration/test_processing_entry_task.py`
- `backend/tests/integration/test_project_workbench_api.py`
- `backend/tests/integration/test_result_layers.py`
- `backend/tests/integration/test_review_operations.py`
- `backend/tests/integration/test_review_working_copy.py`
- `backend/tests/integration/test_task_idempotency.py`
- `frontend/src/api/types.ts`
- `frontend/src/components/review/ReviewPanel.tsx`
- `frontend/src/components/review/ReviewPanel.test.tsx`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- `frontend/src/components/pdf/PdfWorkspace.tsx`
- `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/styles/workbench.css`
- existing PDF/candidate/provider/pipeline/result regression tests only where an additive
  assertion is required; existing expectations不得改宽、skip 或删除。

### Explicitly Out Of Scope

- database migration 或新 table；
- new API endpoint、visual-only review command 或 frontend recognition logic；
- OCR behavior、page classification thresholds、balloon/export semantics；
- full-page/fixed-tile Vision；
- standalone symbols without nearby native line；
- additional symbol families、accuracy threshold platform 或 configurable thresholds；
- source PDF、live labels、screenshots、Provider response body 或 credentials 入 Git。

## Required Test Matrix

下面 32 项必须逐项存在；parameterization 只能覆盖同一 ID 内的 allowlisted variants，
不能合并跨 layer 的 ID。

| Task | IDs | Count |
| --- | --- | ---: |
| Task 2 | PDF-01～PDF-05 | 5 |
| Task 3 | ADV-01～ADV-02、PROV-01～PROV-02 | 4 |
| Task 4 | ADV-03～ADV-09、COV-01～COV-04 | 11 |
| Task 5 | INT-01～INT-06 | 6 |
| Task 6 | FE-01～FE-03 | 3 |
| Task 7 | E2E-01～E2E-02 | 2 |
| Task 8 | LIVE-01 | 1 |
| **Total** |  | **32** |

## Task 0: Activate One Current Plan — Completed At `994cbe4`

- [x] 用户已批准本 subordinate implementation proposal。
- [x] commit `994cbe4` 已在唯一 current plan 中记录 problem boundary、single Owner、
  old-path action、`SR-1 → SR-8` ordering、live-label/literal-run-ID gate、exact allowed
  paths、rollback 和 focused verification。
- [x] activation 保持 `D7-T3` 在 `SR-8` 之后，未改写 prior sealed receipts，也未创建
  第二份 current plan、status registry、candidate/result path 或产品 Owner。
- [x] Option A contract clarification 已激活为 `SR-1` 前置语义。

Task 0 是历史完成记录，不得重跑、重新追加同名 amendment 或再次提交 activation
commit。执行从 Task 1 / `SR-1` contract/Harness RED 继续。

## Task 1: Amend Contract Owners And Seal The Live Evaluation Input

**Files:**

- Modify:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Modify:
  `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
- Modify: `.agent/harness/contracts/p0-contracts.json`（generated）
- Modify: `.agent/harness/contracts/global-contract-bindings.json`（generated）
- Modify: `.agent/harness/policy/provider-call-policy.yaml`
- Create: `.agent/harness/schemas/visual-symbol-eval.schema.json`
- Create:
  `.agent/harness/schemas/visual-symbol-annotation-verdict.schema.json`
- Create: `.agent/harness/scripts/stage-symbol-eval.py`
- Modify: `.agent/harness/scripts/check-contracts.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Modify: `.agent/harness/scripts/run-p0.py`
- Create:
  `backend/tests/contract/harness/test_symbol_eval_contract.py`
- Modify:
  `backend/tests/contract/harness/test_contract_architecture.py`
- Modify:
  `backend/tests/contract/harness/test_live_run_contract.py`

### Step 1: Write RED Harness tests

- [ ] Add tests with these exact names:
  - `test_symbol_eval_schema_is_closed_and_current_source_bound`
  - `test_stage_symbol_eval_rejects_wrong_hash_bbox_or_family_set`
  - `test_symbol_eval_revision_marker_is_positive_noninspection_only`
  - `test_stage_symbol_eval_rejects_missing_or_duplicate_only_negative_family_coverage`
  - `test_symbol_eval_rejects_negative_family_on_positive_label`
  - `test_symbol_eval_requires_negative_family_on_frozen_negative_label`
  - `test_symbol_eval_artifacts_exclude_paths_pdf_bytes_and_screenshots`
  - `test_symbol_eval_loader_requires_literal_sealed_run_id`
  - `test_symbol_annotation_verdict_requires_exact_overlay_review`
  - `test_symbol_eval_byte_change_stales_input_identity`

The test bodies must use existing
`backend/tests/contract/harness/harness_test_support.py` helpers, a synthetic two-page PDF
with the wrong hash for negative cases, and a schema-valid manifest object. They must never
read the real current source. The literal-run loader test must also prove registration executes
no business selector、project mutation or Provider call. The contract cases must distinguish a
valid `symbol_kinds=["revision_marker"]`、`expected_disposition="non_inspection"` label from
`symbol_kinds=["frozen_negative"]` with
`negative_family="revision_table_or_invalid_marker"`; they must reject a missing negative family,
nine labels that repeat only one negative family, `negative_family` on any positive label, and
every frozen-negative label that omits `negative_family`.

- [ ] Run RED:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

Expected: FAIL because the two schemas、staging script、artifact allowlist and literal-run
loader do not exist.

### Step 2: Amend the Markdown Owners first

- [ ] Apply these semantic deltas without turning partial long-term contracts into false full
  P0 claims:

| Contract | Amendment |
| --- | --- |
| `PDF-007` | Add stable visual observation ID/bbox/geometry hash/text relations; current enforcement becomes `P0` only for the fixed current-scope proposal |
| `CAND-001` | Recall-first seeds may consume locally validated visual observations; keep `P0-partial` because not all future symbol families are implemented |
| `CAND-004` | Advisor scope includes local candidate or suspicious visual-observation crop; Provider still owns no disposition |
| `CAND-005` | Expected coverage includes visual IDs; unscheduled/budget-overflow visual observations are blocking |
| `CAND-006` | Ambiguous visual source remains locatable, promotable and ignorable |
| `ITEM-002` | Separate source `raw_text` from visual-assisted `normalized_text`; keep Decimal/source rules |
| `ITEM-003` | Reassert `feature_kind=unknown` for visual diameter and four-field coarse fallback |

- [ ] Amend `P0-REC-005`、`P0-REC-009` and `P0-REC-010` in place:
  - task becomes `D7-T2`;
  - status becomes `pending`;
  - selectors name both existing text tests and the exact new symbol tests;
  - implementation note says existing passed text proof remains valid but does not satisfy the
    visual delta.
- [ ] Do not modify any generated JSON by hand.

### Step 3: Define exact sealed artifacts

- [ ] Create `visual-symbol-eval.schema.json` with:
  - root `additionalProperties=false`;
  - `schema_version="visual-symbol-eval/1"`;
  - exact source SHA-256
    `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec`;
  - `annotation_owner_role="quality_owner"` and `annotation_status="approved"`;
  - exactly two pages with unique non-negative `page_index`;
  - unique non-blank `label_id`;
  - positive-area four-number `bbox_pdf`;
  - sorted, unique `symbol_kinds` from the nine-kind allowlist plus
    `frozen_negative`;
  - exact disposition/projection enums from the design spec;
  - `revision_marker` is the ninth evaluation-positive family, requires
    pre-manual-command `expected_disposition="non_inspection"` and
    `expected_projection=null`, cannot coexist with `frozen_negative`, and is never
    automatically projected as an inspection item; a later explicit Quality Owner
    `promote_source` is outside live symbol evaluation;
  - conditional `negative_family` enum in this exact order:
    1. `part_or_hole_geometry`
    2. `hatch_center_or_cross`
    3. `dimension_leader_or_section_line`
    4. `view_or_section_label`
    5. `revision_table_or_invalid_marker`
    6. `datum_like_letter_or_table_cell`
    7. `watermark_logo_title_or_signoff`
    8. `isometric_hole_slot_or_edge`
    9. `ordinary_text_number_material_or_requirement`
  - `frozen_negative` cannot coexist with another kind;
  - `negative_family` is required when and only when
    `symbol_kinds` exact equal `["frozen_negative"]`; every positive label must omit it;
  - root、page and label objects keep `additionalProperties=false`.
- [ ] Create `visual-symbol-annotation-verdict.schema.json` with a closed object requiring:
  `schema_version` const `visual-symbol-annotation-verdict/1`;
  `annotation_owner_role` const `quality_owner`;
  `overlay_scale_percent` const `200`;
  `unlabeled_target_count` const `0`;
  script-derived `negative_family_count` const `9`;
  `manifest_sha256` matching `^[0-9a-f]{64}$`; and `recorded_at` using JSON Schema
  `format: date-time`.

- [ ] Set artifact names to:
  - `artifacts/visual-symbol-eval.json`
  - `artifacts/visual-symbol-annotation-verdict.json`
- [ ] Extend Harness input identity and schema inventory to bind both exact bytes.
- [ ] Extend `provider-call-policy.yaml` with
  `max_vision_calls_per_page: 16`; keep OCR and existing per-candidate fields.

### Step 4: Implement the staging command

- [ ] `stage-symbol-eval.py` accepts only the required `--source` PDF path、
  required `--manifest` JSON path、required `--mode live` and optional literal open
  `--run-id`; it rejects positional arguments and all other flags.

- [ ] Before writing an artifact, verify:
  - both inputs are real regular non-symlink files and do not change during read;
  - source header、exact SHA-256、two-page count and page bbox;
  - JSON Schema plus unique labels、bbox bounds、kind order、projection/disposition
    compatibility;
  - every one of the nine current positive families appears at least once;
  - the distinct manifest `negative_family` set exact equals the complete nine-value enum and
    every negative family has at least one label; missing-family or duplicate-family-only
    coverage fails regardless of total negative-label count;
  - output canonical JSON has no path、PDF bytes、base64、credential or screenshot field.
- [ ] Create the annotation verdict from the Quality Owner's fixed CLI confirmations
  `overlay_scale_percent=200` and `unlabeled_target_count=0`. Compute
  `negative_family_count=9` and per-negative-family counts only from the mechanically validated
  manifest; do not accept a human-entered or CLI-entered count as coverage proof and do not infer
  any value from model output.
- [ ] Extend `run-p0.py` with
  `register_live_input_artifacts(task_id="D7-T2", artifacts=...)`. It must reuse the existing
  Harness preflight、run schema、input identity、artifact validation、sealing and receipt
  code, record only `phase://live/symbol-eval-registration`, and execute no business selector、
  project mutation or Provider call. Do not create another run/receipt implementation.
- [ ] If no `--run-id` is supplied, call that canonical registration entry with the two input
  artifacts. If it is supplied, accept only the existing literal run ID regex and one open,
  unsealed D7-T2 live staging run; still pass through the same registration validation.
- [ ] Set all sealed run members read-only using the existing run sealing path; do not invent
  a second receipt implementation.

### Step 5: Generate mirrors and verify GREEN

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

Expected: generated mirrors exactly match Markdown Owners; contract drift/conflict/missing are
zero; selected Harness tests PASS.

### Step 6: Quality Owner seals the real manifest

- [ ] Stop unless the Quality Owner supplies an approved manifest and confirms only
  `overlay_scale_percent=200` and `unlabeled_target_count=0` after the overlay review. Staging,
  not the Quality Owner, validates label IDs and derives total/per-family counts from manifest
  bytes.
- [ ] The operator sets local shell variables to real files without writing their values into
  Git or the plan:

```bash
test -f "$QI_SYMBOL_SOURCE_PDF"
test -f "$QI_SYMBOL_EVAL_MANIFEST"
micromamba run -n qi-p0 python \
  .agent/harness/scripts/stage-symbol-eval.py \
  --mode live \
  --source "$QI_SYMBOL_SOURCE_PDF" \
  --manifest "$QI_SYMBOL_EVAL_MANIFEST"
```

Expected: output contains one literal `run_id`, exact source hash verification, total label
count, per-positive-family counts, manifest-derived per-negative-family counts,
`unlabeled_target_count=0`, script-derived `negative_family_count=9`, and a sealed verdict. It
must not print either host path、screenshot data or PDF bytes.

- [ ] Copy the emitted literal run ID into the activated current-plan amendment. Do not record
  `latest` or an environment-variable alias. Production GREEN is blocked until this edit is
  committed.

### Step 7: Commit only Task 1

```bash
git add \
  docs/contracts/MAIN_CONTRACT_MATRIX.md \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
  docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md \
  .agent/harness/contracts/p0-contracts.json \
  .agent/harness/contracts/global-contract-bindings.json \
  .agent/harness/policy/provider-call-policy.yaml \
  .agent/harness/schemas/visual-symbol-eval.schema.json \
  .agent/harness/schemas/visual-symbol-annotation-verdict.schema.json \
  .agent/harness/scripts/stage-symbol-eval.py \
  .agent/harness/scripts/check-contracts.py \
  .agent/harness/scripts/generate-receipt.py \
  .agent/harness/scripts/run-p0.py \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py
git commit -m "test: seal symbol recognition acceptance"
```

## Task 2: Build Deterministic Visual Observations

**Required test IDs:** PDF-01～PDF-05

**Files:**

- Create: `backend/tests/helpers/__init__.py`
- Create: `backend/tests/helpers/symbol_fixture.py`
- Create: `backend/tests/unit/pdf/test_visual_observations.py`
- Create: `backend/app/pdf/visual_observations.py`
- Modify: `backend/app/pdf/schemas.py`
- Modify: `backend/app/pdf/inventory.py`
- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/tests/unit/pdf/test_inventory.py`

### Step 1: Create the deterministic sanitized fixture

- [ ] `build_symbol_fixture(tmp_path)` generates, in the test temp directory only, a two-page
  vector PDF plus an independent manifest with:

| Family | Positive regions |
| --- | ---: |
| diameter | 4 |
| depth | 3 |
| counterbore | 2 |
| surface roughness | 3 |
| GD&T parallelism/perpendicularity/flatness | 3 |
| datum reference | 2 |
| revision marker | 2 |
| frozen negative regions | 12 |

- [ ] Use PyMuPDF drawing primitives and `insert_text()`; target symbols、native text and
  negative geometry must use separate helper functions.
- [ ] The 12 frozen negative regions collectively cover all nine exact `negative_family` enum
  values at least once. A closed triangle with one valid inner revision token is a positive
  `revision_marker/non_inspection`; revision-table cells and triangle-like geometry that fails
  that validator use `revision_table_or_invalid_marker`. Color is not a classifier.
- [ ] Return `(pdf_path, manifest)`; production code must never import this helper or read the
  manifest.
- [ ] Bind fixture identity to helper SHA-256、`symbol-fixture/1` and PyMuPDF version.
- [ ] Assert repeated generation produces identical PDF SHA-256、page boxes and manifest.

### Step 2: Write all five PDF RED tests

- [ ] Add tests with these exact names:
  - `test_visual_observation_id_and_order_are_stable`
  - `test_small_nearby_path_items_form_text_adjacent_context`
  - `test_large_distant_or_page_geometry_is_rejected`
  - `test_visual_bbox_round_trip_and_union`
  - `test_visual_batches_use_stable_first_fit`

- [ ] Test PDF-01 compares exact observation IDs、order、bbox、geometry SHA and associated
  text IDs across two runs.
- [ ] PDF-02 proves individual path width/height `<=96 pt` and both-axis gap `<=12 pt`.
- [ ] PDF-03 includes a part outline、dimension line、hatch、title border and a context whose
  union exceeds 1% page; all are absent from visual observations.
- [ ] PDF-04 round-trips existing `PageTransform` and checks exact source bbox union.
- [ ] PDF-05 runs exact 300-DPI packing and asserts stable batch membership、crop bbox、call
  order on the deterministic fixture. The separate Task 4 preflight owns the `V<=16` proof for
  both current-source pages.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py -q
```

Expected: FAIL because `VisualObservation` and the visual builder do not exist. If the real
sealed manifest is not yet available, stop here; RED is the only permitted production-code
boundary.

### Step 3: Add the additive inventory type

- [ ] Add this exact dataclass and defaulted page field:

```python
from typing import Literal


@dataclass(frozen=True)
class VisualObservation:
    observation_id: str
    source_type: Literal["visual"]
    observation_level: Literal["annotation_context"]
    page_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox
    proposal_kind: Literal["text_adjacent_vector_context"]
    geometry_sha256: str
    associated_text_observation_ids: tuple[str, ...]
```

Add `visual_observations: tuple[VisualObservation, ...] = ()` after the current
`PageInventory` non-default fields so dataclass construction remains valid. Existing callers
that omit it must remain byte-for-byte equivalent after JSON conversion.

### Step 4: Implement canonical geometry and proposal rules

- [ ] In `visual_observations.py`, freeze:

```python
PROPOSAL_RULE_VERSION = "visual-observation/1"
MAX_PATH_ITEM_EXTENT_PT = 96.0
MAX_AXIS_GAP_PT = 12.0
MAX_CONTEXT_PAGE_AREA_RATIO = 0.01
HASH_QUANTUM = Decimal("0.001")
```

- [ ] Canonicalize each PyMuPDF path item as
  `opcode + ordered point/rect/quad coordinates`.
- [ ] Include `width/dashes/lineCap/lineJoin/color/fill`; missing values serialize as JSON
  `null`.
- [ ] Convert finite numeric values with
  `Decimal(str(value)).quantize(HASH_QUANTUM, ROUND_HALF_EVEN)` and remove negative zero.
- [ ] Permit color/fill only as null or 1～4 finite components; collapse ASCII whitespace in
  string dashes; permit line cap/join only as integer or integer array.
- [ ] Raise a typed blocking error for unknown opcode、non-finite coordinate or invalid style.
  Never skip the bad primitive.
- [ ] Sort path items by
  `(bbox.y0, bbox.x0, bbox.y1, bbox.x1, canonical_path_bytes)`.
- [ ] For every non-blank native line, select only individual path items meeting both
  `<=96 pt` extent and `<=12 pt` gap on both axes. Do not inspect the line text.
- [ ] Reject empty and `>1%` page union contexts.
- [ ] Associated IDs are the line plus native spans whose `parent_region_id` equals the line
  ID, sorted by ID.
- [ ] Deduplicate exact geometry digests, then IoU `>=0.8` proposals with identical associated
  IDs by retaining stable sort first.
- [ ] Compute the 24-char ID from:

```text
visual-observation/1
+ source_sha256
+ page_index
+ proposal_kind
+ bbox rounded to 0.001 PDF point
+ geometry_sha256
+ sorted associated text IDs
```

- [ ] Sort final observations by
  `(page_index, bbox.y0, bbox.x0, proposal_kind, observation_id)`.
- [ ] `inventory.py::build_inventory()` computes source SHA-256 once, builds native text first,
  then passes each page plus native observations to the visual builder. It must not call
  `cluster_drawings()`.
- [ ] The same module returns an internal, non-persisted `VisualGeometryContext` alongside each
  observation, containing only canonical path items needed by the local datum/revision
  validator. `PageInventory.to_dict()` persists only the frozen `VisualObservation` fields.
- [ ] Expose one pure reconstruction function that reopens the same source page, rebuilds these
  contexts with the same source hash/rule/version, and verifies reconstructed observation IDs
  exactly equal inventory IDs. `CandidateAdvisor` uses this function; a missing/extra ID or
  geometry-hash mismatch is a blocking proposal error. Do not add canonical path bytes to
  API、DB or inventory JSON.
- [ ] Add a priority-neutral
  `pack_visual_batches(page, ordered_observations)` pure function implementing exact
  padding、7.5% page area、300-DPI pixel preflight、1536-pixel side、32-observation stable
  first-fit and `visual_crop_oversize`. Task 4 owns priority ordering and the shared 16-call
  schedule, not a second packing implementation.

### Step 5: Add visual expected coverage without creating candidates

- [ ] Keep `_selected_observations()` text-only.
- [ ] Add a separate stable `selected_visual_observations(pages)` helper.
- [ ] After deterministic text candidate construction, append one initial
  `CoverageEntry(disposition="ambiguous", requires_confirmation=True)` per visual observation
  and add every visual ID to `CandidateSnapshot.expected_observation_ids`.
- [ ] Do not create a visual candidate in `automatic_result.py`; only `CandidateAdvisor` may
  replace this initial disposition.

### Step 6: Verify GREEN and regressions

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/unit/pdf/test_coordinates.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_coverage.py -q
```

Expected: PDF-01～PDF-05 and existing inventory/OCR/coverage tests PASS; no current text
observation ID or candidate payload changes.

### Step 7: Commit only Task 2

```bash
git add \
  backend/tests/helpers/__init__.py \
  backend/tests/helpers/symbol_fixture.py \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/app/pdf/visual_observations.py \
  backend/app/pdf/schemas.py \
  backend/app/pdf/inventory.py \
  backend/app/processing/automatic_result.py \
  backend/tests/unit/pdf/test_inventory.py
git commit -m "feat: build deterministic visual observations"
```

## Task 3: Freeze The Visual Provider Contract And Cache Envelope

**Required test IDs:** ADV-01、ADV-02、PROV-01、PROV-02

**Files:**

- Create: `backend/app/providers/visual_symbol_review.schema.json`
- Create: `backend/app/candidates/symbol_review.py`
- Modify: `backend/app/providers/base.py`
- Modify: `backend/app/providers/qwen_vl.py`
- Modify: `backend/app/candidates/advisor.py`
- Create: `backend/tests/contract/test_qwen_symbol_provider.py`
- Create:
  `.agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json`
- Modify: `.agent/harness/scripts/run-provider-contracts.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Create: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Modify: `backend/tests/contract/test_provider_call_records.py`

### Step 1: Add the sanitized Provider fixture

- [ ] The committed fixture uses `provider-fixture/1`, `qwen-vl`,
  `visual-symbol-review/1`, opaque `fixture://` refs, a synthetic request ID and a JSON content
  value containing only two fake observation IDs.
- [ ] It must not contain a real crop、base64、host path、project ID、current-source text or
  credential-shaped value.
- [ ] Add it to `run-provider-contracts.py` and `generate-receipt.py` controlled-file identity.

### Step 2: Write the four RED tests

- [ ] ADV-01
  `test_visual_symbol_response_accepts_only_exact_schema`:
  exact fixture parses; missing required field、extra root/detection field and
  `requires_confirmation=false` raise `VisualSymbolSchemaError`.
- [ ] ADV-02
  `test_visual_symbol_response_rejects_invalid_identity_or_shape`:
  unknown observation ID、bbox outside `[0,1]`、non-positive bbox、unknown text source、
  duplicate detection tuple、more than four detections for one observation and unknown kind
  cannot yield an accepted detection or mutate a candidate.
- [ ] PROV-01
  `test_qwen_visual_symbol_schema_and_cache_identity`:
  Qwen request has one local crop, JSON-only non-thinking mode, exact prompt/schema version;
  cache key changes when crop hash、source hash、visual IDs、model、prompt、schema、adapter、
  proposal rule or PyMuPDF version changes.
- [ ] PROV-02
  `test_qwen_visual_symbol_records_are_redacted_on_success_and_failure`:
  success and invalid-schema call records include only request/response resource refs、hashes、
  versions、request ID、duration and usage; serialized records and raised messages exclude
  crop bytes、base64、SDK body、private path、credential and model explanation.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  -k "visual_symbol_response or qwen_visual_symbol" -q
```

Expected: FAIL because the schema、parser、Provider method and visual cache envelope are absent.

### Step 3: Freeze the JSON Schema

- [ ] Create a Draft 2020-12 schema with root and detection
  `additionalProperties=false`.
- [ ] Root fields:
  - `schema_version` const `visual-symbol-review/1`;
  - `detections`, array, maximum 128.
- [ ] Detection required fields:
  - `visual_observation_id`: non-blank string;
  - `symbol_kind`: enum of
    `diameter/depth/counterbore/surface_roughness/gdt_parallelism/`
    `gdt_perpendicularity/gdt_flatness/datum_reference/revision_marker`;
  - `bbox_normalized`: exactly four numbers in `[0,1]`;
  - `associated_text_observation_ids`: unique string array;
  - `requires_confirmation`: const `true`.
- [ ] Do not add confidence、transcription、item type、disposition、nominal、tolerance、
  feature kind or explanation fields.

### Step 4: Add pure response and decision types

- [ ] In `symbol_review.py`, define exact immutable boundaries:

```python
SymbolKind = Literal[
    "diameter",
    "depth",
    "counterbore",
    "surface_roughness",
    "gdt_parallelism",
    "gdt_perpendicularity",
    "gdt_flatness",
    "datum_reference",
    "revision_marker",
]


@dataclass(frozen=True)
class ValidatedSymbolDetection:
    visual_observation_id: str
    symbol_kind: SymbolKind
    bbox_pdf: BBox
    associated_text_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class RejectedSymbolDetection:
    visual_observation_id: str
    rejection_code: Literal[
        "visual_bbox_invalid",
        "visual_source_mismatch",
        "visual_duplicate_detection",
    ]
```

- [ ] `parse_visual_symbol_json()` validates the exact JSON Schema and raises
  `VisualSymbolSchemaError("visual symbol response violates frozen schema")` without echoing
  content.
- [ ] When the SDK returned a non-blank request ID but content is schema-invalid,
  `QwenVisionProvider.review_symbols()` raises a typed safe exception carrying only request ID
  and numeric usage; it must not attach or stringify the raw content.
- [ ] `validate_symbol_detections()` receives the current batch identities、per-observation
  text allowlists and crop→page transform. It:
  - converts normalized bbox to page coordinates;
  - rejects non-positive or crop-external bbox;
  - enforces current-batch visual IDs and text allowlist subsets;
  - permits at most four detections per observation;
  - rejects duplicate `(observation ID, kind, bbox rounded to 0.001)` tuples;
  - returns stable accepted/rejected tuples sorted by page reading order;
  - never returns Provider payload dictionaries to callers.

### Step 5: Extend the existing Provider port

- [ ] Add `review_symbols(image: bytes, prompt: str) -> VisionResult` to the existing Vision
  Provider protocol; keep `review_candidate()` unchanged for text routes.
- [ ] `QwenVisionProvider.review_symbols()` uses:

```text
system: Review local engineering drawing symbol contexts. Output JSON only.
user: one bounded PNG image + the canonical prompt + "Output in JSON format."
response_format: {"type": "json_object"}
extra_body: {"enable_thinking": false}
```

- [ ] It returns `VisionResult` only after `parse_visual_symbol_json()` succeeds and the SDK
  request ID is non-blank.
- [ ] It never accepts a full PDF or page image.

### Step 6: Add the visual cache/call-record envelope

- [ ] Keep existing text cache bytes and `candidate-advisor-cache/1` untouched.
- [ ] Use a separate path pattern
  `projects/{safe_project_id}/provider-cache/qwen-symbol/{cache_key}.json` with
  `visual-symbol-advisor-cache/1`.
- [ ] Cache identity includes:

```text
source_sha256
visual observation IDs in stable order
crop_bbox_pdf
crop_sha256
model
visual-symbol-prompt/1
visual-symbol-review/1
qwen-openai-compatible/1
visual-observation/1
PyMuPDF version
```

- [ ] Cache hit requires an existing matching Provider call audit record; invalid bytes、
  missing audit、hash/version/schema mismatch raise sanitized `CandidateAdvisorFailure`.
- [ ] On a real call, persist crop and validated response through
  `LocalFileStorage.write_verified()` and `ProviderCallRecord`; do not put either body into
  DB、logs or coverage.
- [ ] On an invalid-schema call, persist a canonical sanitized failure response containing only
  `schema_version="visual-symbol-call-failure/1"` and
  `error_code="visual_schema_invalid"`, then persist the same allowlisted call record with the
  safe request ID/usage and that failure response ref. Raise the blocking
  `CandidateAdvisorFailure` afterward. Never persist the invalid Provider body.

### Step 7: Verify GREEN and existing text Provider behavior

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_advisor.py -q
micromamba run -n qi-p0 python \
  .agent/harness/scripts/run-provider-contracts.py
```

Expected: ADV-01、ADV-02、PROV-01、PROV-02 PASS; existing candidate-review fixture and text
cache tests still PASS; Harness reports `external_calls=0`.

### Step 8: Commit only Task 3

```bash
git add \
  backend/app/providers/visual_symbol_review.schema.json \
  backend/app/candidates/symbol_review.py \
  backend/app/providers/base.py \
  backend/app/providers/qwen_vl.py \
  backend/app/candidates/advisor.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  .agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json \
  .agent/harness/scripts/run-provider-contracts.py \
  .agent/harness/scripts/generate-receipt.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/contract/test_provider_call_records.py
git commit -m "feat: freeze visual symbol advisor contract"
```

## Task 4: Add Unified Scheduling, Local Projection And Coverage Writes

**Required test IDs:** ADV-03～ADV-09、COV-01～COV-04

**Files:**

- Modify: `backend/app/candidates/symbol_review.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/candidates/coverage.py`
- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Modify: `backend/tests/unit/candidates/test_coverage.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`

### Step 1: Write seven projection/scheduler RED tests

- [ ] ADV-03 `test_diameter_enriches_existing_candidate`:
  candidate ID and raw text remain unchanged; normalized text contains `Φ`;
  `feature_kind="unknown"`、confirmation true、visual+text source union and bbox union.
- [ ] ADV-04 `test_depth_uses_same_crop_typed_value_or_stays_ambiguous`:
  one same-crop typed value updates/projects; missing、two distinct values or conflict leaves
  original candidate unchanged and visual coverage ambiguous.
- [ ] ADV-05 `test_counterbore_maps_to_stable_composite`:
  only `{counterbore,diameter,depth}` maps; canonical `⌴`; ordered diameter/depth
  sub-requirements; no new public enum.
- [ ] ADV-06
  `test_surface_roughness_maps_to_four_field_coarse_candidate`:
  exact `raw_text/coordinates/coarse_type/requires_confirmation` field set and exactly one
  associated decimal value.
- [ ] ADV-07 `test_gdt_kinds_map_to_four_field_coarse_candidate`:
  parameterize parallelism/perpendicularity/flatness to `∥/⊥/⏥`; exact four fields; one
  tolerance token and allowlisted datum letters only.
- [ ] ADV-08 `test_reference_revision_and_no_detection_dispositions`:
  validated boxed datum becomes reference/no item; exact triangle+inner token revision becomes
  recoverable non-inspection; invalid revision and no detection remain actionable ambiguous.
- [ ] ADV-09
  `test_unified_scheduler_is_deterministic_and_blocks_visual_overflow`:
  exact visual priorities、stable first-fit、visual-first order and text remainder; 17 visual
  batches raise `symbol_route_budget_exhausted`; excess text route remains unchanged without
  provenance.

### Step 2: Write four coverage RED tests

- [ ] COV-01 `test_visual_candidate_has_one_complete_coverage_entry`:
  exactly one primary disposition、candidate ID、visual source、coordinates and text lineage.
- [ ] COV-02
  `test_visual_reference_noninspection_and_ambiguous_are_distinct`:
  disposition and confirmation flags follow the frozen table and do not overwrite each other.
- [ ] COV-03 `test_visual_missing_source_coordinates_or_conflict_blocks`:
  missing source、missing bbox、missing disposition、unexecuted visual batch and duplicate
  visual primary entries are blocking.
- [ ] COV-04 `test_visual_confirmation_cannot_be_downgraded`:
  candidate projection and Provider response cannot clear confirmation; only locally validated
  datum reference may be false.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py -q
```

Expected: the 11 new tests FAIL because schedule、mapping and final writes are absent.

### Step 3: Apply exact visual priority and unified schedule

- [ ] Reuse Task 2 observations、packer and exact constants:
  - padding
    `min(24, max(6, ceil(0.10 * max(union.width, union.height))))` PDF points;
  - max crop area `7.5%` page;
  - render scale `300/72`;
  - precomputed pixel dimensions use `ceil` and each side `<=1536`;
  - max 32 observations per batch.
- [ ] Do not reimplement stable first-fit in candidate code. Pass the exact priority-ordered
  observations to `pack_visual_batches()`; propagate `visual_crop_oversize`.
- [ ] Exact route priority:
  0 for parser-failed numeric/thread text, 1 for existing confirmation candidate, 2 for all
  other visual contexts. Tie-break is
  `(page_index,bbox.y0,bbox.x0,proposal_kind,observation_id)`.
- [ ] Let `V` be visual batch count per page:
  - `V>16` raises `symbol_route_budget_exhausted` before any call;
  - execute all `V` visual calls first;
  - select at most `16-V` existing text routes using the old stable text sort;
  - do not create an “unreviewed” visual state.
- [ ] Render each crop at exact 300 DPI after scheduling; do not downscale.
- [ ] Expose a pure
  `plan_visual_batches(pages, snapshot) -> tuple[tuple[VisualBatch, ...], ...]` function used
  by `CandidateAdvisor` and the current-source preflight. The outer tuple follows page order;
  the inner tuple follows call order. It must not construct Provider、render crop or mutate
  snapshot.

### Step 4: Implement deterministic local projections

- [ ] Add immutable decision boundary:

```python
@dataclass(frozen=True)
class VisualReviewDecision:
    observation_id: str
    disposition: Disposition
    source_location_ids: tuple[str, ...]
    coordinates: BBox
    candidate_id: str | None
    existing_candidate_index: int | None
    candidate_envelope: dict[str, Any] | None
    requires_confirmation: bool
    symbol_kinds: tuple[SymbolKind, ...]
    rejection_code: str | None
```

- [ ] Associated text reading order is
  `(page_index, angle % 360, bbox.y0, bbox.x0, observation_id)`.
- [ ] Only these kind sets are projectable:
  `{diameter}`、`{depth}`、`{diameter,depth}`、
  `{counterbore,diameter,depth}`、one roughness、one of three GD&T、one datum or one
  revision. All other sets return `visual_projection_conflict`.
- [ ] Diameter:
  run existing `parse_annotation()` against canonical `Φ` plus same-crop native text; retain
  source `raw_text`; set normalized symbol、unknown feature kind and confirmation.
- [ ] Depth:
  accept one same-crop typed value only; single-line uses parser output; multi-line reuses
  existing composite shape. Never choose nearest/max/provider value.
- [ ] Counterbore:
  require all three kinds and parser-valid diameter/depth sources; output existing composite
  with order 0 diameter and order 1 depth; prepend canonical `⌴` only to normalized text.
- [ ] Roughness:
  require exactly one distinct ASCII decimal token; emit only the frozen four fields.
- [ ] GD&T:
  require exactly one tolerance decimal; accept source-ordered single uppercase datum tokens;
  emit only the frozen four fields with canonical symbol.
- [ ] Datum:
  use the reconstructed canonical path items to require a locally validated boxed datum
  letter; disposition `reference_context`,
  confirmation false, no item.
- [ ] Revision:
  use the reconstructed canonical path items to require a three-straight-segment closed
  path、closure distance `<=0.5 pt`、bbox width/height in `[4,24] pt` and one
  `[A-Z0-9]{1,3}` token inside or within `2 pt`; disposition
  `non_inspection`, `candidate_id=None`, confirmation true, and no automatic item. A later
  explicit Quality Owner `promote_source` is a working-copy manual override, not a Provider or
  local-projection output.
- [ ] No detection:
  ambiguous、confirmation true、`visual_no_detection`.
- [ ] Candidate coordinates are the exact union of visual and all participating text bboxes;
  source IDs include both families in stable order.
- [ ] Existing candidate match preserves its candidate ID. New candidate ID is
  `stable_candidate_id("visual-candidate/1", *sorted_source_ids, projection_type)`.
- [ ] Existing typed depth mismatch、two primary candidates or source conflict leaves existing
  payload byte-equivalent and returns ambiguous.

### Step 5: Deduplicate and perform the only writes

- [ ] Convert Provider bboxes to page coordinates before dedupe.
- [ ] For same page/kind with
  `intersection_area / min(area_a,area_b) >= 0.8`, retain stable reading-order first and union
  source IDs. Provider response order must not affect output.
- [ ] `CandidateAdvisor.review()` is the only caller that:
  - replaces the initial visual coverage entry;
  - updates an existing candidate or appends one new envelope;
  - records Provider call IDs;
  - recomputes duplicate suggestions only when candidates changed.
- [ ] Per visual coverage `advisor_review` has the exact key set
  `route/schema_version/symbol_kinds/rejection_code`:
  `route` is `visual_symbol`; schema is `visual-symbol-review/1`; kinds are the sorted unique
  actual validated allowlist values (empty on no detection); rejection is null or one frozen
  local code from `visual_bbox_invalid`、`visual_source_mismatch`、
  `visual_duplicate_detection`、`visual_local_parse_failed`、
  `visual_projection_conflict` or `visual_no_detection`.

No model、prompt text、crop body、response、confidence or explanation is exposed.

### Step 6: Strengthen coverage completeness

- [ ] `check_coverage()` accepts the existing expected ID set plus a
  `required_visual_observation_ids` set.
- [ ] Mark blocking when a required visual ID:
  - occurs zero or more than once;
  - lacks source、coordinates or valid primary disposition;
  - has candidate disposition without candidate ID;
  - remains tagged internally as unscheduled;
  - belongs to a budget/crop failure.
- [ ] Continue counting ambiguous and confirmation-required entries as review required, not
  formal success blockers by themselves.

### Step 7: Verify GREEN and old Advisor regression

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_parser.py \
  backend/tests/unit/candidates/test_grouping.py \
  backend/tests/unit/candidates/test_complex_fallback.py \
  backend/tests/unit/candidates/test_duplicates.py -q
```

Expected: ADV-03～ADV-09 and COV-01～COV-04 PASS; all existing text parsing、grouping、
coarse fallback、dedupe and Advisor tests PASS.

### Step 8: Prove the current two-page source fits the hard budget

This is a deterministic no-Provider preflight. It uses the exact source whose bytes were
sealed in Task 1 and prints only batch counts, never its path or content.

```bash
PYTHONPATH=backend micromamba run -n qi-p0 python -c \
  'import sys; from pathlib import Path; from app.pdf.inventory import build_inventory; from app.processing.automatic_result import candidate_snapshot_from_inventory; from app.candidates.symbol_review import plan_visual_batches; pages = build_inventory(Path(sys.argv[1])); snapshot = candidate_snapshot_from_inventory(pages); planned = plan_visual_batches(pages, snapshot); counts = tuple(len(page_batches) for page_batches in planned); assert len(counts) == 2 and all(count <= 16 for count in counts), counts; print("visual_batches_per_page=" + ",".join(map(str, counts)))' \
  "$QI_SYMBOL_SOURCE_PDF"
```

Expected: two comma-separated counts, each `<=16`. If this fails, stop with
`symbol_route_budget_exhausted`; do not tune thresholds or silently drop observations to make
the source pass.

### Step 9: Commit only Task 4

```bash
git add \
  backend/app/candidates/symbol_review.py \
  backend/app/candidates/advisor.py \
  backend/app/candidates/coverage.py \
  backend/app/processing/automatic_result.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/unit/candidates/test_advisor.py
git commit -m "feat: project visual symbols through candidate owner"
```

## Task 5: Wire The Canonical Runtime, Failure Veto And Idempotent Result

**Required test IDs:** INT-01～INT-06

**Files:**

- Create: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Modify: `backend/app/processing/runtime_recognition.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/app/processing/tasks.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_processing_entry_task.py`
- Modify: `backend/tests/integration/test_task_idempotency.py`
- Modify: `backend/tests/integration/test_result_layers.py`
- Modify: `backend/tests/integration/test_review_working_copy.py`
- Modify: `backend/tests/integration/test_review_operations.py`
- Modify: `backend/tests/integration/test_error_records.py`

### Step 1: Write all six logical integration RED tests plus one supporting regression

- [ ] INT-01
  `test_vector_fixture_builds_visual_candidate_and_working_copy`:
  sanitized PDF → native/visual inventory → injected fake Provider → candidate/coverage →
  persisted AutomaticResult → one working copy; assert source IDs and no fixture manifest input.
- [ ] INT-02
  `test_diameter_depth_and_counterbore_group_as_one_annotation`:
  each combination produces one primary candidate and one item, no duplicate visual/text item.
- [ ] INT-03
  `test_roughness_gdt_and_datum_project_without_schema_expansion`:
  roughness/GD&T use existing coarse shape; datum is coverage reference and absent from items;
  `CandidateType`/`CoarseType` sets remain unchanged.
- [ ] INT-04
  `test_visual_provider_failure_prevents_ready_for_edit`:
  parameterize unavailable、invalid root schema、invalid cache/audit、crop oversize、budget
  overflow and coverage conflict; no AutomaticResult/working copy; project failed with exact
  sanitized code/stage/category.
- [ ] INT-05
  `test_visual_no_detection_remains_actionable_source_review`:
  no-detection entry has page/bbox/source and can execute existing `promote_source` or
  `ignore_source`; it never silently enters active items before the command.
- [ ] INT-06 `test_visual_processing_replay_is_idempotent`:
  second canonical logical task call returns the first result ref; raw/working counts remain
  one; Provider call count increment is zero; a late failure cannot overwrite the winner.
- [ ] Supporting regression
  `test_revision_marker_stays_noninspection_until_explicit_promote_source`:
  assert the automatic result and initial working copy contain
  `non_inspection + candidate_id=null + requires_confirmation=true` coverage and no item for a
  qualifying revision marker; no Provider、validator、automatic processing or frontend-derived
  path promotes it. On independent working-copy branches, an explicit Quality Owner
  `promote_source` with all existing required manual fields creates exactly one manual item,
  while explicit `ignore_source` resolves confirmation with no item. This supporting regression
  is not a new logical ID; the Required Test Matrix remains exactly 32.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_symbol_recognition_pipeline.py -q
```

Expected: FAIL because canonical runtime、failure mapping and result bootstrap are not wired to
the visual decisions.

### Step 2: Wire one canonical processing path

- [ ] `RuntimeRecognition.build_inventory()` continues to call the single native inventory
  builder, which now includes visual observations. OCR behavior remains unchanged.
- [ ] `RuntimeRecognition.build_candidate_snapshot()`:
  1. builds the deterministic text+initial-visual snapshot once;
  2. attaches OCR request IDs;
  3. calls the existing `CandidateAdvisor.review()` once with source PDF and all pages;
  4. returns the Advisor result to the existing `InventoryPipeline`.
- [ ] `tasks.py::inventory_project` keeps one `CandidateAdvisor` injection and the existing
  `VISION_PROVIDER_FACTORY`; do not construct a visual-only Advisor or task.
- [ ] A fake Provider in tests implements both `review_candidate()` and `review_symbols()` but
  is injected through the same production seam.

### Step 3: Map failures without leaking details

- [ ] Root Provider/schema/cache failures remain:

```text
code=vision_provider_call_failed
stage=candidate_advisor
cause_category=transient_provider_failure
```

- [ ] `symbol_route_budget_exhausted` and `visual_crop_oversize` use:

```text
code=symbol_route_budget_exhausted or visual_crop_oversize
stage=candidate_advisor
cause_category=processing_defect
```

- [ ] Coverage incompleteness remains:

```text
code=coverage_blocking
stage=coverage
cause_category=processing_defect
```

- [ ] Error messages must be constant sanitized summaries. No source path、crop、SDK body、
  Provider content、credential or associated customer text.
- [ ] All failures happen before `build_automatic_result()` commits
  `processing → ready_for_edit`.

### Step 4: Preserve immutable raw/working layers

- [ ] `ReviewService.create_from_raw()` continues to create items only from candidate envelopes.
- [ ] It keeps visual/text `source_location_ids` and `normalized_text` in item payload.
- [ ] `_review_coverage()` strips `advisor_review` before exposing the mutable working copy,
  just as it does for text Advisor provenance, but retains the local Owner-committed
  `symbol_kinds` needed to distinguish a qualifying revision marker from no-detection; it must
  not derive that discriminator in the frontend.
- [ ] Both source-review states remain present and distinct with source、bbox、disposition and
  confirmation:
  - no-detection is `ambiguous + visual_no_detection`;
  - qualifying revision marker is
    `non_inspection + candidate_id=null + requires_confirmation=true`.
  Existing source commands may act only after an explicit Quality Owner command.
- [ ] Existing raw result immutability tests add an assertion that creating/reviewing a new
  symbol result does not mutate an old text-only result.

### Step 5: Preserve logical task winner semantics

- [ ] Cache and Provider work only occur inside the first active logical task execution.
- [ ] On replay after success, return the already persisted `job.result_ref` before rebuilding
  inventory or constructing Provider.
- [ ] If another worker commits success first, losing failure cannot alter result、project or
  job state.
- [ ] Use the existing `LogicalJob` and idempotency implementation; do not add an app-level
  symbol idempotency key.

### Step 6: Verify GREEN and runtime regressions

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_error_records.py \
  backend/tests/integration/test_processing_state.py -q
```

Expected: INT-01～INT-06 and
`test_revision_marker_stays_noninspection_until_explicit_promote_source` PASS; existing
canonical task、result-layer、review and error tests PASS; all fixture tests report no external
call. The supporting regression does not change the 32 logical-ID count.

### Step 7: Commit only Task 5

```bash
git add \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/app/processing/runtime_recognition.py \
  backend/app/processing/pipeline.py \
  backend/app/processing/tasks.py \
  backend/app/review/service.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_error_records.py
git commit -m "feat: persist visual symbol recognition results"
```

## Task 6: Project Visual Sources And Separate Raw From Recognized Text

**Required test IDs:** FE-01～FE-03

**Files:**

- Modify: `backend/app/projects/router.py`
- Modify: `backend/tests/integration/test_project_workbench_api.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

### Step 1: Write backend projection RED

- [ ] Extend
  `test_project_workbench_projects_source_only_coverage_for_review` with one visual
  observation and assert:

```json
{
  "id": "visual-observation-id",
  "item_ids": [],
  "page_index": 0,
  "bbox_pdf": [60.0, 70.0, 100.0, 90.0],
  "raw_text": "图形符号待确认",
  "source_type": "visual"
}
```

- [ ] Existing native source response adds `source_type="text"` without changing its ID、
  page、bbox or raw text.
- [ ] `advisor_review`、geometry hash、associated text IDs and Provider response are absent
  from the API.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_workbench_api.py \
  -k "source_only_coverage" -q
```

Expected: FAIL because `_project_pages()` only indexes `observations` and source responses have
no source type.

### Step 2: Write all three frontend RED tests

- [ ] FE-01 in `ReviewPanel.test.tsx`:
  `shows raw_and_normalized_symbol_text_separately`. Render `raw_text="10"` and
  `normalized_text="Φ10"`; assert editable “图纸原文” remains `10`, read-only “识别结果”
  is `Φ10`, and no normalized field appears when both strings are equal.
- [ ] FE-02 in `InspectionItemTable.test.tsx`:
  `renders_coarse_symbol_and_confirmation`. Parameterize roughness and three GD&T coarse
  items; assert Owner-provided coarse type/canonical symbol and “需确认” are visible; unknown
  coarse type remains the existing safe empty-state label.
- [ ] FE-03 in `PdfWorkspace.test.tsx`:
  `locates_and_actions_visual_source`. Parameterize an
  `ambiguous + visual_no_detection` source and a qualifying
  `revision_marker + non_inspection` source. Selection moves to the persisted page/bbox; the UI
  respectively shows “图形符号待确认” and “修订标记（非检验）待确认”. Through
  `InspectionWorkbench.test.tsx`, only explicit Quality Owner actions emit existing
  promote/ignore commands, and no Provider response or frontend-inferred promotion is rendered.

```bash
npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
```

Expected: the three focused cases FAIL because TS types and UI distinctions are absent.

### Step 3: Add one source lookup, not one endpoint

- [ ] `_project_pages()` indexes both:
  - existing `page["observations"]` as source type `text`;
  - additive `page.get("visual_observations", [])` as source type `visual`.
- [ ] Visual source lookup uses its persisted page/bbox and constant display text
  `图形符号待确认`; it does not expose geometry/proposal/provider fields.
- [ ] `_project_items()` continues to project only coverage entries requiring confirmation and
  without candidate IDs as pending sources. Reference contexts do not enter the list; revision
  non-inspection with confirmation and ambiguous no-detection do, retaining the backend
  Owner-committed disposition and `symbol_kinds` so they remain distinguishable.
- [ ] Do not add a second workbench endpoint or database query.

### Step 4: Extend frontend API types additively

- [ ] Add `normalized_text?: string` to the existing `ReviewItem` type and
  `source_type: "text" | "visual"` to the existing `ProjectWorkbenchSource` type.

- [ ] Extend `OverlayBox` and `PendingSourceReview` with optional/stable source type propagation.
  Do not make old fixture objects invalid where the existing tests intentionally construct
  partial overlays.

### Step 5: Render Owner output without frontend inference

- [ ] `ReviewPanel`:
  - keep `raw_text` as the only editable source field;
  - if trimmed `normalized_text` is non-blank and differs, render a read-only “识别结果” row;
  - do not include normalized text in edit command fields;
  - do not derive a symbol from CSS or string matching.
- [ ] `InspectionItemTable`:
  - ambiguous no-detection label is “图形符号待确认”; qualifying revision-marker label is
    “修订标记（非检验）待确认”;
  - the promote editor still requires explicit Quality Owner action、non-blank operator text
    and existing `CandidateType`;
  - reuse existing `promote_source` and `ignore_source`; a revision-marker promotion is a human
    override from initial non-inspection, while ignore confirms non-inspection with no item;
  - frontend copy、symbol matching、CSS or model output cannot invoke or simulate either command;
  - coarse visual items display only fields already committed by backend Owner.
- [ ] `PdfWorkspace`:
  - continue using persisted bbox and page transform;
  - visual source selection/zoom follows the existing source path;
  - do not add image upload or model call.
- [ ] Add only necessary Chinese copy and scoped styles consistent with the approved information
  hierarchy; do not restore duplicate item headings.

### Step 6: Verify GREEN, full frontend and build

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_workbench_api.py -q
npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/ProjectWorkbenchApp.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
npm --prefix frontend run build
```

Expected: FE-01～FE-03 PASS; workbench source-only、dirty-draft、selection and build gates
PASS.

### Step 7: Run integrated browser QA

- [ ] Start the approved local/QA runtime without changing committed runtime config.
- [ ] Use Chrome DevTools MCP to verify one fixture project at desktop viewport:
  - raw and recognized values are simultaneously visible;
  - ambiguous no-detection and qualifying revision-marker noninspection are visibly distinct,
    and both source selections locate the correct page/bbox;
  - promote/ignore remain explicit Quality Owner actions guarded by unsaved-draft behavior;
  - no Provider JSON appears in DOM、network response or console;
  - no new console error or failed request.
- [ ] Save only sanitized textual observations; do not save current-source screenshot into Git.

### Step 8: Commit only Task 6

```bash
git add \
  backend/app/projects/router.py \
  backend/tests/integration/test_project_workbench_api.py \
  frontend/src/api/types.ts \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/ProjectWorkbenchApp.tsx \
  frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx \
  frontend/src/components/pdf/PdfWorkspace.tsx \
  frontend/src/components/pdf/PdfWorkspace.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: review visual symbol sources"
```

## Task 7: Close Sanitized E2E And Full Regression

**Required test IDs:** E2E-01～E2E-02

**Files:**

- Create: `backend/tests/e2e/test_symbol_recognition.py`
- Modify only when an additive assertion is necessary:
  `backend/tests/e2e/test_offline_automatic_result.py`
- Modify only when an additive assertion is necessary:
  `backend/tests/e2e/test_offline_vertical.py`
- Modify only when an additive assertion is necessary:
  `backend/tests/e2e/test_no_silent_success.py`

### Step 1: Write both E2E tests through canonical seams

- [ ] E2E-01 `test_symbol_fixture_positive_flow`:
  create the sanitized PDF, upload/process through the canonical task with a frozen fake
  Provider, then compare generated candidates/coverage/working copy against the independent
  fixture manifest. Assert exact-one match for all 19 positive regions and
  `external_calls=0`.
- [ ] E2E-02 `test_symbol_fixture_negative_regions_do_not_create_items`:
  assert all 12 frozen negative regions have zero overlapping candidate/reference/item and do
  not disappear from the fixture comparison.
- [ ] The fake Provider receives only crop bytes and prompt, derives its response from the
  synthetic observation IDs included in the prompt, and never reads the expected manifest.
- [ ] Do not reuse the live current-source labels or real Provider response.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/e2e/test_symbol_recognition.py -q
```

Expected before final E2E assertions are wired: FAIL on exact positive/negative comparison.
Expected after implementation: two tests PASS and report zero external calls.

### Step 2: Run the complete focused 32-check gate

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py -q
npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
```

Expected: all 32 required IDs are collected and PASS. Verify collection explicitly:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py \
  --collect-only -q
```

Expected: each exact backend test name in the Required Test Matrix appears; frontend test names
are verified by Vitest output. A parameterized test may emit multiple cases but does not reduce
the 32 logical IDs.

### Step 3: Run explicit existing-behavior regression

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_parser.py \
  backend/tests/unit/candidates/test_grouping.py \
  backend/tests/unit/candidates/test_complex_fallback.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/e2e/test_offline_automatic_result.py \
  backend/tests/e2e/test_offline_vertical.py \
  backend/tests/e2e/test_no_silent_success.py -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: all existing suites PASS without skip/count relaxation; text-only candidate payload、
coverage、working-copy creation and export-facing result layers remain compatible.

### Step 4: Run contract, policy and privacy checks

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/run-provider-contracts.py
git diff --check
rg -n \
  "(Authorization:|BEGIN (RSA|OPENSSH) PRIVATE KEY|credential=|password=|api[_-]?key=|data:image/.+base64,|/home/|/Users/)" \
  backend/app/pdf/visual_observations.py \
  backend/app/candidates/symbol_review.py \
  backend/app/candidates/advisor.py \
  backend/app/providers/visual_symbol_review.schema.json \
  backend/tests/helpers/symbol_fixture.py \
  .agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json
```

Expected: contract check and provider fixture runner exit 0; diff check is clean; `rg` returns no
match. Do not scan or print `.env` values.

### Step 5: Use the repository smoke-test skill

- [ ] Invoke `auto-feature-smoke-test` after all implementation commits, following its current
  `SKILL.md`.
- [ ] Record its commands and results in the current-plan amendment. A skipped runtime check
  must name a real blocker and cannot be treated as a pass.

### Step 6: Independent read-only review

- [ ] Use one `reviewer` agent after the code diff is complete. Its prompt must state:
  role `reviewer`; exact file/diff scope; read-only authority; no file modifications; no nested
  delegation; stop on higher-rule conflict; expected verdict/blockers/concerns/evidence/files;
  commands run or why unavailable.
- [ ] Reviewer must specifically inspect:
  - single Owner and old silent-truncation retirement;
  - no false symbol semantics or hole inference;
  - exact source/bbox/coverage lineage;
  - visual budget blocking;
  - Provider/schema/cache redaction;
  - old text route and idempotency regression;
  - test independence from expected manifests.
- [ ] Parent verifies every blocking claim directly and applies only minimal fixes with focused
  reruns. Core-behavior fixes require a second read-only review of the final diff.

### Step 7: Commit only Task 7

```bash
git add \
  backend/tests/e2e/test_symbol_recognition.py
git commit -m "test: cover symbol recognition end to end"
```

If additive assertions were required in the three existing E2E files, stage those exact files
in the same command. Do not stage any generated local run、cache、screenshot or test-results
directory.

## Task 8: Execute Sealed Current-PDF Acceptance And Hand Back To D7-T3

**Required test ID:** LIVE-01

**Files:**

- Create: `.agent/harness/scripts/symbol_eval.py`
- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Modify: `.agent/harness/scripts/live_evidence_policy.py`
- Modify: `.agent/harness/schemas/live-run-evidence.schema.json`
- Modify: `.agent/harness/policy/p0-acceptance-policy.yaml`
- Modify:
  `backend/tests/contract/harness/test_symbol_eval_contract.py`
- Modify:
  `backend/tests/contract/harness/test_live_run_contract.py`
- Modify:
  `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
- Modify: `.agent/harness/contracts/p0-contracts.json`（generated）
- Modify: `.agent/harness/contracts/global-contract-bindings.json`（generated）
- Modify:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`

### Step 1: Write LIVE-01 and run RED against synthetic result objects

- [ ] Add `test_sealed_current_pdf_symbol_manifest` to
  `test_symbol_eval_contract.py`. It uses a temporary sealed artifact and synthetic actual
  result objects to prove:
  - positive candidate exact-one matching;
  - reference/non-inspection matching against the pre-manual-command Owner result;
  - a qualifying revision marker is exactly
    `non_inspection + candidate_id=null + requires_confirmation=true`;
  - degree zero and degree greater than one fail;
  - detected kind set must equal label kind set;
  - projection must equal expected projection;
  - overlap is
    `intersection_area / min(actual_visual_area, label_area) >= 0.5`;
  - any candidate overlapping `frozen_negative` at the threshold fails;
  - candidate without visual source is excluded from visual eval;
  - visual candidate without one positive edge fails.
- [ ] Add a live-run contract test proving `--symbol-eval-run` requires one literal sealed
  staging run and the full run binds both manifest and annotation-verdict bytes.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py \
  -k "symbol" -q
```

Expected: FAIL because the evaluator、live phase and artifact loader are absent.

### Step 2: Implement a post-result-only evaluator

- [ ] `symbol_eval.py` accepts only parsed manifest、inventory visual observations、
  raw candidates and raw coverage. It must never participate in proposal、prompt、Provider or
  candidate construction.
- [ ] Candidate visual bbox is the union of all visual IDs in `source_location_ids`.
- [ ] Detected kinds are the sorted unique union of coverage
  `advisor_review.symbol_kinds` for those visual IDs.
- [ ] Build graph edges only when page、exact kinds、exact projection and overlap threshold all
  match.
- [ ] Enforce exact degree one on both candidate-label sides, exact single match for
  reference/non-inspection labels, and zero negative overlaps.
- [ ] Return a sanitized report containing counts、label IDs、candidate IDs、dispositions、
  overlap ratios and pass/fail reasons. Do not include source text、PDF bytes、host path、
  Provider response or crop.

### Step 3: Bind the evaluator to the existing full live run

- [ ] Add CLI `--symbol-eval-run` to `run-p0.py`; it must accept the same literal run-ID regex
  used by current-four registration, reject aliases/symlinks/writable sealed paths, validate
  both schemas and recompute input identity.
- [ ] Copy exact artifact bytes into the full live run before any Provider call.
- [ ] Add one selector
  `phase://live/symbol-recognition?input_set=current-four`.
- [ ] Execute it for the first checkpoint source hash only, after automatic candidate/coverage
  persistence and before any `promote_source` / `ignore_source` command or quality-owner
  item-set acceptance.
- [ ] It loads the new project’s immutable raw result and inventory, calls only
  `symbol_eval.py`, stores a sanitized report, and blocks the run on any mismatch.
- [ ] Add live evidence fields:
  manifest SHA、verdict SHA、label/per-family counts、visual call counts per page、match counts、
  negative false-positive count and report ref.
- [ ] Enforce actual visual calls `<=16/page`; text+visual total also `<=16/page`.
- [ ] Do not reuse an old project result. The current source must be uploaded as a new project
  within the bound live run.
- [ ] Add `symbol_eval.py`、its schema/policy dependencies and selector identity to the existing
  controlled-code inventory in `generate-receipt.py`; the live receipt must bind their exact
  bytes.

### Step 4: Re-run Harness GREEN before spending Provider calls

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py \
  backend/tests/contract/harness/test_receipt_policy.py -q
```

Expected: LIVE-01 synthetic contract cases PASS; artifact/schema/code/input identities are
closed; no network call has occurred.

### Step 5: Commit the live gate before any Provider call

```bash
git add \
  .agent/harness/scripts/symbol_eval.py \
  .agent/harness/scripts/run-p0.py \
  .agent/harness/scripts/generate-receipt.py \
  .agent/harness/scripts/live_evidence_policy.py \
  .agent/harness/schemas/live-run-evidence.schema.json \
  .agent/harness/policy/p0-acceptance-policy.yaml \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py
git diff --cached --check
git commit -m "test: bind live symbol recognition gate"
git show --format=%H --no-patch HEAD
```

Expected: the gate code、tests、schema and policy share one committed code identity. Record that
literal commit SHA for the run; do not execute the live selector against uncommitted gate code.

### Step 6: Materialize and execute the literal live command

- [ ] Read the exact current-four registration run ID and the exact symbol-eval staging run ID
  recorded in the activated current-plan amendment.
- [ ] Invoke `run-p0.py live --scope full-p0 --input-set current-four` with both IDs written
  literally in the shell command. Do not use `latest`、glob、command substitution or an
  environment-variable alias for either ID.
- [ ] The plan intentionally does not invent future run IDs. If either literal is absent, stop;
  this is a real evidence blocker, not a value to guess.
- [ ] Required result for the first two-page source:
  - source SHA exact match;
  - every positive label has exactly one edge;
  - every participating visual candidate has exactly one positive edge;
  - reference and pre-manual revision-marker non-inspection labels match exactly;
  - frozen-negative false positives zero;
  - no positive `visual_no_detection`;
  - no projection conflict、coverage blocking、crop oversize or budget exhaustion;
  - visual and total Vision calls at most 16 per page;
  - project uses a new raw result; old result bytes/count remain unchanged.
- [ ] Continue the existing current-four live sequence only if the first checkpoint and the
  symbol selector pass. Do not use success on the remaining three PDFs to mask a first-source
  failure.

### Step 7: Perform real browser evidence

- [ ] Through the existing authenticated/approved project workbench, use Chrome DevTools MCP
  to verify on the new project:
  - at least one diameter/depth/counterbore item shows source raw text and recognized canonical
    symbol separately;
  - one roughness/GD&T coarse item shows confirmation state;
  - one visual source can be located to the correct page/bbox and acted with the existing
    review command;
  - no Provider response is present;
  - refresh preserves result identity and does not repeat Provider calls.
- [ ] Bind sanitized browser evidence to the same run/project/result identity. Do not commit
  current-source screenshot.

### Step 8: Final receipt update without prematurely completing D7-T3

- [ ] When all checks pass:
  - change amended `P0-REC-005/009/010` statuses from `pending` to `passed`;
  - regenerate both JSON mirrors;
  - record Task SR-1～SR-8 commits、32-check result、existing regression result、live run ID、
    receipt ID and reviewer verdict in the current-plan amendment;
  - state that D7-T2 symbol closure is complete and D7-T3 may now resume.
- [ ] Do **not** mark D7-T3 complete in this task; D7-T3 still owns final receipt enforcement、
  rollback proof and overall independent review.

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
git diff --check -- \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
  docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md
git add \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
  .agent/harness/contracts/p0-contracts.json \
  .agent/harness/contracts/global-contract-bindings.json \
  docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md
git diff --cached --check
git commit -m "docs: record live symbol recognition evidence"
```

## Rollback Plan

Rollback is an explicit current-plan action, not silent fallback:

1. Stop new uploads and do not delete sealed runs、cache or Provider call records.
2. Mark the symbol receipt failed/stale and record the blocking code in the current plan.
3. Revert Task 8 → Task 2 commits in reverse order with `git revert` and each exact commit hash
   recorded during execution.
   Do not reset、force-push or overwrite unrelated dirty files.
4. Revert Task 1 contract/Harness amendment only after the code commits are reverted; keep the
   immutable historical evidence directories untouched.
5. Revert Task 0 activation last, adding a note that D7-T3 remains blocked by the original
   missing-symbol defect.
6. Run the preserved text-path baseline:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_parser.py \
  backend/tests/unit/candidates/test_grouping.py \
  backend/tests/unit/candidates/test_complex_fallback.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_result_layers.py -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: old text-only baseline PASS; symbol capability is absent and D7-T3 remains explicitly
blocked. Rollback does not convert the original missing-symbol behavior into accepted success.

## Completion Checklist

- [x] User approved this subordinate implementation proposal.
- [x] Task 0 activated exactly one current plan at commit `994cbe4`; Option A clarification is
  active and Task 0 must not be repeated.
- [ ] Stable contract Owners were amended before production GREEN.
- [ ] Quality Owner sealed exact live labels and 200% overlay verdict before production GREEN.
- [ ] Staging mechanically proved all nine positive families and all nine distinct
  `negative_family` values; `negative_family_count=9` was derived from the manifest rather than
  entered by a human.
- [ ] All 32 required logical tests exist and pass.
- [ ] Existing text/OCR/parser/Advisor/result/frontend regression suites pass without relaxation.
- [ ] Provider contract/cache/call records are schema-bound and redacted.
- [ ] No visual observation is silently unscheduled or missing a coverage disposition.
- [ ] Current-source live result passes exact-one positive/reference/non-inspection matching and
  zero negative false positives.
- [ ] Actual visual and total Vision calls are within 16 per page.
- [ ] A new project/result was used; old immutable results remain unchanged.
- [ ] Chrome evidence proves raw/recognized separation and visual source recovery.
- [ ] `auto-feature-smoke-test` completed or reports a real blocker.
- [ ] Independent reviewer verdict is `accept` or all blocking issues were fixed and re-reviewed.
- [ ] D7-T2 symbol closure is recorded; D7-T3 is resumed, not prematurely marked complete.

## Execution Handoff

Task 0 is complete at commit `994cbe4`, Option A clarification is active, and execution resumes
at Task 1 / `SR-1` contract/Harness RED. Do not repeat Task 0 or append another activation
amendment. The two implementation modes remain:

1. `superpowers:subagent-driven-development` in this session, with one bounded writer at a time
   and mandatory read-only reviewer checkpoints.
2. `superpowers:executing-plans` in a fresh isolated execution session.

Repository ordering overrides both choices: start with Task 1 / `SR-1`; its sealed live-label
gate must be satisfied before any production GREEN.
