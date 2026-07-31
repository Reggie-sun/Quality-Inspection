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
- Status: `PRT-3 committed at ce546be0dcb4d7ffc8b47b41fa855fd6d6430dfd; PRT-4 next`
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
- Next verification: `PRT-4` missing evidence/cache schema RED in
  `test_symbol_cache.py + test_symbol_routing_evidence.py +
  test_provider_call_records.py`。
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
- `PRT-0` through `PRT-7` are complete. The committed parent amendment below
  defines `PRT-8` as the next task, but the current authorization covers only
  writing、reviewing and committing that amendment.
- `PRT-8` live execution still requires one later explicit user authorization.
  It authorizes one isolated bounded canary only; it does not authorize
  production-default promotion.
- `legacy_high_recall` remains preserved. No task below deletes it、marks it for
  removal、changes a historical result or imports its `/5` cache into the new
  namespace.
- No task except a separately user-authorized `PRT-8` live execution may check
  credential presence、make Provider live calls or upload a PDF. `PRT-8` never
  authorizes printing credential values or running formal live Harness.

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
- Create: `backend/app/candidates/symbol_escalation_contracts.py`
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

- [x] **Step 1: RED planner and mode tests**

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

- [x] **Step 2: GREEN migration and planner**

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
`symbol_escalation_contracts.py` owns the immutable batch/budget records,
canonical content/lineage/budget digests and fail-closed record validation.
`symbol_escalation_planner.py` remains the only owner of escalation-request
admission、dedup/merge planning and budget reservation state transitions;
`symbol_routing.py` retains only pre-VLM decision and recognition
mode/router-version contracts. The planner exposes `max_in_flight=2` as a named
production budget and proves that
window sizes `1` and `2` generate the same stable escalation-group plan. Actual
bounded execution、completion-order equivalence and attempt accounting close in
`PRT-3`, where the Provider execution seam exists.

- [x] **Step 3: Verify and commit**

Run the RED command, then:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_processing_entry_task.py -q
git diff --check
git add backend/app/candidates/symbol_routing.py \
  backend/app/candidates/symbol_escalation_contracts.py \
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

**PRT-2 evidence (`2026-07-29`):**

- Required planner/mode tests were introduced as RED before the minimal
  implementation. Review counterexamples then exposed and closed unstable wall
  accounting、malformed decision/state records、overlap-merge、lineage/budget
  binding、retry identity、hostile collection and empty-family cross-field gaps.
- Final focused `test_symbol_routing.py` verification reported `93 passed`.
  The unchanged local-resolution/routing/visual-observation/advisor regression
  group reported `214 passed`; focused Ruff and `git diff --check` passed.
- On the exact isolated `qi-symbol-routing-migration-postgres` /
  `qi-symbol-routing-migration` targets, Alembic
  `upgrade head -> downgrade 0007 -> upgrade head` succeeded. The four PRT-2
  integration files reported `45 passed` both before and after the rollback
  cycle. Both disposable targets were removed afterward; no live database was
  touched.
- Independent spec and quality reviews both returned
  `accept with concerns` with no blocker. PRT-3 must import the named unified
  `16/page` ceiling, retire the legacy executor-local literal and own actual
  execution/timing evidence. PRT-4 must bind provenance authenticity; current
  digests prove record self-consistency only.
- Commit: `46d3ea77c75deb4e6b21b12aa97046f1955f7f34`.

### PRT-3: Integrate CandidateAdvisor Without Deleting Legacy

**Files:**

- Modify: `backend/app/candidates/local_symbol_resolution.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/processing/runtime_recognition.py`
- Modify: `backend/app/candidates/symbol_review.py`
- Modify: `backend/tests/unit/candidates/test_local_symbol_resolution.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`
- Modify: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Modify: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Modify: `backend/tests/e2e/test_symbol_recognition.py`

**PRT-3 pre-implementation boundary (`2026-07-30`):**

Read-only call-chain mapping proved that production currently has no Owner that
prepares `family_hypotheses` for `resolve_visual_observation()`.
`VisualObservation.proposal_kind` is intentionally generic, and test fixture
label maps or Provider output cannot become pre-VLM evidence. Before Advisor
integration, add one deterministic helper in the existing Local Resolution
Owner. It replays the frozen nine-family resolver with identical immutable local
inputs and returns only families that already produce a complete local
resolution. Zero positives remain unknown and escalate; multiple positives
remain a conflict and escalate. It never invents a learned classifier or turns
counterbore/GD&T near-misses into local success. This bounded amendment adds the
local resolver and its unit test to PRT-3; it does not change the PRT-1 matrix,
Provider schema or final-write ownership.

- [ ] **Step 1: RED zero-call and mixed-route tests**

Prove:

- deterministic family-hypothesis preparation is label-free, replay-stable and
  returns only complete local positives;
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
  backend/tests/unit/candidates/test_local_symbol_resolution.py \
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
It imports `MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE` from the escalation contract Owner,
retires the legacy advisor-local `16/page` constant and carries the exact
observation-member and primary/retry identities into attempt accounting.
`local_symbol_resolution.py` remains the only family-preparation Owner: Advisor
passes the same observation/text/candidate/geometry facts to its deterministic
helper and then to `resolve_visual_observation()`. Advisor must not parse fixture
labels、guess a family from project/runtime identity or use Provider output to
backfill pre-VLM hypotheses.

- [ ] **Step 3: Verify and commit**

Run the RED command plus:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/contract/test_qwen_symbol_provider.py -q
git diff --check
git add backend/app/candidates/local_symbol_resolution.py \
  backend/app/candidates/advisor.py \
  backend/app/processing/runtime_recognition.py \
  backend/app/candidates/symbol_review.py \
  backend/tests/unit/candidates/test_local_symbol_resolution.py \
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
- Modify: `backend/app/processing/tasks.py`
- Create: `backend/tests/unit/candidates/test_symbol_cache.py`
- Create: `backend/tests/integration/test_symbol_routing_evidence.py`
- Modify: `backend/tests/integration/test_schema.py`
- Modify: `backend/tests/contract/test_provider_call_records.py`

`backend/app/processing/tasks.py` is the existing composition root and must
inject the project-scoped cache/evidence services; `CandidateAdvisor` and its
worker threads must not acquire a hidden global session or share the task
session. `backend/tests/integration/test_schema.py` owns the current exact-table
contract and must be amended with migration `0009`.

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
  backend/app/candidates/advisor.py backend/app/processing/tasks.py \
  backend/tests/unit/candidates/test_symbol_cache.py \
  backend/tests/integration/test_symbol_routing_evidence.py \
  backend/tests/integration/test_schema.py \
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

**PRT-7 Step 1 selection record (`2026-07-31`):**

- Selected lane: `Heavy`.
- Selected plan:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`,
  `PRT-7 Step 1` only.
- Selection evidence: feature HEAD
  `41175aa9f359370d9284711c30d685b8c4f15302`, live main
  `ae883c1a8cc09de0cc340aac7b83e86ba36fa17f`, merge-base
  `50d118523181fe2edc9c240afe070faed22a7def`, feature ahead `12` / behind `1`;
  index and unmerged entries are empty; all five PRT-7 paths and all
  non-artifact paths are clean. The sole main-only delta changes
  `design-qa.md`, `ReviewPanel.tsx`, and `ReviewPanel.test.tsx`, with no overlap
  against this step.
- Validation action: `continue`; write only the dual-route offline evidence
  contract tests, run the exact two-file command once RED is written, preserve
  the observed missing-contract failure, complete an independent scoped review,
  and stop before GREEN.
- Problem boundary: one sealed input identity must bind both
  `legacy_high_recall` and `production_uncertainty` offline outputs, including
  admitted/local/escalated/deduped/cache/call/unresolved counts, reason
  distribution, explicit cold/warm identity, raw latency distribution, recall
  delta, completeness/partial outcomes, and Quality Owner verdict refs. A
  single `513.44s` canary is not percentile evidence.
- Owner and old-path action: `CandidateAdvisor` remains the sole
  candidate/coverage/completeness semantic Owner. Harness is an offline evidence
  consumer/validator only. Existing schema and evaluator paths are `preserve`
  during RED; no old path is replaced or marked in this step.
- Unchanged contract: no Provider, upload, browser, formal live Harness,
  production promotion, main merge, push, artifact cleanup, or `PRT-8`; do not
  modify `visual-symbol-eval.schema.json` or `symbol_eval.py` before the expected
  RED is observed.
- Writer ownership and order: the parent is the single sequential TDD writer for
  the two test files and this selection/evidence record; one independent
  read-only reviewer follows the RED command.
- Next verification:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

**PRT-7 bounded scope amendment (`2026-07-31`):**

- User authorization extends only the PRT-7 offline Harness boundary to a
  sanitized `D7-T2` routing-comparison fixture, immutable receipt
  `external_calls` evidence, one stale Harness selector correction, and four
  pre-existing Ruff-only corrections. Harness remains validation-only;
  `verification_high_recall` remains Harness-only and cross-project cache stays
  `blocked_missing_security_scope_owner`.
- New allowed paths are the receipt schema/generator, `run-p0.py`, P0 mirror,
  sanitized manifest fixture, the three named lint-only files, the traceability
  matrix selector Owner, hash-only global bindings, and the two named
  integration-test baseline files. No Provider, upload, browser, formal live
  Harness, promotion, PRT-8, main merge, or push is authorized.
- Runtime rule: any later database verification must use a disposable isolated
  PostgreSQL instance only; never mutate the existing dev or production database.
- Next verification: focused Harness RED/GREEN, `check-contracts.py`, the
  corrected `P0-REC-010` selector, full specified Ruff command, JSON/schema
  validation, and `git diff --check`. Full backend/frontend/build/fixture CLI
  remain a separate next step.

- [x] **Step 1: RED evidence contract**

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

**PRT-7 Step 1 RED evidence (`2026-07-31`):**

- Exact command: the two-file command above.
- Exit code: `1`.
- Result: `3 failed, 83 passed in 5.77s`.
- Expected failures:
  - `test_offline_routing_comparison_schema_is_closed_and_complete`: missing
    `visual-symbol-eval.schema.json#/$defs/routingComparisonEvidence`, so the
    closed schema cannot yet admit the shared sealed identity, dual-mode
    cold/warm outputs, seven routing counts, reason distribution, latency
    distribution, completeness outcomes, recall delta, or Quality Owner verdict
    refs.
  - `test_offline_routing_comparison_validator_binds_modes_to_one_identity`:
    missing
    `symbol_eval.py::validate_routing_comparison_evidence`, so Harness cannot yet
    validate exact legacy/uncertainty × cold/warm membership, sealed/content
    identity agreement, or recall-delta arithmetic without recomputing Owner
    semantics.
  - `test_single_live_canary_cannot_masquerade_as_latency_percentiles`: missing
    `visual-symbol-eval.schema.json#/$defs/latencyDistribution`, so the contract
    cannot yet distinguish one raw `513440.2794169728ms` sample from a measured
    distribution that is eligible to report P50/P95.
- Failure-surface verdict: expected RED. No fixture, collection, environment,
  Provider, upload, browser, formal live Harness, or production path failed.
  `visual-symbol-eval.schema.json` and `symbol_eval.py` remain unmodified.
- Initial scoped review rejected two test-contract gaps: it did not individually
  remove all seven counts / three completeness outcomes / both mode verdict
  refs, and it did not separately cover missing/extra mode-cache membership or a
  valid nonzero recall delta. The parent amended only the RED tests, then reran
  the exact command with exit `1`, `3 failed, 83 passed in 5.68s`; the failure
  surface remained the same three missing PRT-7 contracts.
- Final scoped re-review independently reran the exact command with exit `1`,
  `3 failed, 83 passed in 5.79s`, confirmed the expanded negative controls,
  unchanged schema/evaluator sources, empty index and allowed source diff, and
  returned `accept` with `0 blockers`. Existing `__pycache__` / `.pyc` artifacts
  remain unstaged and unmodified by this step.

**PRT-7 Steps 2/3 selection record (`2026-07-31`):**

- Selected lane: `Heavy`.
- Selected plan:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`,
  `PRT-7 Steps 2 and 3` only.
- Selection evidence: the user selected option A and explicitly authorized
  GREEN, task review, repository/fixture verification, commit and final review
  while retaining the `PRT-8` stop. Feature HEAD is
  `11961086e7a52ac203efbf77e4d9dea5d134ad19`; live main is
  `f01a38883241256dc5f6a966566af0c4c96705b2`; merge-base remains
  `50d118523181fe2edc9c240afe070faed22a7def`; feature is ahead `13` / behind
  `2`. The new main-only `f01a388` delta changes only
  `frontend/src/app/localContext.ts`, `frontend/src/main.tsx`, and
  `frontend/src/main.test.tsx`, with no PRT-7 path overlap.
- Validation action: `continue`; satisfy the accepted Step 1 RED with the
  minimum closed schema definitions and offline validator, then run the exact
  Step 3 commands and independent reviews.
- Problem boundary: Harness validates already-owned offline evidence only. It
  must not calculate candidate, coverage, completeness, recall success or
  promotion success; `CandidateAdvisor` remains the sole business semantic
  Owner. `verification_high_recall` remains Harness-only and
  cross-project cache remains
  `blocked_missing_security_scope_owner`.
- Old-path action: preserve `legacy_high_recall` and the current production
  paths. This task adds no production default, removal mark, fallback, shadow
  writer or second final-write path.
- Writer ownership and order: one bounded sequential `tdd_developer` writer
  owns the five PRT-7 paths, followed by one independent read-only reviewer;
  the parent owns final diff review, Step 3 verification and final decision.
- Next verification:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

- [x] **Step 2: GREEN offline shadow**

Generate fixture-only evidence with `external_calls=0`. Report current
cross-project-cache gate as blocked, not passed. `verification_high_recall` remains
Harness-only and cannot write production results.

- [x] **Step 3: Repository verification and stop**

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
git add .agent/harness/contracts/global-contract-bindings.json \
  .agent/harness/contracts/p0-contracts.json \
  .agent/harness/fixtures/manifests/symbol-routing-comparison-v1.json \
  .agent/harness/schemas/receipt.schema.json \
  .agent/harness/schemas/visual-symbol-eval.schema.json \
  .agent/harness/scripts/generate-receipt.py \
  .agent/harness/scripts/run-p0.py \
  .agent/harness/scripts/symbol_eval.py \
  backend/app/candidates/disposition.py \
  backend/app/candidates/parser.py \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/integration/test_project_intake_api.py \
  backend/tests/integration/test_symbol_routing_evidence.py \
  backend/tests/unit/helpers/test_welli_layout_regression.py \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
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

**PRT-7 Steps 2/3 evidence (`2026-07-31`):**

- Focused TDD closed the accepted RED plus three independent review cycles.
  The final exact two-file Harness command exited `0` with `96 passed`.
  `check-contracts.py` reported `global_contracts=69`, `p0_contracts=111`,
  `mapped=101`, `unclassified=0`, and every drift/conflict count `0`.
- The closed comparison contract binds one sanitized sealed input to exact
  `legacy_high_recall` / `production_uncertainty` × cold/warm outputs, all seven
  routing counts, reason distribution, raw latency samples, completeness
  outcomes, recall delta, and per-mode Quality Owner refs. Harness validates
  identity, membership, sample-count consistency and arithmetic only; it does
  not calculate CandidateAdvisor business verdicts. A single
  `513440.2794169728ms` sample remains ineligible for P50/P95.
- The fixture runner preserves legacy `receipt/1` readability, rejects
  registration-only symbol-eval artifacts from task execution, empties Provider
  credentials, forces offline Provider controls, and binds Python/Node network
  tripwires to a sealed lifecycle proof. Receipt generation independently
  requires an ordered, disjoint, exact partition of attempted, executed and
  pre-execution-blocked selectors before reporting `external_calls=0`;
  non-fixture or incomplete proof reports `null`.
- `P0-REC-010` now selects the existing
  `test_local_symbol_resolution.py::test_conflicting_family_evidence_escalates`
  Owner test. The traceability source, generated mirror and hash-only global
  binding agree. Full Ruff passed after three behavior-neutral baseline lint
  corrections.
- On a fresh, migrated, disposable PostgreSQL container with no named volume,
  the full backend command exited `0`: `1506 passed, 4 warnings in 52.04s`.
  Two test-only baseline files were minimally corrected to assert relative
  intake counts, distinguish the two later PRT-6 preview tables, and supply the
  no-existing-job `scalar` stub. Frontend verification passed with `25` files /
  `263` tests; production build passed with the existing chunk-size warning.
- Exact fixture command:
  `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python
  .agent/harness/scripts/run-p0.py fixture --scope task --task D7-T2`.
  It produced immutable run `20260731T023152459255Z-45112b99` and exited `1`
  because its task receipt is intentionally `blocked`: the six live-only phase
  selectors were stopped before execution in fixture mode. The seven offline
  selectors passed, with `0 failed`, `0 not_run`, fresh receipt,
  `formal_p0_verdict_allowed=false`, sealed routing/proof artifacts and
  `external_calls=0`. Literal `generate-receipt.py --check-run
  20260731T023152459255Z-45112b99` reported `receipt_valid=1`.
- The disposable PostgreSQL container and network were removed after evidence
  capture. `git diff --check`, mirror/binding checks and the full specified Ruff
  command passed. The old immutable failure run
  `20260731T010824036074Z-4ede5669` remains untouched.
- Independent final review returned `accept with concerns`, `0 blockers`.
  Its source-only staging concern is resolved by the explicit list above; the
  remaining compatibility-cleanup suggestion is non-blocking and deferred.
  No Provider, upload, browser, formal live Harness, production promotion,
  production default/fallback, cache Owner, main merge, push, artifact cleanup
  or `PRT-8` action occurred.

## PRT-8 Parent Amendment: One Isolated Canary, No Promotion

### Selection Record

- Selected lane: `Heavy`.
- Selected plan:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`,
  `PRT-8` only.
- Selection evidence: user authorized an amendment-only continuation after the
  read-only preflight. Feature implementation HEAD is
  `12c88b5e509451030f373fad8dc748e0b01418e3`; live `main` is
  `31f7bf319129a056683b43833317a743faef46c8`; merge-base is
  `50d118523181fe2edc9c240afe070faed22a7def`; feature is ahead `14` / behind
  `10`. Index and unmerged entries are empty, all `188` dirty entries are
  pre-existing `pyc`、`__pycache__` or immutable Harness-run artifacts, and
  non-artifact dirty count is `0`.
- Validation action: `amend`. The offline evidence is sufficient to define one
  isolated canary, but not production promotion. The single `513.44s` historical
  run and any single successor canary remain raw samples, never P50/P95.
- Writer ownership and order: the parent is the only amendment writer for this
  plan. One independent read-only reviewer must accept the committed amendment
  with `0` blockers. No writer may execute the live steps while this amendment
  is being written or reviewed.
- Next verification: `git diff --check`,
  `.agent/harness/scripts/check-contracts.py`, exact diff/staging review,
  amendment commit, then independent review. Stop and request a new explicit
  user authorization before Step 1 below.

### Decision Boundary

`PRT-8` is not a combined canary-and-promotion shortcut. It owns exactly one
isolated `production_uncertainty` browser upload against the frozen feature
implementation and a sanitized evidence/rollback record. It does not:

- change the repository or deployment default from `legacy_high_recall`;
- merge `main`、push、open a PR or deploy to a shared production runtime;
- run `full-p0`、formal live Harness、current-four or a second project;
- retry、re-upload、make a direct Provider call or approve/freeze/export;
- enable cross-project cache or claim its security gate passed;
- mark `legacy_high_recall` for removal or satisfy production promotion.

Production-default promotion remains blocked until a later parent decision has
all of the following fresh evidence:

1. live-main convergence for the project API/workbench paths changed after
   `50d1185`;
2. the design cohort with at least `20` independent project executions per
   source class and explicit cold/warm distributions;
3. current-four、partial-failure browser、cache and rollback evidence;
4. a bound storage/security Owner for same-tenant cross-project cache, or a new
   approved design that explicitly removes that P0 promotion requirement;
5. an affirmative Quality Owner verdict and independent promotion review.

The still-open cache status is therefore unchanged:

```text
cross_project_cache_status=blocked_missing_security_scope_owner
project_local_content_cache_allowed=true
```

### Owner, Old Path And Failure Contract

- `CandidateAdvisor` remains the only candidate、coverage and completeness
  semantic Owner.
- `build_automatic_result()` remains the only terminal persistence Executor.
- Project intake freezes `production_uncertainty` and
  `symbol-uncertainty-router/1` for the canary project.
- Provider、cache、frontend and Harness remain Advisor/evidence consumers; none
  may infer a promotion verdict.
- `legacy_high_recall` action is `preserve`: it remains the shared deployment
  default and real consumer for every non-canary new project. The isolated
  canary does not replace it, so no removal mark is created.
- Any source、code、model、prompt、schema、adapter、router、runtime、database or
  credential-presence mismatch stops before browser file selection.
- Any terminal success、localized partial result、Provider failure、timeout or
  budget exhaustion consumes the one-canary authorization and stops without
  retry. Systemic lineage/contract failure must remain fail-closed.

### Frozen Canary Identity

The live authorization, if later granted, is valid only for:

```text
implementation_head=12c88b5e509451030f373fad8dc748e0b01418e3
source_filename=JS26032501-1-03-036#上下座B#A1.pdf
source_sha256=58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec
recognition_mode=production_uncertainty
router_version=symbol-uncertainty-router/1
configured_model=qwen3-vl-plus
prompt_version=visual-symbol-prompt/4
response_schema=visual-symbol-review/2
adapter_version=qwen-openai-compatible/5
cache_identity_schema=visual-symbol-cache-identity/1
qwen_vl_sha256=f862fb012d919456299386b482f67672b4e18450fc3de597c4711c42f38f42ad
symbol_review_sha256=fe40293d48903f1578bb9241367a16d0849034818b4fba71d137238056297bd4
provider_runtime_sha256=1774815f29ca8302f7869697cafbc45c1cabc8f508b8a19c7ba4eb92cbff42f8
symbol_routing_sha256=9580aa60a5404d920ad6ec37f16e32d37558f3ede25c2e96249b3b2bdc7be866
candidate_advisor_sha256=18ae0e234fcd6db0934624290ba19c17c6271e2563d537bab782f3765a04e6b5
processing_pipeline_sha256=39a555d1b774e7400f0f4c8694fcf24e5525150a46ac774de20d954ad5d70048
config_sha256=fe577c3f38e7e5552784cb1b7d0f3a17cf7518a2bb13c4ffd32473a96a7b8748
```

`QI_SYMBOL_SOURCE_PDF` must point to the named file outside Git. Only its
basename、existence and SHA-256 may be reported; the private absolute path must
not enter logs、screenshots、the plan or Git. Credential values must never be
read into agent output; only boolean presence may be checked inside the isolated
containers.

### Isolated Runtime Contract

The canary uses only these new resources and ports:

```text
network=qi-prt8-canary
postgres_container=qi-prt8-canary-postgres
redis_container=qi-prt8-canary-redis
api_container=qi-prt8-canary-api
worker_container=qi-prt8-canary-worker
frontend_container=qi-prt8-canary-frontend
postgres_volume=qi_prt8_canary_postgres
storage_volume=qi_prt8_canary_storage
api_image=qi-prt8-canary-api:12c88b5
frontend_image=qi-prt8-canary-frontend:12c88b5
postgres_port=127.0.0.1:15432
api_port=127.0.0.1:18080
frontend_port=127.0.0.1:15173
```

If any named resource or port already exists, stop before creating or deleting
anything. The canary must not attach to the existing dev/QA/production database、
Redis、storage、API、worker or frontend. The two canary data volumes are preserved
after execution for audit; do not clean them as artifacts. Containers and the
network may be removed only after they are stopped and the sanitized evidence
has been captured and hashed. Preserve both images and both data volumes until
the later promotion decision.

### PRT-8: Execute The One Authorized Canary

**Files:**

- Modify after execution:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`
- Do not modify: production code、tests、schemas、Harness、frontend source、
  runtime config files or any existing immutable run.
- Temporary screenshot directory:
  `/tmp/qi-prt8-canary-evidence/`
- Docker writes only the ten named isolated resources above.

- [ ] **Step 1: Revalidate source, Git and resource identity without live calls**

Run from the feature worktree:

```bash
git merge-base --is-ancestor \
  12c88b5e509451030f373fad8dc748e0b01418e3 HEAD || exit 1
git diff --quiet \
  12c88b5e509451030f373fad8dc748e0b01418e3 -- \
  . ':(exclude)docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md' \
  || exit 1
test "$(basename -- "$QI_SYMBOL_SOURCE_PDF")" = \
  "JS26032501-1-03-036#上下座B#A1.pdf" || exit 1
test "$(sha256sum "$QI_SYMBOL_SOURCE_PDF" | cut -d ' ' -f 1)" = \
  "58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec" \
  || exit 1
test "$(git status --porcelain=v1 | awk '
function artifact(p) {
  return p ~ /(^|\/)__pycache__\// ||
    p ~ /\.pyc$/ ||
    p ~ /^\.agent\/harness\/runs\//
}
{ p=substr($0,4); if (!artifact(p)) count++ }
END { print count+0 }')" = "0" || exit 1
test "$(sha256sum backend/app/providers/qwen_vl.py | cut -d ' ' -f 1)" = \
  "f862fb012d919456299386b482f67672b4e18450fc3de597c4711c42f38f42ad" \
  || exit 1
test "$(sha256sum backend/app/candidates/symbol_review.py | cut -d ' ' -f 1)" = \
  "fe40293d48903f1578bb9241367a16d0849034818b4fba71d137238056297bd4" \
  || exit 1
test "$(sha256sum backend/app/providers/runtime.py | cut -d ' ' -f 1)" = \
  "1774815f29ca8302f7869697cafbc45c1cabc8f508b8a19c7ba4eb92cbff42f8" \
  || exit 1
test "$(sha256sum backend/app/candidates/symbol_routing.py | cut -d ' ' -f 1)" = \
  "9580aa60a5404d920ad6ec37f16e32d37558f3ede25c2e96249b3b2bdc7be866" \
  || exit 1
test "$(sha256sum backend/app/candidates/advisor.py | cut -d ' ' -f 1)" = \
  "18ae0e234fcd6db0934624290ba19c17c6271e2563d537bab782f3765a04e6b5" \
  || exit 1
test "$(sha256sum backend/app/processing/pipeline.py | cut -d ' ' -f 1)" = \
  "39a555d1b774e7400f0f4c8694fcf24e5525150a46ac774de20d954ad5d70048" \
  || exit 1
test "$(sha256sum backend/app/config.py | cut -d ' ' -f 1)" = \
  "fe577c3f38e7e5552784cb1b7d0f3a17cf7518a2bb13c4ffd32473a96a7b8748" \
  || exit 1
```

Then inspect live `main` only for commits after
`31f7bf319129a056683b43833317a743faef46c8`. A new delta does not change the
frozen canary runtime, but any symbol-routing contract、Provider or sealed-source
change requires a parent amendment before continuing. Do not merge `main`.

- [ ] **Step 2: Start the isolated runtime with zero Provider calls**

Run the exact preflight and startup sequence below. It refuses to reuse or
delete an existing name、volume or listening port:

```bash
for prt8_container in \
  qi-prt8-canary-postgres \
  qi-prt8-canary-redis \
  qi-prt8-canary-api \
  qi-prt8-canary-worker \
  qi-prt8-canary-frontend
do
  if docker container inspect "$prt8_container" >/dev/null 2>&1; then
    exit 1
  fi
done
if docker network inspect qi-prt8-canary >/dev/null 2>&1; then
  exit 1
fi
for prt8_volume in qi_prt8_canary_postgres qi_prt8_canary_storage
do
  if docker volume inspect "$prt8_volume" >/dev/null 2>&1; then
    exit 1
  fi
done
for prt8_image in \
  qi-prt8-canary-api:12c88b5 \
  qi-prt8-canary-frontend:12c88b5
do
  if docker image inspect "$prt8_image" >/dev/null 2>&1; then
    exit 1
  fi
done
if ss -ltn | rg -q ':(15432|18080|15173)\b'; then
  exit 1
fi
test -f .env || exit 1

docker build -t qi-prt8-canary-api:12c88b5 backend
docker build -t qi-prt8-canary-frontend:12c88b5 frontend
docker network create qi-prt8-canary
docker volume create qi_prt8_canary_postgres
docker volume create qi_prt8_canary_storage
docker run --detach \
  --name qi-prt8-canary-postgres \
  --network qi-prt8-canary \
  --env POSTGRES_DB=qi \
  --env POSTGRES_USER=qi \
  --env POSTGRES_PASSWORD=qi \
  --publish 127.0.0.1:15432:5432 \
  --volume qi_prt8_canary_postgres:/var/lib/postgresql/data \
  postgres:17-alpine
docker run --detach \
  --name qi-prt8-canary-redis \
  --network qi-prt8-canary \
  redis:7-alpine \
  redis-server --appendonly no
for prt8_attempt in $(seq 1 30)
do
  if docker exec qi-prt8-canary-postgres pg_isready -U qi -d qi; then
    break
  fi
  if test "$prt8_attempt" = "30"; then
    exit 1
  fi
  sleep 2
done

cd backend
PYTHONDONTWRITEBYTECODE=1 \
QI_DATABASE_URL=postgresql+psycopg://qi:qi@127.0.0.1:15432/qi \
micromamba run -n qi-p0 alembic -c alembic.ini upgrade head
cd ..

docker run --detach \
  --name qi-prt8-canary-api \
  --network qi-prt8-canary \
  --network-alias api \
  --env-file .env \
  --env QI_DATABASE_URL=postgresql+psycopg://qi:qi@qi-prt8-canary-postgres:5432/qi \
  --env QI_REDIS_URL=redis://qi-prt8-canary-redis:6379/0 \
  --env QI_STORAGE_ROOT=/data \
  --env QI_SYMBOL_RECOGNITION_MODE=production_uncertainty \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --publish 127.0.0.1:18080:8000 \
  --volume qi_prt8_canary_storage:/data \
  qi-prt8-canary-api:12c88b5
docker run --detach \
  --name qi-prt8-canary-worker \
  --network qi-prt8-canary \
  --env-file .env \
  --env QI_DATABASE_URL=postgresql+psycopg://qi:qi@qi-prt8-canary-postgres:5432/qi \
  --env QI_REDIS_URL=redis://qi-prt8-canary-redis:6379/0 \
  --env QI_STORAGE_ROOT=/data \
  --env QI_SYMBOL_RECOGNITION_MODE=production_uncertainty \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --volume qi_prt8_canary_storage:/data \
  qi-prt8-canary-api:12c88b5 \
  celery -A app.celery_app:celery_app worker --loglevel=info --concurrency=1
docker run --detach \
  --name qi-prt8-canary-frontend \
  --network qi-prt8-canary \
  --env QI_API_PROXY_TARGET=http://api:8000 \
  --publish 127.0.0.1:15173:3000 \
  qi-prt8-canary-frontend:12c88b5

for prt8_attempt in $(seq 1 30)
do
  if curl --noproxy 127.0.0.1 -fsS \
    http://127.0.0.1:18080/api/v1/health >/dev/null; then
    break
  fi
  if test "$prt8_attempt" = "30"; then
    exit 1
  fi
  sleep 2
done
curl --noproxy 127.0.0.1 -fsS \
  http://127.0.0.1:15173/ >/dev/null
test "$(docker inspect -f '{{.State.Running}}' qi-prt8-canary-worker)" = \
  "true"
docker exec qi-prt8-canary-worker sh -c \
  'test -n "$QI_QWEN_API_KEY" && printf "qwen_api_key_present=true\n"'
docker exec qi-prt8-canary-api python -c \
  'from app.config import get_settings; s=get_settings(); print(f"mode={s.symbol_recognition_mode} model={s.qwen_model}")'
test "$(docker exec qi-prt8-canary-api sha256sum \
  /app/app/providers/qwen_vl.py | cut -d ' ' -f 1)" = \
  "f862fb012d919456299386b482f67672b4e18450fc3de597c4711c42f38f42ad"
test "$(docker exec qi-prt8-canary-worker sha256sum \
  /app/app/providers/qwen_vl.py | cut -d ' ' -f 1)" = \
  "f862fb012d919456299386b482f67672b4e18450fc3de597c4711c42f38f42ad"
test "$(docker exec qi-prt8-canary-api sha256sum \
  /app/app/candidates/symbol_review.py | cut -d ' ' -f 1)" = \
  "fe40293d48903f1578bb9241367a16d0849034818b4fba71d137238056297bd4"
test "$(docker exec qi-prt8-canary-worker sha256sum \
  /app/app/candidates/symbol_review.py | cut -d ' ' -f 1)" = \
  "fe40293d48903f1578bb9241367a16d0849034818b4fba71d137238056297bd4"
```

Expected: API health `ok`、worker `running`、frontend HTTP success, matching
host/API/worker source hashes, `mode=production_uncertainty`,
`model=qwen3-vl-plus` and `qwen_api_key_present=true`. Do not print `.env`、
`docker inspect` environment arrays or credential values. With no project
created, Provider construction/calls remain `0`.

- [ ] **Step 3: Consume exactly one browser canary**

Use Chrome MCP against `http://127.0.0.1:15173/`:

1. select `QI_SYMBOL_SOURCE_PDF` exactly once;
2. click submit exactly once;
3. record the returned project ID and confirm intake froze
   `production_uncertainty` / `symbol-uncertainty-router/1`;
4. capture the first `local_ready` or `vlm_enriching` preview before terminal;
5. wait only for `ready_for_review`、`partial_review_required` or a fail-closed
   project error;
6. capture the terminal/error state and stop interacting.

Budgets are hard:

```text
browser_file_selections=1
browser_submit_clicks=1
project_creations=1
direct_provider_calls=0
visual_primary_calls_per_page<=4
visual_primary_calls_per_project<=8
in_flight_visual_calls<=2
visual_wall_time_per_page<=45s
visual_wall_time_per_project<=90s
schema_retry<=1/project
```

Do not click retry、review mutations、Confirm、freeze、balloon or export. If the
project is non-terminal after the bounded worker budget has exhausted, capture
sanitized status/call evidence, stop the isolated worker and record a failed
canary. Never submit a second project.

- [ ] **Step 4: Record sanitized evidence and perform isolated rollback**

Record in this plan:

- exact project/task/preview/terminal result IDs that are safe opaque refs;
- frozen mode/router、source hash and runtime/code identities;
- admitted/local/escalated/deduped/cache/call/unresolved counts;
- reason-code and outcome distributions;
- ordered raw stage/provider durations with sample count;
- completeness、partial or fail-closed outcome;
- cache namespace/provenance validation result;
- screenshot paths plus SHA-256;
- browser/action counts、authorization consumed and external call count;
- Quality Owner verdict state.

Set `PRT8_PROJECT_ID` to the opaque project ID shown by the browser, validate it
as a UUID, then collect the database-owned counts without reading raw Provider
payloads:

```bash
test "$(printf '%s' "$PRT8_PROJECT_ID" | \
  rg -c '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')" = \
  "1" || exit 1
docker exec qi-prt8-canary-postgres \
  psql -U qi -d qi -v ON_ERROR_STOP=1 -P pager=off -c \
  "SELECT recognition_mode, recognition_router_version
   FROM projects
   WHERE id = '$PRT8_PROJECT_ID'::uuid"
docker exec qi-prt8-canary-postgres \
  psql -U qi -d qi -v ON_ERROR_STOP=1 -P pager=off -c \
  "SELECT disposition, count(*)
   FROM symbol_routing_decisions
   WHERE project_id = '$PRT8_PROJECT_ID'::uuid
   GROUP BY disposition
   ORDER BY disposition"
docker exec qi-prt8-canary-postgres \
  psql -U qi -d qi -v ON_ERROR_STOP=1 -P pager=off -c \
  "SELECT reason_code, count(*)
   FROM symbol_routing_decisions,
   LATERAL jsonb_array_elements_text(
     local_resolution_reason_codes ||
     escalation_reason_codes ||
     block_reason_codes
   ) AS reasons(reason_code)
   WHERE project_id = '$PRT8_PROJECT_ID'::uuid
   GROUP BY reason_code
   ORDER BY reason_code"
docker exec qi-prt8-canary-postgres \
  psql -U qi -d qi -v ON_ERROR_STOP=1 -P pager=off -c \
  "SELECT event_code, count(*)
   FROM symbol_escalation_attempt_events
   WHERE project_id = '$PRT8_PROJECT_ID'::uuid
   GROUP BY event_code
   ORDER BY event_code"
docker exec qi-prt8-canary-postgres \
  psql -U qi -d qi -v ON_ERROR_STOP=1 -P pager=off -c \
  "SELECT outcome_code, count(*)
   FROM symbol_escalation_outcomes
   WHERE project_id = '$PRT8_PROJECT_ID'::uuid
   GROUP BY outcome_code
   ORDER BY outcome_code"
docker exec qi-prt8-canary-postgres \
  psql -U qi -d qi -v ON_ERROR_STOP=1 -P pager=off -c \
  "SELECT completeness, recognition_mode, router_version,
          jsonb_array_length(provider_call_ids) AS call_count,
          recognition_summary, recognition_evidence_ref
   FROM automatic_results
   WHERE project_id = '$PRT8_PROJECT_ID'::uuid"
docker exec qi-prt8-canary-postgres \
  psql -U qi -d qi -v ON_ERROR_STOP=1 -P pager=off -c \
  "SELECT revision, semantic_snapshot->>'stage' AS stage,
          semantic_snapshot->'counts' AS counts
   FROM recognition_preview_revisions
   WHERE project_id = '$PRT8_PROJECT_ID'::uuid
   ORDER BY revision"
```

Read Provider duration records only through their existing redacted
`ProviderCallRecord` allowlist. Report `request_id`、`model`、prompt/schema
versions、`duration_ms`、`retry_count` and safe refs; do not open the referenced
response payloads.

Do not store raw Provider response、crop/image bytes、credential、private path or
unsanitized logs. One canary produces one raw latency sample only. Report
`p50_eligible=false` and `p95_eligible=false`.

Stop and remove only the five canary application/runtime containers and
`qi-prt8-canary` network after evidence capture. Preserve
`qi_prt8_canary_postgres`、`qi_prt8_canary_storage` and both tagged images.
Verify the repository default remains `legacy_high_recall` and the existing
non-canary runtime was not restarted or modified. This isolated stop is not a
deployment rollback drill and must not be reported as one.

```bash
docker stop \
  qi-prt8-canary-frontend \
  qi-prt8-canary-worker \
  qi-prt8-canary-api \
  qi-prt8-canary-redis \
  qi-prt8-canary-postgres
docker rm \
  qi-prt8-canary-frontend \
  qi-prt8-canary-worker \
  qi-prt8-canary-api \
  qi-prt8-canary-redis \
  qi-prt8-canary-postgres
docker network rm qi-prt8-canary
docker volume inspect qi_prt8_canary_postgres >/dev/null
docker volume inspect qi_prt8_canary_storage >/dev/null
docker image inspect qi-prt8-canary-api:12c88b5 >/dev/null
docker image inspect qi-prt8-canary-frontend:12c88b5 >/dev/null
```

An explicitly authorized Quality Owner must inspect the sealed positives、
frozen negatives、unresolved sources、partial state and browser evidence and
return `accept` or `reject`. Until that human verdict is recorded, the PRT-8
result is `blocked_quality_owner_verdict` regardless of automated metrics.

- [ ] **Step 5: Commit evidence, review and stop before promotion**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
git diff --check
git add docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: record production routing canary"
```

The staged path list must contain exactly this plan. An independent read-only
reviewer must return `accept` with `0` blockers for source/runtime identity,
exact-one authorization consumption、budget arithmetic、privacy、Owner uniqueness、
project-local cache boundary、legacy preservation and honest no-percentile/no-
promotion reporting.

Stop after review. Do not change the production default、mark the old path、run a
second canary、start full-P0、merge `main` or push. The next action must be a new
user decision based on the actual canary and Quality Owner evidence.

### Amendment-Only Commit Contract

The currently authorized write is only this parent amendment. Before committing
it, run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
git diff --check
git add docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: authorize production routing canary"
```

The staged path list must contain exactly this plan. After the independent
amendment review accepts with `0` blockers, stop before PRT-8 Step 1 and ask for
one explicit live-canary authorization.
