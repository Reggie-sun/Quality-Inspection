# Provider Failure Classification And Durable Evidence Design

## Status

- Date: `2026-08-02`
- Status: `independent review accepted; awaiting user approval; implementation not authorized`
- Selected lane: `Heavy`
- Parent plan: `docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`
- Sealed evidence: `.agent/harness/runs/20260801T153347947042Z-0fea7c81/`
- Evidence commit: `91e02b5`
- Current source commit: `f6bac94f348b91676da2d545c82bd7361cde3773`

本文只设计 visual-symbol Provider failure 的安全分类、脱敏 durable evidence、传播一致性和 project-blocking stop 后的 terminal evidence。它不创建 `GDT-10D`，不授权 implementation、Provider/live invocation、credential/runtime 变更、budget 扩张或 production promotion。

## Problem

GDT-10C 的唯一 full-live invocation `20260801T153347947042Z-0fea7c81` 已封存失败。当前 evidence account 是：`198` 个 escalated groups 中 `190` 个在 plan 阶段被拒绝并拥有 budget-exhausted terminal evidence；`8` 个被 admitted，只有最初两个进入并发窗口并写 crop，随后在取得可信 request ID 前快速失败；剩余六个从未提交。

当前代码不能从封存证据判断两个 fast failures 是 HTTP status rejection、transport failure、metadata failure 还是其它异常，原因是：

1. `QwenVisionProvider.review_symbols()` 只把 timeout 与 connection/OSError 转成 `LocalizedProviderFailure`；SDK HTTP status、metadata validation 和其它异常原样越过 Provider 边界。
2. `CandidateAdvisor.call_once()` 只识别已有 `failure_category`、built-in timeout/connection；其它异常被转换为 `CandidateAdvisorFailure(failure_category=None)`。
3. `_visual_review_result()` 捕获该异常时却用 fallback `provider_transport_failure` 写 attempt event 和 terminal outcome，然后仍原样传播 `failure_category=None`。
4. production collector 只把可信 `timeout|transport|schema` 放入 `localized_failure_stages`；无 category 的异常进入 `worker_failures`，阻止继续提交 queued jobs，并在为剩余六组写 terminal evidence 前抛出 document-level failure。

因此，现有持久化事实与传播事实互相矛盾；把所有 unknown 自动视为 transport 会错误地把 authentication、bad request、rate limit、server rejection、metadata corruption 或本地 defect 降级成 ROI-localized partial。

## Goals

- 对 SDK timeout、connection、HTTP status、response metadata、schema 和 unknown exception 形成安全、稳定、可测试的事实分类。
- Provider 只提交 factual classification；`CandidateAdvisor`/`ProductionRetryCoordinator` 继续唯一拥有 retry 和 `roi_localized|project_blocking` disposition。
- 一次 failure 的 persisted event、durable diagnostic、terminal outcome 和 propagated `CandidateAdvisorFailure` 必须来自同一个 immutable classification object。
- 未提交的 admitted groups 在 project-blocking stop 后必须得到“未调用 Provider”的 cancellation event 和 terminal outcome；不得伪装成 budget exhaustion、transport 或 successful partial。
- 保持 raw exception、response body、headers、URL、path、prompt、image、token 和 credential 不进入 DB、storage artifact、API/error message 或 logs。
- 任何无法分类、无法原子持久化或 evidence replay 冲突都 fail closed，不生成 `AutomaticResult`。

## Non-Goals

- 不改变 `timeout=60.0`、SDK `max_retries=0`、concurrency `2`、page/project/call/wall budget。
- 不给 timeout、transport、HTTP status、metadata 或 unknown failure 增加 automatic retry。
- 不改变 production schema-invalid 最多一次且仅由 `ProductionRetryCoordinator` 授权的 contract。
- 不修改 OCR、`review_candidate()` legacy behavior、GD&T schema/normalizer、ReviewService、frontend、export、Harness live policy 或 current-four acceptance。
- 不补写或重解释 GDT-10C sealed evidence；新 schema 只作用于 implementation 后的新 attempts。
- 不在本 spec 中批准下一次 live verification cycle。

## Evidence Audit

### Confirmed Control Flow

- Provider classification Owner: `backend/app/providers/qwen_vl.py::QwenVisionProvider.review_symbols()`。
- Provider-to-Advisor boundary: `backend/app/candidates/advisor.py::CandidateAdvisor._visual_review_result()::call_once()`。
- Evidence persistence seams: `CandidateAdvisor._append_attempt_event()`、`_record_terminal_outcome()` 与 `RoutingEvidenceRepository`。
- Production scheduler: `CandidateAdvisor.review()` 中 `ThreadPoolExecutor(max_workers=MAX_VISUAL_IN_FLIGHT)`；`MAX_VISUAL_IN_FLIGHT=2`。
- Document failure projection: `backend/app/processing/pipeline.py::InventoryPipeline.run()`。

### Confirmed Mismatches

以下旧路径都必须被替换，而不是继续依赖 generic transport fallback：

- Provider factory unknown exception：写 `provider_transport_failure`，传播 category `None`。
- `call_once()` unknown exception：写 `provider_transport_failure`，传播 category `None`。
- defensive `result is None`：写 `provider_transport_failure`，传播 category `None`。
- queued production jobs：首次 project-blocking worker failure 后停止提交，但未写 cancellation terminal evidence。

GDT-10C 的 tracked run 只能证明 run sealed `failed`、`failure_reason=live_start_failed:RuntimeError` 且没有 symbol report/AutomaticResult/pause/receipt；`190 + 2 + 6` 的 routing aggregate 已由 parent plan/bug-memory 和上一轮只读 review 封存。本设计不声称 tracked Harness JSON 自身包含 DB routing rows。

## Considered Approaches

### A. Typed Failure Facts + Atomic Versioned Routing Evidence

Provider adapter产生 typed、脱敏事实；Advisor 用 frozen policy mapping 决定 scope/retry；routing attempt v2 在同一事务写 diagnostic、event 和 terminal outcome；scheduler 为未提交 group 写明确 cancellation terminal。

优点：单一分类来源、DB 可查询、event/exception 可机械校验、privacy 和 replay 边界明确。代价：需要一个小型 Alembic migration，并触碰 Provider、Advisor、routing evidence 与 pipeline tests。

### B. Minimal Exception Catch Mapping

只在 `qwen_vl.py` catch `APIStatusError`/metadata error，并删除 unknown-to-transport fallback；继续使用现有 attempt rows。

优点：改动少。缺点：没有 durable status/metadata diagnostic；event 与传播一致性仍依赖分散字符串；六个未提交 group 仍没有 terminal evidence；不能满足本次 blocker。

### C. Harness-Only Redacted Diagnostic Artifact

在 Harness/log 或 object storage 单独写 failure summary，production DB 和 scheduler 不变。

优点：不迁移 DB。缺点：建立第二 evidence truth，只解决一次 live 调试，不解决 production collector、replay 或 exact-once terminal contract。

## Decision

选择 Approach A。它是唯一同时满足 safe classification、durable evidence、propagation consistency、terminal completeness 和 fail-closed privacy 的方案。

## Classification Contract

### Provider Facts

`backend/app/providers/base.py` 新增 frozen `ProviderFailureFact` 与 sanitized `ClassifiedProviderFailure`。Provider fact 只描述观察到的 failure，不决定业务 disposition：

```python
ProviderFailureCategory = Literal[
    "timeout",
    "transport",
    "schema",
    "authentication",
    "request_rejected",
    "rate_limited",
    "service_failure",
    "metadata_invalid",
    "unclassified",
]

ProviderFailureOrigin = Literal[
    "sdk_timeout",
    "sdk_connection",
    "sdk_http_status",
    "response_metadata",
    "response_schema",
    "provider_boundary",
]
```

Fact 只允许：`category`、`origin`、`http_status`、sanitized `provider_request_id` 和 `request_id_state`。它不包含 exception、message、body、headers、request URL 或 response content。`ProviderFailureFact.__post_init__()` 自身必须重新验证 category/origin/status matrix 和 request ID；不能只信任 adapter helper。

safe request ID Owner 也位于 `backend/app/providers/base.py`。只接受 `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` 且不含（case-insensitive）`authorization|api[_-]?key|secret|credential|bearer|token|password|passwd|cookie|session` 的值。unsafe candidate 立即丢弃，只保留 `request_id_state="rejected"`；原值不得离开 stack-local sanitizer。`review_symbols()` 的成功与 schema response metadata validation也必须复用该 helper，防止同一 ID 在 error path被拒绝、却在 call record/cache path被接受。

timeout、connection、status、metadata 和 unknown exception 都必须在对应 `except` block 内只生成 safe fact，退出 `except` 后才抛 `ClassifiedProviderFailure`。因此 sanitized carrier 的 `__cause__` 与 `__context__` 都必须为 `None`；不能依赖 `raise ... from None`，因为它仍会把原 exception 保存在 `__context__`。

### Schema Failure Carrier And Retry Seam

已有 `VisualSymbolProviderError` 继续作为 sanitized schema failure carrier，但必须新增同一个 validated `fact: ProviderFailureFact(category="schema", origin="response_schema", ...)`。它继续保留现有 safe `request_id`、allowlisted integer `usage`、exact `failure_stage` 与 allowlisted/hash-only schema `diagnostic`；这些字段是唯一 schema retry 判断输入，不进入 generic Provider diagnostic 的 extension bag。

唯一 production schema retry 控制流为：

```text
QwenVisionProvider raises VisualSymbolProviderError(fact=schema fact)
→ CandidateAdvisor.call_once returns that typed carrier without eligibility filtering
→ ProductionRetryCoordinator.authorize_schema_retry(carrier, identity, duration)
   alone checks typed fact, exact failure_stage, identity, wall/call/page/project budget
→ if authorized: atomically persist sanitized schema attempt + retry_scheduled, then call once
→ if not authorized or second schema failure: derive Advisor classification from carrier.fact
→ atomically persist terminal provider_schema_invalid + outcome
→ propagate CandidateAdvisorFailure with the same classification/event SHA
```

首次 schema failure 获得唯一 retry 时，其 Provider diagnostic 使用 `retry_decision="authorized_schema_retry"` 且不是 terminal。最终 schema failure、timeout、transport 与所有 project-blocking failures 使用 `retry_decision="not_authorized"`。retry decision 不属于 `ProviderFailureFact` 或 frozen Advisor classification；它只能由 `ProductionRetryCoordinator.authorize_schema_retry()` 提交给 evidence writer。production `_visual_review_result()` 不再拥有 `allow_schema_retry` predicate，也不再在调用 coordinator前检查 `failure_stage`；legacy/shadow 无 routing evidence 的 retry behavior保持现有路径，不提升为 production Owner。

### Exact Status Matrix

| Observed failure | `category` | Advisor stage | Scope | Pipeline cause | Automatic retry |
| --- | --- | --- | --- | --- | ---: |
| `APITimeoutError` / `TimeoutError` | `timeout` | `provider_timeout` | `roi_localized` | existing partial path | `0` |
| HTTP `408` | `timeout` | `provider_timeout` | `roi_localized` | existing partial path | `0` |
| `APIConnectionError` / `ConnectionError` / `OSError` | `transport` | `provider_transport_failure` | `roi_localized` | existing partial path | `0` |
| existing valid-metadata schema failure after authorized retry | `schema` | `provider_schema_invalid` | `roi_localized` | existing partial path | only existing coordinator decision |
| HTTP `401|403` | `authentication` | `provider_authentication_failed` | `project_blocking` | `invalid_configuration` | `0` |
| HTTP `429` | `rate_limited` | `provider_rate_limited` | `project_blocking` | `transient_provider_failure` | `0` |
| HTTP `500..599` | `service_failure` | `provider_service_failure` | `project_blocking` | `transient_provider_failure` | `0` |
| other HTTP `400..499` | `request_rejected` | `provider_request_rejected` | `project_blocking` | `processing_defect` | `0` |
| completion/request ID/usage metadata invalid | `metadata_invalid` | `provider_metadata_invalid` | `project_blocking` | `processing_defect` | `0` |
| any other exception at Provider boundary | `unclassified` | `provider_unclassified_failure` | `project_blocking` | `processing_defect` | `0` |

`429`/`5xx` 虽然可被 operator 视为 transient，但不得自动尝试剩余 groups：共享 Provider 状态很可能影响同一批次，继续提交会扩大 cost/budget。`retryable` user-facing projection 与 automatic retry 是不同 decision dimensions；本设计只复用现有 `transient_provider_failure` projection，不授权自动重试或 live rerun。

### Advisor Disposition Owner

`CandidateAdvisor` 用单一 frozen mapping 将 `ProviderFailureFact` 转成 `AdvisorFailureClassification`：

```python
@dataclass(frozen=True)
class AdvisorFailureClassification:
    fact: ProviderFailureFact
    failure_stage: str
    scope: Literal["roi_localized", "project_blocking"]
    pipeline_cause_category: Literal[
        "invalid_configuration",
        "processing_defect",
        "transient_provider_failure",
    ] | None
```

classification 的 category/origin/status/request-ID properties 全部只代理 immutable `fact`。`AdvisorFailureClassification.__post_init__()` 必须重新计算并验证 `fact.category -> stage/scope/cause` frozen mapping；不允许 test stub 或 future caller 手工构造矛盾组合。

`CandidateAdvisorFailure` 可以传播该 classification 和 persisted event SHA，但不能携带原异常。constructor 必须再次要求 classification/event SHA 成对且 SHA valid；production persistence enabled 时，缺少 valid event SHA 的 Provider failure 不得被 collector 视为 localized。

`pipeline_cause_category` 只有 `project_blocking` classification 才必须非空；`roi_localized` classification 必须为 `None`，因为它只进入 partial-result 路径而不产生 document-level ErrorRecord。若 localized classification 意外越过 collector 到达 pipeline，视为 invariant violation 并 fail closed 为 `processing_defect`，不得借此改变 retry contract。

Provider factory exception、Provider protocol 未按 contract 传播 typed carrier、以及 defensive `result is None` 都是 Advisor-local boundary/invariant failures，不得由 Advisor伪造 `ProviderFailureFact`。它们分别使用 repository-owned fixed stage `provider_factory_failed|provider_contract_failure|advisor_result_missing`、`scope="project_blocking"`、`pipeline_cause_category="processing_defect"` 和 exact `visual-symbol-advisor-boundary-failure/1` diagnostic；factory/protocol exception也必须在 catch 内只选择 safe classification、退出 catch 后才持久化/抛 sanitized `CandidateAdvisorFailure`，其 cause/context 均为空。这样可以退出旧 generic transport fallback，又不把 Advisor defect冒充成 Provider fact。

## Durable Diagnostic Evidence

### Attempt Event Version 2

新 Alembic revision `0014_symbol_provider_failure_diagnostics` 为 `symbol_escalation_attempt_events` 增加：

- `schema_version VARCHAR(64) NOT NULL DEFAULT 'symbol-escalation-attempt/1'`；constant server default 在不执行 row `UPDATE` 的前提下为历史 rows 提供 v1，并允许 migration-first compatibility window 内的旧 writer 继续写 v1；
- `diagnostic JSONB NULL`；
- `diagnostic_sha256 VARCHAR(64) NULL`。

`symbol_escalation_attempt_events` 已由 `prevent_symbol_escalation_attempt_events_update_delete` trigger 封为 immutable；`0014` 禁止用 `UPDATE` backfill，也禁止 disable trigger。新 writers 必须显式使用 `symbol-escalation-attempt/2`；server default 只服务 v1 compatibility，不得替代新 writer 显式版本。旧 event/outcome rows、hashes 和 sealed runs 不重写。DB check 与 application validator共同要求：v1 row 的 diagnostic/hash 均为空；v2 row 的 diagnostic/hash 均非空且 hash 为 64 lowercase hex。diagnostic hash 进入 v2 event canonical hash。

v1 server default 是有期限的 migration-first compatibility bridge，不是 durable alternate writer。production promotion在本 plan 外仍 blocked；未来只有在所有 attempt writers已部署 v2、runtime identity证明无旧 writer、并经过 observation window确认没有新 v1 row后，才可由单独批准的 `0015_drop_symbol_attempt_v1_default` 删除 default。未完成该 retirement gate不得 promotion；本 plan 不提前创建或执行 `0015`。

Provider failure diagnostic exact shape：

```json
{
  "schema_version": "visual-symbol-provider-failure/1",
  "failure_category": "rate_limited",
  "failure_stage": "provider_rate_limited",
  "scope": "project_blocking",
  "origin": "sdk_http_status",
  "http_status": 429,
  "request_id_state": "absent",
  "pipeline_cause_category": "transient_provider_failure",
  "retry_decision": "not_authorized"
}
```

允许 `http_status=null`，且只有 `sdk_http_status` 允许 `400..599`；`retry_decision` 只允许 `not_authorized|authorized_schema_retry`，后者只允许 schema first attempt 与相邻 `retry_scheduled` event。只有通过 Provider-base fact invariant 的值才进入 event 的 `provider_request_id`。error response request ID 只用于 correlation，不创建 Provider call record、request/response artifact 或 cache entry。

Advisor-local boundary failure diagnostic exact shape：

```json
{
  "schema_version": "visual-symbol-advisor-boundary-failure/1",
  "failure_stage": "provider_contract_failure",
  "scope": "project_blocking",
  "pipeline_cause_category": "processing_defect",
  "provider_work_started": true
}
```

`provider_factory_failed` 必须 `provider_work_started=false`；`provider_contract_failure|advisor_result_missing` 必须为 `true`。这些 failure 不携带 Provider category、HTTP status 或 request ID。

Scheduler stop diagnostic exact shape：

```json
{
  "schema_version": "visual-symbol-scheduler-stop/1",
  "stop_reason": "project_blocking_provider_failure",
  "blocking_event_sha256": "<64 lowercase hex>",
  "provider_work_started": false
}
```

`stop_reason` 只允许 `project_blocking_provider_failure|project_blocking_advisor_boundary_failure`。前者只允许 `AdvisorFailureClassification`，后者只允许 `AdvisorBoundaryFailureClassification`；两者都引用对应 blocking attempt event SHA。queued group自身的 `provider_work_started=false` 与 generic `not_started_after_project_failure/cancelled_after_project_failure` 语义不变，但 durable diagnostic不会把 Advisor-local defect冒充成 Provider failure。

禁止保存 raw exception 的 text、repr、class、cause/context、SDK body/code/param、headers、URL、local path、prompt、crop bytes、usage payload、token 或 credential。也禁止对 raw secret-bearing detail 做 hash 后持久化；只 hash canonical sanitized diagnostic。

### Atomic Failure Write

`RoutingEvidenceRepository.record_failure_terminal()` 在一个 DB transaction 中完成：

1. 验证 group decision hash 与 exact observation set；
2. append/replay v2 attempt event + diagnostic；
3. 写唯一 terminal outcome；
4. 返回 persisted `event_sha256`。

`RoutingEvidenceRepository.record_schema_retry()` 在另一个单 transaction 中 append/replay同一 attempt index 的 `provider_schema_invalid` v2 diagnostic（`retry_decision="authorized_schema_retry"`）和带 exact `visual-symbol-retry-control/1` diagnostic 的 `retry_scheduled` event；retry-control diagnostic 只包含 `retry_reason="schema_invalid"`、`authorization_owner="production_retry_coordinator"` 和前一 failure event SHA。generic `append_attempt()` 与 `record_failure_terminal()` 必须拒绝 authorized-schema-retry diagnostic 和 `retry_scheduled` event；只有 private pair insert path可写这两种 events，并在落库前验证完整 pair、相同 attempt/group/decision/request ID、canonical adjacency和 cross-reference SHA。只有 pair transaction commit 成功后才允许发起第二次 Provider call。它不写 terminal outcome。若 persistence 失败，不执行 retry，rollback整个 pair并转成 routing-evidence blocking failure。

`CandidateAdvisor` 只有在 commit 成功后才抛带该 SHA 的 `CandidateAdvisorFailure`。若 persistence 失败，rollback 并改为 `failure_origin="routing_evidence"` 的 blocking failure；不得传播一个看似可局部化、但没有 durable terminal 的 Provider category。

已有 cache/success/budget paths 不为本任务重构；只把 Provider terminal failure 和 new scheduler cancellation 收敛到该 atomic method。

## Scheduler Terminal Semantics

### Localized Failure

只有 `timeout|transport|schema` 且 `scope="roi_localized"`、mapping 一致、event SHA 已持久化时，collector 才把 observation 放入 `localized_failure_stages`。它继续调度剩余 admitted groups，最终保留 siblings 并返回 `partial_review_required`。

### Project-Blocking Failure

`authentication|request_rejected|rate_limited|service_failure|metadata_invalid|unclassified` 和三个 Advisor-boundary classifications 都停止新的 Provider submission。并发窗口中已经 submitted 的 futures 必须 drain；其成功或失败 evidence 按实际结果落盘，completion order 不改变 deterministic first blocking failure（最小 job index）。scheduler必须按 classification type选择上述两个 exact stop reasons。

drain 后、抛 document failure 前，对每个 admitted-but-never-submitted group 按 stable job order写：

- attempt event `not_started_after_project_failure`，`attempt_index=0`，`provider_request_id=None`；
- scheduler stop diagnostic，引用 first blocking failure 的 `event_sha256`；
- terminal group outcome `cancelled`；
- per-observation outcome `cancelled_after_project_failure`。

这些 rows 明确表示 Provider work 从未开始。不得复用 `not_started_budget_exhausted`、`routing_budget_exhausted` 或 `cancelled_after_project_budget`，因为 GDT-10C 的六组通过了 plan budget；把 failure stop 写成 budget stop 会产生新的 false evidence。

只有当 first blocking Provider or Advisor-boundary event 已 durable commit 时才允许写 dependent cancellations。任何 cancellation batch 写入失败都转成 routing-evidence blocking failure；不生成 `AutomaticResult`。

### Result Boundary

- ROI-localized failures：继续现有 Coverage `ambiguous + requires_confirmation` 和 `partial_review_required`。
- project-blocking failures 与其 queued cancellations：保留 routing evidence，但整个 document `failed`，不生成 AutomaticResult/working copy/pause/symbol report/receipt。
- budget-denied groups：继续 `not_started_budget_exhausted + budget_exhausted`，不受本设计影响。

## Persisted/Propagated Consistency Invariants

对每个 Provider terminal failure，测试必须机械证明：

```text
persisted diagnostic.failure_category
== propagated CandidateAdvisorFailure.failure_category

persisted diagnostic.failure_stage
== persisted attempt.event_code
== propagated CandidateAdvisorFailure.failure_stage

persisted diagnostic.scope
== propagated CandidateAdvisorFailure.failure_scope

persisted attempt.event_sha256
== propagated CandidateAdvisorFailure.failure_event_sha256
== scheduler cancellation diagnostic.blocking_event_sha256 (when present)
```

任何不等、缺字段、unknown enum、diagnostic/hash mismatch 或 replay conflict 都是 `routing_evidence` corruption，不得 fallback 为 transport、partial 或 retryable success。

## Privacy And Security Boundaries

- classification 只检查 exception type、integer status code 和 SDK 已解析的 `request_id` property；不读取或持久化 body、message、headers map、URL 或其它 SDK error fields。
- safe request ID 在 Provider-base helper 和 `ProviderFailureFact` invariant 两层验证；`token|password|passwd|cookie|session` 等 negative cases必须拒绝。invalid value只留下 `request_id_state="rejected"`，原值不进入日志或 assertion message。
- sanitized Provider carriers 的 `__cause__` 与 `__context__` 必须均为 `None`；tests覆盖 timeout、connection、status、metadata、schema 和 unknown 全矩阵。
- persisted error messages 固定为 repository-owned literals。
- tests 用 private marker 同时检查 exception、DB JSONB、storage artifacts、ErrorRecord 和 returned payload；禁止只检查 `str(exc)`。
- diagnostic schema `extra="forbid"`/exact-key validation；没有 extension bag、raw metadata 或 arbitrary tags。

## Verification Contract

Implementation 必须按以下顺序执行：

1. Provider contract RED/GREEN：timeout、connection、HTTP `401/403/408/429/5xx/other 4xx`、metadata invalid、schema carrier、unknown；验证 exact category、safe request ID 和 cause/context/private marker 不泄漏。
2. Migration/repository RED/GREEN：active immutable trigger + legacy v1 rows 下 `0013 -> 0014` 无 UPDATE backfill、v1-only `0014 -> 0013`、v2-present downgrade veto、v1 replay、v2 diagnostic/hash exactness、atomic rollback、immutable first-writer conflict。
3. Advisor classification RED/GREEN：event、diagnostic、terminal 和 propagated fields exact equal；unknown 不再写 transport。
4. Scheduler RED/GREEN：concurrency `2` 下两个 in-flight actual outcomes + 六个 never-submitted cancellation terminals；Provider call count保持 `2`，没有 queued crop/request/call/cache artifacts。
5. Localized regression：timeout/transport zero retry、schema-only single retry、siblings/technical requirements/Coverage/partial result不变。
6. Pipeline projection：rate-limit/service failure 使用现有 transient cause；auth 使用 invalid configuration；request/metadata/unknown 使用 processing defect；任何 project-blocking failure 不产出 result layers。
7. `make test-backend`、Harness offline contracts、Ruff、`check-contracts.py`、`git diff --check`。
8. Independent reviewer检查 Owner、old-path replacement、evidence exact-once、migration rollback、privacy、retry/budget和 false-success boundary。

本 implementation verification 禁止 Provider/live、browser、`make verify-p0-live`、credential injection、runtime recreate 或 GDT-10 next cycle。

## Rollback

- Code rollback：revert 本 companion plan commits 的逆序集合，不 reset unrelated history。
- Database rollback：只允许在 isolated PostgreSQL 且不存在任何 v2 attempt row 时 downgrade `0014 -> 0013`；v1-only downgrade只删除无信息增量的兼容 columns，保留原 routing decisions/outcomes 和旧 event fields。
- Downgrade veto：只要存在 active v2 application，或数据库存在任一 `schema_version='symbol-escalation-attempt/2'`、非空 diagnostic/hash row，migration 必须在 drop columns 前 fail closed，且所有 rows/columns保持不变。不得通过删 v2 durable evidence 来完成 rollback。
- First verification after rollback：`backend/tests/integration/test_symbol_routing_evidence.py` 的 v1 replay/immutability focused gate；随后 localized failure integration 和 processing error projection。
- Rollback 后 GDT-10 Step 4 仍 blocked，不允许恢复 unknown-to-transport fallback，也不自动授权 live。

## Acceptance Criteria

1. Provider status/metadata/unknown failure 全部得到 exact safe category；没有 generic unknown-to-transport fallback。
2. Provider facts 与 Advisor disposition Owner 分离，`ProductionRetryCoordinator` 仍是唯一 production retry authority。
3. persisted event/diagnostic/outcome 与 propagated exception 可机械证明一致。
4. project-blocking stop 后 every admitted group 恰有一个 terminal outcome；never-submitted groups 明确为 cancellation，且 Provider call count不增加。
5. timeout/transport/schema localized partial behavior和所有 retry/budget constants不变。
6. raw exception/body/header/URL/path/prompt/token/credential 未进入任何 durable or returned surface。
7. project-blocking failure 不生成 AutomaticResult、working copy、pause、symbol report 或 receipt。
8. migration upgrade/downgrade、v1 history compatibility、atomic persistence和 independent reviewer verdict 均通过。
9. user 显式批准本设计后，才可进入 companion implementation plan；批准 implementation 仍不等于批准任何新 live cycle。
10. 所有 new writers 显式写 v2；v1 server default只作为 temporary bridge，future `0015` retirement gate完成前不得 production promotion。
