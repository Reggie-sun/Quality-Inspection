# Provider Timeout Retry And Partial Failure Design

## Status

- Date: `2026-08-01`
- Status: `approved for GDT-10 planning; implementation pending`
- Selected lane: `Heavy`
- Parent plan: `docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`
- Scope owner: `backend/app/candidates/advisor.py::CandidateAdvisor`
- Runtime dependency: `docs/superpowers/specs/2026-08-01-compose-worktree-runtime-isolation-design.md` and `docs/superpowers/plans/2026-08-01-compose-worktree-runtime-isolation.md` must be merged into this branch and satisfy their completion contract before another paid live run

本文只定义 GDT-10 live Provider timeout 的 retry、failure disposition、runtime identity 和 evidence 边界。它不重开结构化 GD&T 的 domain schema、normalizer、API、frontend 或 export 设计，也不授权 production deployment。

## Problem

Fresh full-P0 run `20260801T071203401727Z-09cb5cc6` 在同一 worktree `/3` runtime 下完成 `18` 个 authenticated Qwen request/response/cache/call records 后，第 `19` 个 crop 在 `60.236s` 后由 `QwenVisionProvider.review_symbols()` 抛出 localized `timeout`。调用链进入 `CandidateAdvisor.review()` 的 `legacy_high_recall` sequential branch，timeout 被提升为 document-level `CandidateAdvisorFailure`，因此 run 以 `live_start_failed:RuntimeError` 结束，未生成 typed Case A/B、pause identity 或 receipt。

该失败不是 schema、credential、source、crop 或 Compose mid-run replacement 导致。失败发生后 `30s` 才有 main-worktree Compose recreate；后者是下一次 live 的独立 topology blocker，不是本次 timeout 的根因。

当前实现同时存在以下已验证约束：

- `backend/app/providers/runtime.py` 使用 `timeout=60.0`、`max_retries=0`；
- `MAX_VISUAL_PAGE_WALL_SECONDS=45.0`、`MAX_VISUAL_PROJECT_WALL_SECONDS=90.0`；
- `ProductionRetryCoordinator` 已拥有 `production_uncertainty` 的唯一 project-wide retry authorization；
- `production_uncertainty` 已把 localized `timeout|transport|schema` 转成单 ROI unresolved outcome，并保留 siblings 为 `partial_review_required`；
- symbol canary contract 已要求 `recognition_mode="production_uncertainty"`；
- project 在创建时冻结 recognition mode，不能在 processing 中途切换。

因此，直接在 SDK、Provider wrapper 或 legacy loop 增加 timeout retry 会建立第二个 retry Owner，并与现有 page wall budget 冲突。

## Goals

- GDT-10 的 fresh live run 在任何上传或付费调用前证明 API 与 worker 都使用 `production_uncertainty`。
- 一个 ROI timeout 只影响该 ROI；已成功的 siblings、technical requirements、Coverage 和 call evidence 必须保留。
- `ReviewService` 投影到 working copy 时必须保留 localized Provider failure entry 的 `ambiguous + requires_confirmation=true`；不得让 generic system-default path 静默转成 `non_inspection`。
- timeout attempt 没有 Provider `request_id` 时，只写安全 routing attempt/outcome，不伪造 call record、request/response artifact 或 request ID。
- 保持 `CandidateAdvisor`/`ProductionRetryCoordinator` 为 `production_uncertainty` 的唯一 retry 和 failure-disposition Owner；不重构 legacy sequential schema retry。
- 保持现有 Provider timeout、SDK retry、call/page/project budget 和 schema retry contract 不变。
- fresh live 只有在同一隔离 runtime、同一 literal run identity 和 current-four evidence 下才能继续 GDT-10 Step 4。

## Non-Goals

- 不把 `timeout=60.0` 改成更大或更小的猜测值。
- 不启用 OpenAI SDK automatic retry。
- 不给 timeout、transport 或 capability failure 增加 automatic retry。
- 不减少 visual batches、改变 crop packing、降低 current-four coverage 或跳过失败 ROI。
- 不增加 checkpoint/resume、第二个 Provider、shadow write 或新的 feature flag。
- 不把 `partial_review_required` 转成 formal live success；typed Case A/B 和现有非 GD&T acceptance 仍必须由实际 evidence 证明。
- 不在本 spec 中修改 Compose project name、ports、volumes 或 public main runtime；这些由独立 isolation plan 拥有。

## Decision

### Retry Matrix

| Failure family | Automatic retry | Owner | Required result |
| --- | ---: | --- | --- |
| `tool_arguments_schema_invalid` in `production_uncertainty` | 最多 `1` 次 | `ProductionRetryCoordinator` | 继续使用现有 budget authorization、retry evidence 和 `retry_count=1` |
| `timeout` | `0` 次 | `CandidateAdvisor` | 单 ROI `provider_timeout` + terminal `unresolved` + project `partial_review_required` |
| `transport` | `0` 次 | `CandidateAdvisor` | 单 ROI `provider_transport_failure` + terminal `unresolved` + project `partial_review_required` |
| `schema` after authorized retry | `0` 次 | `CandidateAdvisor` | 单 ROI `provider_schema_invalid` + terminal `unresolved` + project `partial_review_required` |
| capability unavailable | `0` 次 | capability preflight | fail before paid work；不得伪装为 partial success |
| routing identity、persistence 或 evidence corruption | `0` 次 | owning validator/repository | blocking/fatal；不得降级为 localized Provider failure |

Timeout 不自动重试的原因是：一次 `60s` timeout 已超过 `45s` page wall budget；且没有 Provider `request_id` 不能证明 server 未完成请求。立即重发既违反 latency/cost contract，也可能重复付费。后续若要改变 timeout 或为 timeout 建立独立 retry budget，必须另开 runtime-policy spec，不能由 GDT-10 顺手扩大。

### Runtime Identity

GDT-10 Step 4 的 isolated runtime 必须同时满足：

```text
API Settings.symbol_recognition_mode    = production_uncertainty
worker Settings.symbol_recognition_mode = production_uncertainty
router_version                          = symbol-uncertainty-router/1
model                                   = qwen3-vl-plus-2025-12-19
API/worker code identity                = current worktree /3 hashes
database revision                       = 0013
```

`run-p0.py` 必须在 registration、run-directory creation、source upload、project creation 和 Provider network call之前，通过 zero-paid container/database inspection 验证 API/worker exact hashes、mode/model/router 与 database revision。任一不符时立即退出，run directory count 不变。

该要求只约束 GDT-10 的隔离 verification runtime。`Settings.symbol_recognition_mode` 的 repository default 仍是 `legacy_high_recall`；本 spec 不把隔离 canary mode 提升为未经授权的 public production promotion。

### Failure And Evidence Semantics

对于没有 Provider response 的 timeout attempt：

1. 保留 canonical crop bytes、crop SHA、execution identity 和 routing decision identity；
2. append `EscalationAttemptEvent(event_code="provider_timeout", attempt_index=0, provider_request_id=None)`；
3. 写 terminal `EscalationOutcome(outcome_code="unresolved")`，对应 observation outcome 为 `provider_timeout`；
4. Coverage entry 保留 observation ID、source location、PDF coordinates，设置 `requires_confirmation=true`；
5. `AutomaticResult.completeness="partial_review_required"`，`ProjectStatus.phase="partial_review_required"`；`ReviewWorkingCopy` 不新增 duplicate completeness 字段；
6. working-copy coverage 保留该 entry 的 `failure_stage`、`disposition="ambiguous"`、`requires_confirmation=true`，并计入 `review_required_count`；
7. 不创建 Provider call record、request artifact、response artifact、cache winner 或虚构 request ID；
8. 已成功或 cache-resolved 的 sibling outcomes、candidates、technical requirements 和 call records 原样保留。

只有收到合法 Provider response metadata 的 attempt 才允许创建 canonical call record。错误消息、exception cause、URL、local path、token 和 credential 不进入 evidence 或 user-visible payload。

### Live Acceptance Boundary

`partial_review_required` 说明 pipeline 没有因为一个 localized timeout 丢失整个 document，不等于 GDT-10 Step 4 已通过。

Step 4 仍要求 fresh current-four run 同时证明：

- typed Case A/B；
- 所有既有 non-GD&T symbol results；
- every required observation 有 exact-once Coverage；
- authenticated Provider/crop/model/prompt/schema identity 完整；
- `execution_state=visual_qa_pending:first-pdf-balloons`。

如果 timeout 命中 Case A/B 或导致上述 acceptance 缺失，本次 run 保持 blocked。不得在同一 run 中手工补写 Provider evidence，也不得把旧 run 的成功 crop/call record 拼入 current run。

## Ownership And Old Path

### Single Owners

- Provider failure localization: `QwenVisionProvider`，只把 SDK/network exception 分类为 `timeout|transport|schema`。
- Retry authorization and localized disposition: `CandidateAdvisor` + `ProductionRetryCoordinator`。
- Routing evidence persistence: `RoutingEvidenceRepository`。
- Working-copy failure projection: `ReviewService` only preserves the Owner-committed localized failure/disposition；它不重新分类 Provider failure。
- GD&T semantic candidate: `GeometricToleranceNormalizer`，本 spec 不改变。
- GDT-10 live preflight: repository Harness `run-p0.py`。
- Compose topology isolation: separate Compose isolation design/plan。

### Old Path Action

GDT-10 不再允许“使用 repository default 创建 live project，然后等到 paid processing 或 post-run canary 才发现 mode 不符”的路径。

`legacy_high_recall` 本身不是本 spec 的删除对象；它仍服务未迁移 consumer。对 GDT-10 唯一需要 retire 的是未验证 recognition identity 的 live activation path。retirement proof 是 zero-paid preflight test：legacy API 或 worker mode 必须在 run/registration/provider work 之前被拒绝。

`ReviewService._review_coverage()` 的 generic `candidate_id=None -> non_inspection` system-default path 只适用于 owner-confirmed no-detection/default cases。对 allowlisted `provider_timeout|provider_transport_failure|provider_schema_invalid`，旧行为必须被替换为 failure-stage preservation；不得把 unresolved Provider ROI 静默消解。

## Unchanged Contracts

- Provider 仍不是业务 disposition Owner。
- `GeometricToleranceNormalizer` 仍是唯一 GD&T semantic Owner。
- `timeout=60.0`、OpenAI `max_retries=0`、page/project/call budget 常量不变。
- `production_uncertainty` schema invalid 的最多一次 Advisor-authorized retry 不变，并与任何 future production retry 共享唯一 coordinator。仍有 consumer 的 legacy sequential schema retry 保持原样且不属于 GDT-10 isolated path；本 spec 不借机重构它。
- Coverage exact-once、blocking/fatal 不转 success、same-reviewed-result export 不变。
- current-four、literal run ID、no-synthetic、sealed receipt 和 headed QA 边界不变。
- public main runtime、production deployment 与 current P0 contract matrix 不变。

## Verification Contract

Implementation 必须按以下顺序验证：

1. Harness contract：API 或 worker 为 `legacy_high_recall`、任一 code hash 不匹配或 database revision 不是 exact `0013` 时，preflight fail closed，registration/run count/Provider stub calls 都保持 zero；两侧 exact identity 时通过。
2. Integration：一个 `TimeoutError` 或 `ConnectionError` 只调用失败 ROI 一次，生成对应 attempt + unresolved outcome，无 provider request ID/call record，siblings 和 technical requirements 保留，`AutomaticResult.completeness` 与 project phase 为 `partial_review_required`。
3. Review projection：localized Provider failure entry 在 working-copy coverage 中保持 `ambiguous + requires_confirmation=true + failure_stage`；普通 `visual_no_detection` 仍走现有 system default。
4. Retry invariant：production schema invalid 仍最多一次；timeout/transport 都是 zero retry；SDK `max_retries=0`；legacy retry behavior 不变。
5. Full offline backend + Harness contract suites。
6. Independent reviewer 检查 Owner、old-path retirement、privacy、budget 和 false-success boundary。
7. Compose isolation plan 完成且 runtime quiet/identity preflight 通过后，才允许一次 fresh `make verify-p0-live`。

## Rollback

如果 Harness mode preflight 或 localized timeout contract 引入回归：

- revert 对应 GDT-10 amendment commit，不 reset unrelated history；
- 恢复此前 schema-only retry 行为和 Harness checks；
- first verification 为 focused Harness contract test，其次 localized failure integration test 和 focused `test_review_working_copy.py` no-detection/failure-projection regression；
- rollback 后 GDT-10 Step 4 保持 blocked，不允许回到未验证 mode 的 paid live path。

## Acceptance Criteria

1. 文档明确选择 `production_uncertainty` 作为 GDT-10 isolated live identity，而不是修改 global default。
2. timeout/transport zero automatic retry，production schema invalid 最多一次且只有一个 production retry Owner；legacy behavior 不变。
3. `60s > 45s` budget conflict 被测试/文档锁定，不以扩大 wall budget规避。
4. timeout 无 response 时不伪造 request ID、call record、request/response artifact 或 cache record。
5. one-ROI timeout 保留所有 siblings，并形成 exact `partial_review_required` evidence。
6. working-copy coverage 不得把 localized failure 静默改成 `non_inspection`，且普通 no-detection default 不回归。
7. API/worker mode/model/router/hash 或 database `0013` 任一不符，都在任何 paid work 和 run creation 前 fail closed。
8. 上述明确命名的 Compose isolation spec/plan 未合入并完成时不得运行新的 live。
9. independent reviewer verdict 为 `accept` 后，才可进入 fresh GDT-10 Step 4。
