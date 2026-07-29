# Engineering Drawing Symbol Recognition Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 冻结已经完成并验证的 symbol-recognition 实现，把唯一未关闭问题收敛为 Qwen production response-contract blocker；在得到可重复的根因证据前，不再用 full-P0 充当诊断工具。

**Architecture:** 现有 `VisualObservation → CandidateAdvisor → local validator → Coverage Ledger` 单一 Owner 链保持不变。当前只允许一次已经由 parent plan 授权的 exact-crop direct diagnostic；它不创建 project、cache、`AutomaticResult` 或正式 run，也不授权修复。

**Tech Stack:** Python 3.11、PyMuPDF、JSON Schema、OpenAI-compatible Qwen API、pytest、P0 Harness

---

## Status And Authority

- Date: `2026-07-29`
- Selected lane: `Heavy`
- Status: `diagnostic complete; live Provider response contract blocked`
- Current parent plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- Current branch/worktree: `main` /
  `/home/reggie/vscode_folder/Quality_Inspection`
- Selection evidence: 用户明确点名本文件进行收敛；当前 runtime、tests、sealed
  evidence 和 Git history 证明 implementation 已完成，而剩余 blocker 只在
  production Provider response contract。
- Writer ownership and order: parent agent 是本文件唯一 writer；任何 explorer
  或 reviewer 保持只读。先提交本次计划收敛，再在后续明确执行回合消费已授权的
  single diagnostic。
- Validation action: `git diff --check`、placeholder scan、
  `python .agent/harness/scripts/check-contracts.py` 和 independent read-only
  review。
- Next verification: 提交本文件后首先确认 clean worktree 和 unchanged runtime；
  diagnostic 执行回合的第一项 Provider 前验证是下面 Step 3。
- This file owns only the bounded symbol-recognition convergence steps below. It
  does not become a second current plan and cannot authorize `D7-T3`、`SR-5`、
  frontend changes or `main` merge.
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

## Single Owner And Unchanged Contract

- `backend/app/providers/qwen_vl.py::QwenVisionProvider.review_symbols()` owns the
  production request and response-shape classification.
- `backend/app/candidates/symbol_review.py::parse_visual_symbol_json()` owns frozen
  local schema validation.
- `backend/app/candidates/advisor.py::CandidateAdvisor` owns automatic persistence
  and fail-closed result submission; the diagnostic must bypass that persistence
  path without creating a second business Owner.
- Preserve model `qwen3-vl-plus-2025-12-19`、adapter `/4`、prompt v4、response
  schema v1、`temperature=0`、SDK `max_retries=0`、timeout、crop bytes and prompt
  bytes.
- Do not relax schema、normalize new fields、change paging/call cap、switch model、
  add fallback/repair/shadow paths or infer a fix from one response.

## Execution Veto

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
