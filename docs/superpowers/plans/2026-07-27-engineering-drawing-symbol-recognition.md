# Engineering Drawing Symbol Recognition Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留已验证 high-recall proposal、Provider schema 和 Quality Owner gate
的前提下，把默认生产路径收敛为可解释、可审计、低延迟的疑难 ROI uncertainty
router，并以 additive partial/progressive contracts 保留局部失败之外的正式结果。

**Architecture:** `build_page_visual_observations()` 只拥有 proposal admission；
`resolve_visual_observation()`、`route_visual_observation()` 和
`plan_symbol_escalation_batches()` 分别拥有 local resolution、escalation 和 ROI
scheduling。只有 reason-coded unresolved observation 进入 cache/Provider。
`CandidateAdvisor` 保持 candidate/coverage/completeness semantic Owner；
`build_automatic_result()` 保持唯一 persistence Executor。旧
`legacy_high_recall` route 在正式 evidence gate 前只保留，不成为新生产默认。

**Tech Stack:** Python 3.11、PyMuPDF、SQLAlchemy/Alembic、JSON Schema、
OpenAI-compatible Qwen API、React/TypeScript、pytest、Vitest、P0 Harness

---

## Status And Authority

- Date: `2026-07-29`
- Selected lane: `Heavy`
- Status: `PRT-1 committed; PRT-2 next`
- Current parent plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- Current branch/worktree: `codex/symbol-production-routing` /
  `/home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing`
- Selection evidence: 用户在 design commit
  `4541c47dacb591f5c40cf3709d55d48163f82713` 后明确回复“执行,subagent”；
  canary `d61ec678-0133-4a22-ba55-b7dc58d26edf` 已证明 correctness 和 schema
  validity，但 `205 observations -> 29 calls -> 513.44s` 不满足生产体验。
- Writer ownership and order: parent agent 是 plan/contract 唯一 writer；每个
  `PRT-*` task 只有一个 sequential code writer，之后依次做独立 spec review 和
  quality review。Explorer、auditor、reviewer 和 OSS researcher 始终只读。
- Validation action: `amend -> continue`；每个 code task 严格
  RED -> minimal GREEN -> focused regression -> review -> exact commit。
- Next verification: `PRT-2` planner/mode RED in
  `test_symbol_routing.py + test_project_intake_api.py +
  test_project_status_api.py + test_schema.py`。
- This file owns only the bounded symbol-recognition convergence steps below. It
  does not become a second current plan and cannot authorize `D7-T3`、`SR-5`、
  `main` merge or frontend work outside the exact `PRT-6` files and checks.
- 本文件顶部和下方 `Production Routing Implementation` 是当前可执行部分；
  historical diagnostic/remediation/canary outcome 仅作为 immutable evidence，
  不得重放其 Provider/browser authorization。
- This compact plan supersedes the previous executable body at commit
  `5ad308ad97137b4dc9783b95aaa32c82e8b6ee36`. Git preserves that complete
  4067-line historical plan; none of its unchecked boxes remain executable.

## Why This Plan Was Converged

The prior plan no longer represented runtime truth:

- activation `994cbe4` 到当前 diagnostic amendment `ba4339b` 跨约 `47.96h`；
- 该区间有 `59` commits，其中 `35` 个 docs-only、`24` 个 code/test；
- live-gate commit `47571c7` 之后又产生 `41` commits，其中 `27` 个 docs-only；
- current parent plan 在同一区间被修改 `34` 次，其中 `23` 次只是
  `authorize/record`；
- Harness 保留 `12` 个 `full-p0/live` runs，全部 `failed`；
- 旧 subordinate plan 有 `216` 个未完成 checkbox，但其顶部仍错误声称
  `SR-4` 未提交且下一步是 `SR-2C`。

因此，旧文件已从执行计划退化为 append-only 历史记录。继续向其追加 recovery
amendment 会扩大 control-plane drift；本次直接以当前代码、tests、sealed runtime
evidence 和下面的唯一 blocker 重新建立执行边界。

## Verified Current Truth

### Implementation

以下能力已经提交，不得按旧 checkbox 重做：

- sealed symbol input/evaluation contract: `d3fac79`
- deterministic visual observations: `bb035bc`
- frozen Provider schema/adapter contract: `90bfb43`
- proposal gate and candidate projection through live Harness:
  `0876587..47571c7`
- prompt、forced-tool、lineage、projection and exact-reporting recovery:
  `9d9f99e..f47d2c3`
- proposal v3 compaction: `0a59798`、`efea8f7`
- sanitized failure classification、bounded schema retry、bbox normalization、
  deterministic sampling and safe schema diagnostics:
  `68ff9ad`、`e9fd7a7`、`8af2870`、`df06405`、`163e0a5`

Latest committed implementation verification remains:

- full backend: `704 passed`
- Provider fixtures: `50 passed`, `external_calls=0`
- contracts、Ruff、privacy、smoke and independent review: passed

这些证据证明 local implementation contract；它们不证明 production Qwen 会稳定返回
schema-valid tool arguments。

### Latest Live Failure

- run: `20260729T051043520116Z-8ddc6a1a`
- project: `217e3b9d-b5f8-44a6-b2c5-ed19f8bf4679`
- state: `failed / processing_failed`
- first seven visual calls: schema-valid caches
- eighth primary call and its single bounded retry:
  `tool_arguments_schema_invalid`
- target cache key:
  `22a5fe3f35c2cac609bfac570e167dff7d4b7ca759f7bac234779cd5919ac49a`
- target crop SHA-256:
  `5628b3603d6fa7f12d62a637a438740a92f29dd81e2a9de689e492b1dcb53724`
- downstream result counts: `AutomaticResult=0`、working copy `=0`、
  reviewed result `=0`、balloon `=0`、export `=0`

The strongest current conclusion is narrow: production Qwen response conformance
is not stable under the frozen request. No schema leaf or safe remediation has yet
been proven.

## Historical Diagnostic Owner And Unchanged Contract

- `backend/app/providers/qwen_vl.py::QwenVisionProvider.review_symbols()` owns the
  production request and response-shape classification.
- `backend/app/candidates/symbol_review.py::parse_visual_symbol_json()` owns frozen
  local schema validation.
- `backend/app/candidates/advisor.py::CandidateAdvisor` owned automatic
  candidate/coverage/completeness submission for this diagnostic;
  `build_automatic_result()` was and remains the persistence Executor. The
  diagnostic bypassed both without creating a second business Owner.
- Preserve model `qwen3-vl-plus-2025-12-19`、adapter `/4`、prompt v4、response
  schema v1、`temperature=0`、SDK `max_retries=0`、timeout、crop bytes and prompt
  bytes.
- Do not relax schema、normalize new fields、change paging/call cap、switch model、
  add fallback/repair/shadow paths or infer a fix from one response.

## Historical Diagnostic Execution Veto

Until this plan records a completed diagnostic outcome:

- no `full-p0` start or resume;
- no project upload/retry for diagnostic purposes;
- no production、test、schema、prompt、frontend or Harness code change;
- no second direct Provider call;
- no execution of any checkbox from commit `5ad308a` or earlier plan bodies;
- no new append-only recovery amendment in this file. Update `Current Outcome`
  in place instead.

If any source、inventory、batch、cache、crop、prompt、model、adapter、schema or runtime
identity differs, stop before Provider construction.

## Task 1: Execute The One Authorized Exact-Crop Diagnostic

**Files:**

- Modify after the call:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`
- Do not modify: production、tests、frontend、Harness code、sealed runs/projects
- Write only one temporary artifact:
  `/tmp/qi-symbol-schema-diagnostic.*/targeted-diagnostic-report.json`

- [x] **Step 1: Commit the parent-plan authorization**

Authorization commit: `ba4339bde8e2e71adb1bafcca019109ae5816d3e`.

- [x] **Step 2: Complete the no-write reconstruction**

Verified without Provider construction/calls:

```text
source_sha256=58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec
inventory_sha256=8febd89e877fac8589b295172199ba45970acc0cd16a5ae226ae999ae9f95e8b
inventory_exact=true
page_visual_counts=80/125
page_batch_counts=13/16
target_page_index=0
target_batch_index=7
target_member_count=6
cache_key=22a5fe3f35c2cac609bfac570e167dff7d4b7ca759f7bac234779cd5919ac49a
crop_sha256=5628b3603d6fa7f12d62a637a438740a92f29dd81e2a9de689e492b1dcb53724
prompt_sha256=5fad9a4a5a063b64114a4ca674e613f8822918891acbac5327033cb2a75caae5
prompt_bytes=5226
provider_construction=0
provider_calls=0
```

- [x] **Step 3: Revalidate runtime identity immediately before the call**

Required:

```text
API health=ok
worker=running
model=qwen3-vl-plus-2025-12-19
qwen_vl.py=23e8753dc2e577b87c9a011bab80441f38b5598184cc039c781028c58d340356
symbol_review.py=73edf98326c6521121cb80ad3f58c83db4e43f9722a1709ef1fa6261a1854461
providers/runtime.py=1774815f29ca8302f7869697cafbc45c1cabc8f508b8a19c7ba4eb92cbff42f8
```

Expected: host、API and worker hashes match; credentials are checked only for
presence and are never printed.

Verified on `main`: API health `ok`、worker `running`、host/API/worker source and
schema hashes matched, model and credential-presence checks passed, and the
source/inventory/batch/cache/crop/prompt identities from Step 2 reproduced
exactly with Provider construction/calls=`0/0`.

- [x] **Step 4: Invoke the production Provider method exactly once**

Use the reconstructed in-memory crop and canonical prompt to call only:

```python
QwenVisionProvider.review_symbols(crop_png, prompt)
```

Do not call `CandidateAdvisor`、write storage、open a formal Harness run or retry.
The exact-once authorization is session-bound; this plan intentionally does not
provide a reusable shell replay command.

The sole invocation returned `tool_arguments_schema_invalid` after `5632ms` with
request ID `chatcmpl-e1d0556c-0624-913e-ad5b-aebdeb5061a7`. The allowlisted
diagnostic identifies a root-object `required` failure for missing
`schema_version`; direct Provider method invocations=`1`.

- [x] **Step 5: Write and hash one sanitized report**

Allowlisted report fields:

```text
schema/version identities
source/inventory/cache/crop/prompt/payload hashes
page/batch/member counts
request_id
duration_ms
usage
outcome
detection_count OR allowlisted schema diagnostic
formal_run_created=false
project_created=false
cache_written=false
response_retained=false
direct_provider_method_invocations=1
```

Never retain raw tool arguments、payload values、validation message、drawing text、
image bytes or credentials. Set report and containing directory read-only, compute
SHA-256, then update `Current Outcome` in place and commit only this file.

Sanitized report:

```text
path=/tmp/qi-symbol-schema-diagnostic.EVhSLo/targeted-diagnostic-report.json
sha256=e3590660a0b445fcc2e18040308a7fa77ef6c75c43c8dc9f4142db0c8cc64467
directory_mode=500
report_mode=400
```

## Outcome Branch And Stop Condition

- Schema-invalid: record only the existing allowlisted diagnostic and stop. It is
  evidence for a later Owner decision, not authorization to relax or repair schema.
- Schema-valid: record detection count and canonical payload hash, then stop. One
  success confirms intermittency but does not establish stability.
- Transport/timeout failure: record the existing sanitized stage and stop.

All branches consume the one-call authorization. None authorizes another direct
call、production fix、full-P0、manual approval、D7-T3、SR-5 or merge.

## Full-P0 Re-entry Gate

`full-p0` remains blocked until a later user decision supplies all of:

1. one evidenced root-cause hypothesis;
2. one bounded remediation contract with exact Owner/old-path action;
3. focused RED/GREEN and independent review;
4. an isolated live canary budget and acceptance rule appropriate to the observed
   failure mechanism.

Do not use full-P0 to discover whether a proposed fix works.

## Rollback

如果本次计划收敛被否决，只回退该 docs-only commit，恢复 commit `5ad308a`
保存的完整历史文本；不得回退 implementation、runtime 或 sealed evidence。
rollback 后第一项验证是：

```bash
python .agent/harness/scripts/check-contracts.py
```

## Current Outcome

```text
status=completed_schema_invalid
main_commit=b215def608602159bae8692c93390d54548da0d2
request_id=chatcmpl-e1d0556c-0624-913e-ad5b-aebdeb5061a7
duration_ms=5632
usage=3419/185/3604
failure_stage=tool_arguments_schema_invalid
schema_validator=required
schema_instance_path=""
required_member=schema_version
payload_sha256=5db34d6143679e064c3fc758d3caf22e2e9a4c75beee869b47055b491f79b7bc
report_path=/tmp/qi-symbol-schema-diagnostic.EVhSLo/targeted-diagnostic-report.json
report_sha256=e3590660a0b445fcc2e18040308a7fa77ef6c75c43c8dc9f4142db0c8cc64467
direct_provider_method_invocations=1
authorization_consumed=true
formal_run_created=false
project_created=false
cache_written=false
response_retained=false
full_p0_blocked=true
next_action=stop
```

## Remediation Amendment: Missing Structural Schema Version

### Selection Record

- Selected lane: `Standard`
- Selected plan:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`
- Selection evidence:
  - 用户在 `main` 明确要求修复真实上传失败；
  - browser upload project
    `e3cd58e8-37e6-4321-adb8-84c49838a738` 已证明 upload `202`、worker
    received、24 次 Provider HTTP `200`，最终因
    `tool_arguments_schema_invalid` fail closed；
  - 该 project 有 `23` 个 schema-valid cache 和 `1` 个 sanitized failure
    record；失败 cache key 为
    `21bb2e2e1198f459cb0e088211192761ce253ed4980790e04501e229448f11f7`，
    crop SHA-256 为
    `0a2b5ddf4f3d66135995139934cea2119d0adbd797e250bcca61365f7b0973e0`；
  - 该 project 的 formal evidence 只证明 schema failure family；上面的
    completed exact-crop diagnostic 已独立证明同一 production Provider 会
    偶发省略根级 required member `schema_version`；
  - current adapter 已拥有 Qwen-native bbox normalization，但未处理这个
    deterministic structural constant omission。
- Validation action: `amend`；目标和唯一 Owner 不变，新增 bounded
  remediation、cache identity bump 和 focused regression checks。
- Writer ownership and order:
  - parent agent 是唯一 writer；
  - read-only explorer 只提供 call-chain evidence；
  - implementation 完成后由独立 read-only reviewer 审查；
  - 不允许 concurrent writer。
- Next verification: 先新增 missing-`schema_version` focused contract test 并
  确认 RED；不得在 RED 前修改 production。

### Problem Boundary And Root-Cause Hypothesis

本 amendment 只处理一个已证实的 Provider serialization failure：

```text
otherwise schema-valid root object
+ detections is an array
+ schema_version key is absent
→ strict response schema rejects the payload
→ CandidateAdvisor fails closed
→ project never reaches the Quality Owner gate
```

Root-cause hypothesis：Qwen 偶发省略 response schema 中值固定的结构性
discriminator；`QwenVisionProvider` adapter 只归一化 Qwen-native integer bbox，
因此在 strict local validation 前没有补齐该 deterministic constant。该问题位于
Provider adapter boundary，不是上传、frontend、transport、schema 或业务
projection failure。

新 project 没有持久化 leaf-level diagnostic，因此不得声称它已证明同一个 leaf；
它只提供同一 failure family 的 current live evidence。修复依据来自上面 sealed
exact-crop diagnostic 的 missing-`schema_version` leaf 证据。

### Owner, Old Path And Unchanged Contract

- Single Owner:
  `backend/app/providers/qwen_vl.py::_normalize_qwen_native_visual_payload()`
  owns the deterministic Provider-native repair before frozen validation.
- Old path action: replace the incomplete normalization path that only repairs
  integer bbox scaling. Do not add a fallback, bridge, shadow parser or second
  response Owner.
- Repair only when all are true:
  - decoded payload is a root object;
  - `detections` is an array;
  - the `schema_version` key is completely absent.
- Inject only canonical `VISUAL_SCHEMA_VERSION`.
- Preserve fail closed for wrong/null `schema_version`、missing/non-array
  `detections`、extra properties and every invalid detection member.
- Bump `VISUAL_ADAPTER_VERSION` from `/4` to `/5` so old cache identity cannot be
  reused under changed normalization semantics.
- Unchanged:
  - response schema `visual-symbol-review/1`;
  - prompt `visual-symbol-prompt/4`;
  - forced tool、`temperature=0`、SDK `max_retries=0`、timeout；
  - CandidateAdvisor retry/call-cap/paging and fail-closed behavior；
  - candidate projection、review、balloon、export and frontend contracts；
  - model `qwen3-vl-plus-2025-12-19`.

### Allowed Files

- `backend/app/providers/qwen_vl.py`
- `backend/app/candidates/symbol_review.py`
- `backend/tests/contract/test_qwen_symbol_provider.py`
- `.agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json`
- this plan, for amendment and final verified outcome only

No production schema、advisor、pipeline、frontend、sealed run/project/manifest or
credential file may change.

### Required RED/GREEN And Verification

1. RED:
   - otherwise-canonical payload missing only `schema_version` must expect the
     canonical payload and fail against adapter `/4`;
   - negative controls must keep wrong/null version、missing detections and extra
     root fields schema-invalid.
2. GREEN:
   - implement the three-condition repair and `/5` cache identity bump;
   - update only the sanitized Provider fixture identity.
3. Focused:
   - Qwen Provider contract tests;
   - Advisor and Provider call-record regression tests;
   - symbol recognition integration/e2e fixture tests with
     `external_calls=0`.
4. Repository:
   - contracts、Ruff、privacy scan、full backend and `git diff --check`.
5. Independent read-only review must verify Owner uniqueness、negative controls、
   cache invalidation and absence of schema/retry/frontend changes.

The remediation amendment itself did not authorize a live Provider call、
UI retry/upload、API/worker rebuild or `full-p0`. The separately authorized
browser canary below is the only successor live action.

### Rollback

Rollback only the remediation implementation commit and its fixture/test identity
updates; do not alter sealed evidence or historical projects. The first
post-rollback verification is:

```bash
pytest -q backend/tests/contract/test_qwen_symbol_provider.py
```

### Current Remediation State

```text
status=implementation_committed_canary_authorized
branch=main
implementation_commit=da846bb638bf72e7a54a003746cfb7232a8030c2
owner=QwenVisionProvider_adapter
old_path_action=replace_incomplete_qwen_native_normalization
schema_contract_changed=false
retry_or_call_cap_changed=false
frontend_changed=false
focused_provider_contracts=18_passed
symbol_integration_e2e=16_passed
provider_fixtures=56_passed_external_calls_0
full_backend=710_passed
independent_review=accept_with_concern_resolved
live_provider_calls_authorized=one_browser_upload_existing_caps
full_p0_blocked=true
next_action=browser_canary
```

## Browser Canary Authorization

用户在 implementation GREEN、full backend 和 independent review 后明确要求：
“修复完了再次用浏览器上传”。该授权只允许下面一次 browser canary，不授权
formal `full-p0`、direct Provider diagnostic 或自动 retry。

### Identity And Runtime

- source filename: `JS26032501-1-03-036#上下座B#A1.pdf`
- source SHA-256:
  `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec`
- implementation commit:
  `da846bb638bf72e7a54a003746cfb7232a8030c2`
- model: `qwen3-vl-plus-2025-12-19`
- adapter: `qwen-openai-compatible/5`
- response schema: `visual-symbol-review/1`
- UI: keep the current `main` UI at `http://127.0.0.1:5173/`

Rebuild and recreate only API/worker from `main`; do not rebuild、restart or
replace frontend. Before the upload, require:

- API health `ok` and worker `running`;
- host/API/worker hashes match for `qwen_vl.py` and `symbol_review.py`;
- runtime model and adapter match the identities above;
- credential presence may be checked, but values must never be read or printed.

### Exact Budget And Stop Rule

- Browser file selection count: exactly `1`.
- Browser submit click count: exactly `1`.
- Project creation count: exactly `1`.
- Direct Provider calls: `0`.
- Provider calls may occur only through that project’s existing bounded
  CandidateAdvisor path and existing unchanged call caps.
- Do not click `重新处理`、reselect、submit a second project or run a targeted call.
- Acceptance:
  - if the project reaches the Quality Owner review gate, record the exact
    project route and stop; do not approve;
  - if it fails, record only sanitized project/call evidence and stop; do not
    fix or rerun;
  - if runtime/source identity differs, stop before file selection.

This browser canary consumes the authorization regardless of outcome. It does
not unblock formal `full-p0`、D7-T3、SR-5 or any later main merge/push.

### Browser Canary Outcome

The authorization was consumed exactly once:

```text
status=ready_for_review
project_id=d61ec678-0133-4a22-ba55-b7dc58d26edf
task_id=5ddd2b20-1ca0-4ec1-a017-9dc17c7ed831
automatic_result_id=578ca69b-5d6a-43ab-8597-26646ba1f1fa
duration_seconds=513.4402794169728
browser_file_selections=1
browser_submit_clicks=1
project_creations=1
direct_provider_calls=0
candidate_advisor_call_records=29
schema_failure_records=0
schema_valid_cache_records=29
workbench_ready=true
retryable=false
quality_owner_actions=0
frontend_rebuilt=false
screenshot=/tmp/qi-symbol-repair-canary-ready.png
screenshot_sha256=516075f12ce2d8d3eaffbd79228ae6de83d4fa121695ef52052383f2910c5a8e
authorization_consumed=true
full_p0_blocked=true
next_action=quality_owner_manual_review
```

The current SPA remains at `/` and retains the project in browser-local context.
The stable compatibility route is:

```text
http://127.0.0.1:5173/?project_id=d61ec678-0133-4a22-ba55-b7dc58d26edf
```

No review confirmation、freeze、balloon generation、export、retry or second upload
was executed.

## Production Routing Implementation

### Activation And Stop Boundary

- Design source:
  `docs/superpowers/specs/2026-07-29-symbol-recognition-production-routing-design.md`.
- Parent activation:
  `D7-T2 Symbol Recognition Production Routing Implementation Amendment`.
- Current implementation tasks: `PRT-0` through `PRT-7`, in exact order.
- `PRT-8` live canary/promotion is intentionally absent from the authorized task
  list. It requires a separate committed parent amendment after offline evidence.
- `legacy_high_recall` remains preserved. No task below deletes it、marks it for
  removal、changes a historical result or imports its `/5` cache into the new
  namespace.
- No task below may read credentials、make Provider live calls、upload a PDF or
  run formal live Harness.

### Owner Matrix

| Dimension | Unique Owner | Executor / consumer | Forbidden second owner |
|---|---|---|---|
| Proposal admission | `build_page_visual_observations()` | Page Inventory | budget/router |
| Local resolution | `resolve_visual_observation()` | `CandidateAdvisor` | Provider/frontend |
| Escalation decision | `route_visual_observation()` | ROI scheduler | cache/outcome |
| ROI scheduling/budget | `plan_symbol_escalation_batches()` | `CandidateAdvisor` | proposal gate |
| Candidate/coverage/completeness semantics | `CandidateAdvisor` | pipeline | persistence/frontend/Harness |
| Final persistence | `build_automatic_result()` | SQLAlchemy Session | semantic recomputation |
| Manual closure | Review aggregate / Quality Owner | workbench | automatic router |

### PRT-0: Amend Stable Contracts And P0 Bindings

**Files:**

- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Modify:
  `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
- Generate only:
  `.agent/harness/contracts/p0-contracts.json`
- Generate only:
  `.agent/harness/contracts/global-contract-bindings.json`
- Modify after verification:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`
- Test:
  `.agent/harness/scripts/check-contracts.py`
- Test:
  `backend/tests/contract/harness/test_contract_architecture.py`

- [x] **Step 0: Record the docs-only TDD exemption and baseline**

`PRT-0` changes contract/traceability documents only, so production-code TDD is
not applicable. Its pre-change baseline replaces RED:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python .agent/harness/scripts/check-contracts.py
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_contract_architecture.py -q
```

Expected baseline: both pass before edits. After edits, they must still pass while
the affected P0 bindings remain `not_run` or explicitly blocked until new evidence.

- [x] **Step 1: Amend stable contract semantics**

Amend only the existing Owners:

- `CAND-004`: proposal admission and reason-coded escalation are independent;
  only unresolved/conflicting/unknown ROI reaches Provider.
- `CAND-005`: budget/localized failure preserves complete unresolved coverage and
  may yield `partial_review_required`; identity/conflict corruption remains
  blocking.
- `REV-002`: automatic result adds versioned completeness and may bind immutable
  preview revisions; partial is formal immutable evidence but not completeness,
  freeze、balloon or export success.
- `PROV-005`: visual primary-group and actual-attempt budgets are separate; retry
  does not increase primary 4/page or 8/project counts, while every actual
  failure/retry consumes unified 16/page and wall time; cache hit requires
  compatible provenance.
- `DIAG-003`: `local_ready`、`vlm_enriching`、terminal completeness and call/budget
  summaries are observable but never determine business success.
- `SYS-006`/`PRJ-002`: reader-first compatibility and project-frozen recognition
  mode/router version.

- [x] **Step 2: Amend P0 bindings without false closure**

Update `P0-REC-005/009/010`、`P0-RES-001/008`、
`P0-UI-004/006/008` and `P0-ACC-002/007` with the new contract delta and exact
future verification. `P0-RES-008` must explicitly retain:

```text
cross_project_cache_status=blocked_missing_security_scope_owner
project_local_content_cache_allowed=true
```

Do not mark a new proof `passed` before its actual command/evidence exists.

- [x] **Step 3: Verify and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python .agent/harness/scripts/generate-contract-mirror.py
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python .agent/harness/scripts/generate-global-bindings.py
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python .agent/harness/scripts/check-contracts.py
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_contract_architecture.py -q
git diff --check
```

Commit only the two contract files and this status update:

```bash
git add docs/contracts/MAIN_CONTRACT_MATRIX.md \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
  .agent/harness/contracts/p0-contracts.json \
  .agent/harness/contracts/global-contract-bindings.json \
  docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md
git commit -m "docs: activate production symbol routing contracts"
```

**PRT-0 evidence (`2026-07-29`):**

- Pre-change docs-only baseline:
  `check-contracts.py` reported `global_contracts=69`、`p0_contracts=111`、
  `mirror_drift=0`、`bindings_drift=0`; contract architecture reported
  `29 passed`.
- The two registered generators wrote only
  `.agent/harness/contracts/p0-contracts.json` and
  `.agent/harness/contracts/global-contract-bindings.json`.
- Post-change verification reported the same `69/111` counts、zero mirror/binding
  drift、zero unclassified/duplicate/missing/unbound/conflict counts and
  `definition_hash_stable_under_status_only_change=1`; contract architecture
  reported `29 passed`; `git diff --check` passed.
- Projection audit found exactly the ten requested P0 rows in the generated mirror
  and only `SYS-006`、`CAND-004`、`CAND-005`、`REV-002`、`DIAG-003` binding
  membership deltas. All ten production-routing proof rows remain `not_run`.
- Initial commit:
  `530853a01bed603e46f409ad2839f009ba343d77`.
- Spec-review gap: `P0-RES-001` 未把 reader-first automatic-result semantics
  与 project intake 时冻结的 recognition mode/router identity 绑定到
  `PRJ-002`; review fix commit:
  `d06341c533a542e7fd906d46c360b70d7465f8cd`.
- Review-fix verification: registered generation changed only `P0-RES-001` in
  `p0-contracts.json` and only `PRJ-002` binding membership; task ID remains
  `D3-T2` and status remains `not_run`. `check-contracts.py` reported `69/111`
  contracts、zero drift/conflict/missing counts; contract architecture reported
  `29 passed`; `git diff --check` passed.

Rollback is:

```bash
git revert <PRT-0-commit>
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python .agent/harness/scripts/check-contracts.py
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_contract_architecture.py -q
```

The next verification after commit is the literal `PRT-1` missing-module RED for
`test_local_symbol_resolution.py + test_symbol_routing.py`.

### PRT-1: Add Pure Local Resolution And Reason-Coded Routing

**Files:**

- Create: `backend/app/candidates/local_symbol_resolution.py`
- Create: `backend/app/candidates/symbol_routing.py`
- Create: `backend/tests/unit/candidates/test_local_symbol_resolution.py`
- Create: `backend/tests/unit/candidates/test_symbol_routing.py`
- Reuse unchanged:
  `backend/app/candidates/symbol_review.py::project_visual_observation()`

**Frozen local rule boundary:**

- an associated existing candidate is locally resolved only when source IDs,
  same-page coordinates, parsed typed fields and projection all agree;
- diameter/depth may resolve from existing `diameter_dimension`、`thread` or
  `composite` typed fields only; bare numeric text is insufficient;
- roughness may resolve only from an already typed coarse roughness candidate with
  exact associated source and no conflicting family;
- the three GD&T families have no current exact local-kind classifier and always
  escalate in this P0 even when a generic geometric-tolerance coarse candidate
  exists;
- datum/revision may resolve only when replaying both allowlisted family
  hypotheses through the common `project_visual_observation()` projection
  validator yields exactly one non-ambiguous result; the resolver must not import
  or duplicate its private geometry helpers;
- counterbore has no current safe local classifier and therefore escalates;
- zero/multiple family matches、missing source、cross-page source、projection
  conflict or unknown family never resolve locally;
- no decision may use one confidence threshold.

**Nine-family rule/test matrix:**

| Family | Local positive | Near-miss / conflict | Required routing |
|---|---|---|---|
| `diameter` | one same-source typed `diameter_dimension`/compatible composite; common projection agrees | bare linear number、nominal mismatch、multiple associated candidates | resolve only positive; otherwise escalate |
| `depth` | one typed `depth`/`thread_depth`/composite depth matching source and value | naked number、missing depth field、different existing value | resolve only positive; otherwise escalate |
| `counterbore` | none; no safe local classifier exists | any counterbore-like numeric grouping | always escalate |
| `surface_roughness` | exact-source already typed roughness coarse candidate with nonnumeric family evidence and common projection agreement | bare decimal、dimension overlap、multiple coarse families | resolve only positive; otherwise escalate |
| `gdt_parallelism` | none; current coarse candidate cannot prove exact GD&T kind | generic geometric-tolerance coarse candidate or datum conflict | always escalate |
| `gdt_perpendicularity` | none; current coarse candidate cannot prove exact GD&T kind | generic geometric-tolerance coarse candidate or datum conflict | always escalate |
| `gdt_flatness` | none; current coarse candidate cannot prove exact GD&T kind | generic geometric-tolerance coarse candidate or numeric-only text | always escalate |
| `datum_reference` | only its allowlisted hypothesis yields a non-ambiguous common projection | revision hypothesis also passes、invalid frame/leader、multiple letters | resolve only exact-one positive; otherwise escalate |
| `revision_marker` | only its allowlisted hypothesis yields a non-ambiguous common projection | datum hypothesis also passes、open/non-triangle geometry、multiple tokens | resolve only exact-one positive; otherwise escalate |

Every row needs one positive-or-always-escalate test, one near-miss test and one
conflict test. `PRT-7` must report the always-escalate families explicitly; it may
not hide them behind aggregate local-resolution counts or claim the performance
gate before the measured call budget passes.

- [x] **Step 1: Write RED tests**

Required tests:

```text
test_locally_complete_diameter_skips_escalation
test_locally_complete_depth_skips_escalation
test_counterbore_without_typed_evidence_escalates
test_roughness_requires_exact_typed_source
test_each_gdt_family_always_escalates_without_exact_local_kind
test_datum_requires_exact_one_projection
test_revision_requires_exact_one_projection
test_conflicting_family_evidence_escalates
test_unknown_reason_fails_closed
test_every_admitted_observation_has_exactly_one_disposition
test_reason_codes_are_sorted_unique_and_replay_stable
test_confidence_only_cannot_resolve_or_escalate
```

Run and require missing-module/test RED:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_local_symbol_resolution.py \
  backend/tests/unit/candidates/test_symbol_routing.py -q
```

- [x] **Step 2: Implement minimal GREEN**

Add immutable dataclasses:

```text
LocalResolution
RoutingDecision
RoutingDisposition =
  locally_resolved | escalate | block
```

Reason arrays are allowlisted、sorted、deduplicated and exact-one by disposition.
The resolver emits evidence only; the router chooses disposition only. Neither
module calls Provider、cache、storage、DB or frontend.

- [x] **Step 3: Verify and commit**

Run the RED command plus:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/candidates/test_symbol_advisor.py -q
git diff --check
```

After independent spec and quality reviews:

```bash
git add backend/app/candidates/local_symbol_resolution.py \
  backend/app/candidates/symbol_routing.py \
  backend/tests/unit/candidates/test_local_symbol_resolution.py \
  backend/tests/unit/candidates/test_symbol_routing.py
git commit -m "feat: add explainable symbol uncertainty router"
```

**PRT-1 evidence (`2026-07-29`):**

- Initial missing-module RED exited `2` with two collection errors for
  `app.candidates.local_symbol_resolution`.
- The first GREEN reported `39 passed`; independent reviews then reproduced
  false-local-positive and malformed-contract gaps. Three bounded review-fix
  RED rounds reported `15 failed / 41 passed`、`13 failed / 58 passed` and
  `3 failed / 72 passed` before their minimal fixes.
- Final focused verification reported `75 passed`; unchanged
  `test_visual_observations.py + test_symbol_advisor.py` reported `82 passed`;
  focused Ruff and `git diff --check` passed.
- Independent spec and quality reviews accepted the final four-file diff with no
  blocker. Conservative exact coordinate equality may increase escalation rate;
  typed OCR without family-specific deterministic geometry also remains
  escalation because no approved OCR-local reason exists. Either relaxation
  requires measured evidence and a versioned contract amendment.
- Commit:
  `97daeb10dac6a6cac9aa8168d32a97159a3391c5`.

Next verification is the `PRT-2` planner/mode RED. Rollback is
`git revert <PRT-1-commit>` followed by
`test_visual_observations.py + test_symbol_advisor.py`.

### Disposable Migration Verification Boundary

Every `PRT-2/4/5/6` migration proof uses an isolated credential-free PostgreSQL
container, never the running `quality-inspection` database or its named volume.
Before setup, require both inspect commands to report absent; if either target
exists, stop instead of deleting/reusing it.

```bash
if docker container inspect qi-symbol-routing-migration-postgres >/dev/null 2>&1; then
  exit 1
fi
if docker network inspect qi-symbol-routing-migration >/dev/null 2>&1; then
  exit 1
fi
docker network create qi-symbol-routing-migration
docker run --rm -d --name qi-symbol-routing-migration-postgres \
  --network qi-symbol-routing-migration \
  -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine
for attempt in $(seq 1 30); do
  docker exec qi-symbol-routing-migration-postgres \
    pg_isready -U postgres -d postgres && break
  test "$attempt" -lt 30 || exit 1
  sleep 1
done
```

Each Alembic command below runs through:

```bash
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini <arguments>
```

After the task's upgrade/downgrade/upgrade proof, clean up only the exact disposable
targets:

```bash
docker stop qi-symbol-routing-migration-postgres
docker network rm qi-symbol-routing-migration
```

For rollback after a migration commit, first recreate the disposable target at the
committed head, downgrade while the migration file still exists, then clean up,
then `git revert <task-commit>`. Never revert the migration file before downgrade.

### PRT-2: Add Escalation Planner And Project-Frozen Mode

**Files:**

- Modify: `backend/app/candidates/symbol_routing.py`
- Create: `backend/app/candidates/symbol_escalation_planner.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/projects/models.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/projects/router.py`
- Modify: `backend/app/processing/tasks.py`
- Create: `backend/alembic/versions/0008_symbol_routing_mode.py`
- Modify: `backend/tests/unit/candidates/test_symbol_routing.py`
- Modify: `backend/tests/integration/test_project_intake_api.py`
- Modify: `backend/tests/integration/test_project_status_api.py`
- Modify: `backend/tests/integration/test_processing_entry_task.py`
- Modify: `backend/tests/integration/test_schema.py`

- [ ] **Step 1: RED planner and mode tests**

Cover stable dedup/merge order、primary-group budgets `4/page` and `8/project`、
wall budgets `45s/page` and `90s/project`、the existing actual-attempt unified
text+visual `16/page` ceiling、budget denial outcome、default
`legacy_high_recall` and project-frozen `production_uncertainty`. A retry never
increments the 4/8 primary-group counters, but every actual retry increments the
unified 16/page counter and consumes page/project wall time. A projected
concurrent batch that exceeds any applicable counter executes zero members.

Required RED names:

```text
test_planner_enforces_page_project_and_unified_call_budgets
test_retry_preserves_primary_count_but_consumes_actual_and_wall_budget
test_planner_fake_clock_enforces_page_and_project_wall_budgets
test_project_freezes_allowlisted_recognition_mode_at_intake
test_worker_uses_frozen_project_mode_after_settings_change
test_runtime_rejects_verification_high_recall_mode
test_project_schema_has_frozen_symbol_routing_mode
```

`test_project_schema_has_frozen_symbol_routing_mode` checks the current migrated
schema only. The disposable PostgreSQL `upgrade head -> downgrade 0007 -> upgrade
head` commands below are the unique migration downgrade/upgrade evidence; tests
must not downgrade or mock-downgrade the shared integration database.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_symbol_routing.py \
  backend/tests/integration/test_project_intake_api.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_schema.py -q
```

Expected RED: missing recognition settings/columns and planner budget behavior;
unrelated intake/status assertions remain green.

- [ ] **Step 2: GREEN migration and planner**

Add reader-first project columns:

```text
recognition_mode = legacy_high_recall
recognition_router_version = legacy
```

New projects freeze values at intake. Worker reads the row, never a changed
runtime setting. `plan_symbol_escalation_batches()` accepts only `escalate`
decisions and returns stable `EscalationBatch` plus explicit budget outcomes.
`Settings.symbol_recognition_mode` is sourced only from
`QI_SYMBOL_RECOGNITION_MODE` and allowlists
`legacy_high_recall | shadow_uncertainty | production_uncertainty`; default is
`legacy_high_recall`. `projects/router.py::get_project_service()` injects the
frozen value at intake. `verification_high_recall` is rejected by runtime/API and
exists only as a Harness entry. `shadow_uncertainty` runs the legacy route as the
only semantic/final-write path and records only pure uncertainty decisions against
the same observations; it makes no extra Provider call and performs no second
candidate/coverage/result write.
`symbol_escalation_planner.py` owns `plan_symbol_escalation_batches()` and its
immutable proposal、batch、budget and denial records; `symbol_routing.py` retains
only pre-VLM decision and recognition mode/router-version contracts. The planner
exposes `max_in_flight=2` as a named production budget and proves that
window sizes `1` and `2` generate the same stable escalation-group plan. Actual
bounded execution、completion-order equivalence and attempt accounting close in
`PRT-3`, where the Provider execution seam exists.

- [ ] **Step 3: Verify and commit**

Run the RED command, then:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_processing_entry_task.py -q
git diff --check
git add backend/app/candidates/symbol_routing.py \
  backend/app/candidates/symbol_escalation_planner.py backend/app/config.py \
  backend/app/projects/models.py backend/app/projects/service.py \
  backend/app/projects/router.py backend/app/processing/tasks.py \
  backend/alembic/versions/0008_symbol_routing_mode.py \
  backend/tests/unit/candidates/test_symbol_routing.py \
  backend/tests/integration/test_project_intake_api.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_schema.py
git commit -m "feat: freeze symbol routing mode"
```

Migration-specific rollback proof on a disposable database:

```bash
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini downgrade 0007
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
```

If rollback proof fails, do not commit. After commit, next verification is the
`PRT-3` zero-call RED. Rollback recreates the disposable database at committed
head, downgrades to `0007`, cleans up the disposable targets, then runs
`git revert <PRT-2-commit>` and the project-intake/status tests.

### PRT-3: Integrate CandidateAdvisor Without Deleting Legacy

**Files:**

- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/processing/runtime_recognition.py`
- Modify: `backend/app/candidates/symbol_review.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`
- Modify: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Modify: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Modify: `backend/tests/e2e/test_symbol_recognition.py`

- [ ] **Step 1: RED zero-call and mixed-route tests**

Prove:

- locally resolved observations construct no Provider and produce zero visual calls;
- only escalated observations reach the planner;
- mixed local/escalated results retain exact source/coverage;
- `legacy_high_recall` remains byte-compatible;
- invalid/missing routing decision blocks before Provider construction.
- a fake bounded executor proves maximum in-flight visual calls is `2`;
- a failed/retried attempt leaves primary-group count unchanged, increments
  actual/unified call count, consumes wall time and does not create a second
  primary escalation group;
- completion order permutations produce byte-identical final semantics.
- `test_shadow_uncertainty_uses_legacy_final_write_without_extra_provider`
  proves shadow records pure decisions only, with one legacy final write and zero
  additional Provider calls.

Run and require the new zero-call/concurrency assertions to fail:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py -q
```

- [ ] **Step 2: GREEN orchestration**

Split `CandidateAdvisor.review()` into deterministic preparation and enrichment
seams without changing Provider adapter/schema. Reuse
`project_visual_observation()` as the common projection validator. Do not copy its
family projection logic into the resolver. Keep actual attempts counted in the
single `_visual_review_result()` execution seam. The bounded executor submits at
most two compatible batches, checks projected page/project/unified budgets before
submission and merges completed results by stable escalation-group order.

- [ ] **Step 3: Verify and commit**

Run the RED command plus:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/contract/test_qwen_symbol_provider.py -q
git diff --check
git add backend/app/candidates/advisor.py \
  backend/app/processing/runtime_recognition.py \
  backend/app/candidates/symbol_review.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py
git commit -m "feat: route only uncertain symbol regions"
```

All Provider fixtures must report `external_calls=0`. After independent spec and
quality reviews, next verification is `PRT-4` evidence/cache RED. Rollback is
`git revert <PRT-3-commit>` followed by the same unit/integration/e2e command and
one explicit legacy byte-compatibility assertion.

### PRT-4: Add Immutable Routing Evidence And Project-Local Content Cache

**Files:**

- Create: `backend/app/candidates/symbol_cache.py`
- Create: `backend/app/candidates/routing_evidence.py`
- Modify: `backend/app/candidates/models.py`
- Create: `backend/alembic/versions/0009_symbol_routing_evidence.py`
- Modify: `backend/app/candidates/advisor.py`
- Create: `backend/tests/unit/candidates/test_symbol_cache.py`
- Create: `backend/tests/integration/test_symbol_routing_evidence.py`
- Modify: `backend/tests/contract/test_provider_call_records.py`

- [ ] **Step 1: RED evidence/cache tests**

Cover exact-one routing decision、attempt and terminal outcome; immutable
update/delete rejection; content identity/version mismatch; invalid provenance
quarantine; failed response never cached; concurrent same-key writes leave one
schema-valid record; current project consumer provenance is newly recorded.

Run and require missing cache/evidence schema RED:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_symbol_cache.py \
  backend/tests/integration/test_symbol_routing_evidence.py \
  backend/tests/contract/test_provider_call_records.py -q
```

- [ ] **Step 2: GREEN project-local namespace**

Identity binds canonical ROI content hash、model、prompt、schema、adapter、
proposal/router/PyMuPDF versions. Namespace includes the current project security
scope. Use validated immutable records and DB unique/first-writer semantics;
filesystem `os.replace()` alone is not cache CAS.

Do not implement or test cross-project hits. Record that acceptance as blocked by
missing tenant/security Owner.

- [ ] **Step 3: Verify and commit**

Run the RED command plus:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_schema.py \
  backend/tests/unit/candidates/test_symbol_advisor.py -q
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini downgrade 0008
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
git diff --check
git add backend/app/candidates/symbol_cache.py \
  backend/app/candidates/routing_evidence.py backend/app/candidates/models.py \
  backend/alembic/versions/0009_symbol_routing_evidence.py \
  backend/app/candidates/advisor.py \
  backend/tests/unit/candidates/test_symbol_cache.py \
  backend/tests/integration/test_symbol_routing_evidence.py \
  backend/tests/contract/test_provider_call_records.py
git commit -m "feat: persist symbol routing evidence"
```

Independent security/Owner review must accept the project-local boundary. Next
verification is `PRT-5` partial-result RED. Rollback recreates the disposable
database at committed head, downgrades to `0008`, cleans up, then runs
`git revert <PRT-4-commit>` and reruns the RED command; never delete
historical evidence/cache rows manually.

### PRT-5: Persist Terminal Completeness And Localized Partial Failure

**Files:**

- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/app/candidates/models.py`
- Create: `backend/alembic/versions/0010_symbol_result_completeness.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/app/providers/base.py`
- Modify: `backend/app/providers/qwen_vl.py`
- Modify: `backend/app/capabilities/service.py`
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_result_layers.py`
- Modify: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Modify: `backend/tests/integration/test_project_status_api.py`
- Modify: `backend/tests/integration/test_processing_preflight.py`
- Modify: `backend/tests/integration/test_review_freeze.py`
- Modify: `backend/tests/integration/test_balloon_validation.py`
- Modify: `backend/tests/contract/test_qwen_symbol_provider.py`

- [ ] **Step 1: RED partial/systemic tests**

One ROI timeout/transport/schema failure retains sibling local/cache/VLM results
and yields one immutable `partial_review_required` result. Malformed/incompatible
cache provenance is quarantined and treated as a miss. Missing source identity、
invalid routing schema、failure to persist/revalidate newly produced evidence or
conflicting coverage still creates no result. Partial result creates one working
copy, but unresolved confirmation blocks freeze、balloon and export.

Run and require new completeness/partial assertions to fail:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_processing_preflight.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_balloon_validation.py \
  backend/tests/contract/test_qwen_symbol_provider.py -q
```

- [ ] **Step 2: GREEN additive completeness**

Add:

```text
AutomaticResult.completeness = complete | partial_review_required
recognition_mode
router_version
recognition_summary
recognition_evidence_ref
```

Backfill old rows as `complete`. `CandidateAdvisor` submits all semantics;
`build_automatic_result()` validates and persists without recomputing. Terminal
write remains exact-once. Late responses may append audit only and never mutate
the result. Provider failures are classified into sanitized schema、timeout、
transport and unavailable outcomes at the existing adapter boundary. Preflight
remains a hard Veto for legacy/systemic capability failure. A project-frozen
uncertainty route skips vision preflight when escalation count is zero; when
localized escalations exist, sanitized unavailable/timeout/transport/schema
outcomes affect only their bound ROI and use the explicit partial contract.

- [ ] **Step 3: Verify and commit**

Run the RED command plus:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/e2e/test_symbol_recognition.py -q
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini downgrade 0009
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
git diff --check
git add backend/app/processing/automatic_result.py \
  backend/app/candidates/models.py \
  backend/alembic/versions/0010_symbol_result_completeness.py \
  backend/app/candidates/advisor.py backend/app/processing/pipeline.py \
  backend/app/providers/base.py backend/app/providers/qwen_vl.py \
  backend/app/capabilities/service.py backend/app/projects/schemas.py \
  backend/app/projects/service.py backend/app/review/service.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_processing_preflight.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_balloon_validation.py \
  backend/tests/contract/test_qwen_symbol_provider.py
git commit -m "feat: preserve partial symbol results"
```

Independent Owner review must prove cache lookup quarantine and systemic
provenance corruption are distinct. Next verification is `PRT-6` preview RED.
Rollback recreates the disposable database at committed head, downgrades to
`0009`, cleans up, then runs `git revert <PRT-5-commit>` and the
result/status/freeze tests; old rows must still read as `complete`.

### PRT-6: Add Backend-Owned Progressive Preview And Read-Only UX

**Files:**

- Create: `backend/app/processing/recognition_preview.py`
- Modify: `backend/app/candidates/models.py`
- Create: `backend/alembic/versions/0011_recognition_preview.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/processing/runtime_recognition.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/app/processing/tasks.py`
- Modify: `backend/app/jobs/idempotency.py`
- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/projects/router.py`
- Modify: `backend/tests/integration/test_project_status_api.py`
- Modify: `backend/tests/integration/test_project_workbench_api.py`
- Modify: `backend/tests/integration/test_processing_entry_task.py`
- Modify: `backend/tests/integration/test_task_idempotency.py`
- Modify: `backend/tests/integration/test_schema.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`
- Modify: `backend/tests/unit/pdf/test_runtime_ocr.py`
- Create: `backend/tests/integration/test_recognition_preview.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/app/QualityInspectionApp.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Create: `frontend/src/components/workbench/RecognitionPreviewApp.tsx`
- Modify: `frontend/src/app/QualityInspectionApp.test.tsx`
- Create:
  `frontend/src/components/workbench/RecognitionPreviewApp.test.tsx`

- [ ] **Step 1: RED preview/CAS/API/frontend tests**

Cover immutable revision、single-head CAS、refresh、out-of-order/late response、
`local_ready -> vlm_enriching -> terminal`、source-PDF identity and disabled
mutation controls. Frontend must never synthesize a working copy.

Run and require missing preview model/API/component RED:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_recognition_preview.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_schema.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/pdf/test_runtime_ocr.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/app/QualityInspectionApp.test.tsx \
  src/components/workbench/RecognitionPreviewApp.test.tsx
```

- [ ] **Step 2: GREEN preview**

Persist immutable `RecognitionPreviewRevision` plus one mutable CAS head. Add a
read-only `/projects/{id}/recognition-preview` endpoint. Existing `/workbench`
continues to require a real `ReviewWorkingCopy`. Terminal result supersedes the
preview; late response cannot move the head or mutate terminal state.
`RuntimeRecognition` injects a persistence-only preview sink into
`CandidateAdvisor`; the Advisor submits the locally resolved semantic snapshot
before enrichment, and the sink persists without recomputing it. Task/pipeline
own transaction and retry boundaries only.

- [ ] **Step 3: Verify and commit**

Run the RED command plus:

```bash
micromamba run -n qi-p0 npm --prefix frontend run build
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini downgrade 0010
docker run --rm --network qi-symbol-routing-migration \
  -v /home/reggie/vscode_folder/Quality_Inspection/.worktrees/symbol-production-routing/backend:/workspace/backend:ro \
  -w /workspace/backend \
  -e QI_DATABASE_URL=postgresql+psycopg://postgres@qi-symbol-routing-migration-postgres:5432/postgres \
  quality-inspection-api alembic -c alembic.ini upgrade head
git diff --check
git add backend/app/processing/recognition_preview.py \
  backend/app/candidates/models.py \
  backend/alembic/versions/0011_recognition_preview.py \
  backend/app/candidates/advisor.py \
  backend/app/processing/runtime_recognition.py \
  backend/app/processing/pipeline.py backend/app/processing/tasks.py \
  backend/app/jobs/idempotency.py \
  backend/app/processing/automatic_result.py \
  backend/app/projects/schemas.py backend/app/projects/service.py \
  backend/app/projects/router.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_schema.py \
  backend/tests/integration/test_recognition_preview.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  frontend/src/api/types.ts frontend/src/app/QualityInspectionApp.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/components/workbench/RecognitionPreviewApp.tsx \
  frontend/src/app/QualityInspectionApp.test.tsx \
  frontend/src/components/workbench/RecognitionPreviewApp.test.tsx
git commit -m "feat: stream symbol recognition previews"
```

Before commit, use Chrome MCP against a locally seeded fixture project (no upload,
no Provider) and capture four states: `local_ready`、incremental enrichment、
refresh recovery and terminal partial veto. Mutation controls must stay disabled
until a real working copy exists. Next verification is `PRT-7` Harness RED.
Rollback recreates the disposable database at committed head, downgrades to
`0010`, cleans up, then runs `git revert <PRT-6-commit>`, backend preview/API plus
frontend unit/build, and verifies the old workbench flow.

### PRT-7: Add Offline Shadow, Harness And Promotion Evidence Contract

**Files:**

- Modify:
  `.agent/harness/schemas/visual-symbol-eval.schema.json`
- Modify:
  `.agent/harness/scripts/symbol_eval.py`
- Modify:
  `backend/tests/contract/harness/test_symbol_eval_contract.py`
- Modify:
  `backend/tests/contract/harness/test_live_run_contract.py`
- Modify:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`

- [ ] **Step 1: RED evidence contract**

Require both legacy and uncertainty outputs for the same sealed inputs:
admitted/local/escalated/deduped/cache/call/unresolved counts、reason distribution、
cold/warm identity、latency distribution、recall delta、partial outcomes and
Quality Owner verdict refs. No single 513.44s canary becomes a fabricated P50/P95
baseline.

Run and require the new routing/latency/completeness fields to fail schema/tests:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

- [ ] **Step 2: GREEN offline shadow**

Generate fixture-only evidence with `external_calls=0`. Report current
cross-project-cache gate as blocked, not passed. `verification_high_recall` remains
Harness-only and cannot write production results.

- [ ] **Step 3: Repository verification and stop**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python .agent/harness/scripts/check-contracts.py
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 ruff check backend/app backend/tests \
  .agent/harness/scripts
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python \
  .agent/harness/scripts/run-p0.py fixture --scope task --task D7-T2
git diff --check
git add .agent/harness/schemas/visual-symbol-eval.schema.json \
  .agent/harness/scripts/symbol_eval.py \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py \
  docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md
git commit -m "test: gate production symbol routing"
```

Provider-call contract tests are the privacy/sanitization gate; the fixture receipt
must report `external_calls=0`. Run independent final review after the full command
set. Stop before Provider、upload、formal live Harness、production promotion、
old-path mark or `main` merge.

Record exact commits、test counts、remaining blocked gates and the next single
authorization needed for `PRT-8`.

Rollback is `git revert <PRT-7-commit>` followed first by both Harness contract
modules and `check-contracts.py`; preserve the immutable fixture run even if it
becomes stale. The only next verification after successful PRT-7 is a new parent
amendment decision for the still-blocked security-scope cache and `PRT-8`.
