# Symbol Recognition Production Routing Design

## Status And Authority

- Date: `2026-07-29`
- Status: `proposed`
- Selected lane: `Heavy`
- Scope: 工程图符号识别的 production uncertainty routing、低延迟执行和渐进式审核体验
- Current parent plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- Current subordinate plan:
  `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`
- Execution authorization: 本文只定义 design contract，不修改、替代或 amend 现有
  plan，也不授权 implementation、Provider live call、browser upload、runtime
  config、Harness run 或 merge。

本文是当前 symbol-recognition 正确性实现之后的 production-routing design。它不重做
visual proposal、Provider schema 或 candidate projection，也不把一次成功 canary
外推为通用性能基线。后续只有在唯一 current plan 明确吸收本 design、锁定
allowed paths、task ordering、rollback 和验证命令后，才能进入 implementation。

若本文后续被 Quality Owner 批准并由唯一 current plan 激活，它只 supersede
`2026-07-27-engineering-drawing-symbol-recognition-design.md` 中以下旧 clauses：

- all admitted visual observations 默认进入 VLM；
- 任一 localized visual Provider failure 导致整份 PDF 不产生 AutomaticResult；
- visual capability 永不使用 feature flag 或 bounded rollback path。

旧 spec 的 proposal rule、symbol families、Provider schema、local projection、
sealed evaluation、Coverage Veto、Quality Owner manual gate 和 immutable historical
result contracts 均不被本文重定义。本文处于 `proposed` 时不发生 supersession。

## Selection Record

- Problem boundary: 把当前“所有通过 high-recall proposal gate 的 visual
  observations 都进入 VLM”收敛为“本地证据先确定性处理，只有可解释的不确定 ROI
  才进入 VLM”，并允许不相关的局部 Provider 失败以可审核 partial result 收口。
- Single final business Owner:
  `backend/app/candidates/advisor.py::CandidateAdvisor` 继续唯一提交 automatic
  candidate、coverage 和 result completeness；不得建立第二个 raw-result writer。
- Old path action: 当前 high-recall all-observations route 在
  `production_uncertainty` canary promotion 前继续 `preserve`，因为它仍是 canonical
  active production path。只有 canary promotion 时、rollback consumer 已被实际验证
  后才进入有 deadline 的 `mark`；在 replacement gate 通过前不删除，在新 production
  mode 中不得作为逐 ROI 自动 fallback。
- Unchanged contract: proposal admission、Provider schema validation、candidate
  projection、Coverage Veto、Quality Owner manual commands、review/freeze/balloon/export
  顺序、immutable historical results 均保持各自现有 Owner。
- First future verification: 对当前两页 sealed source 离线重放 routing decision，
  Provider construction/calls 必须为 `0`，并机械证明每个 admitted observation
  恰有一个 local-resolution 或 escalation disposition。

## Current Problem

### Verified Current Path

截至 `2026-07-29`，当前代码和已记录 canary 形成下列链路：

```text
native PDF text + vector geometry
  -> build_page_visual_observations()
  -> all retained VisualObservation records
  -> plan_visual_batches()
  -> every batch enters CandidateAdvisor._visual_review_result()
  -> Qwen review_symbols()
  -> local schema validation and projection
  -> one final CandidateSnapshot / AutomaticResult
```

具体事实：

- `backend/app/pdf/visual_observations.py::build_page_visual_observations()` 使用
  geometry 和 short-token rule table 负责 proposal admission。它回答“这个局部上下文
  是否值得进入 symbol-recognition coverage”，不回答“本地证据是否已经足以提交结果”。
- `backend/app/candidates/symbol_review.py::plan_visual_batches()` 对页面内全部
  `page.visual_observations` 排序、打包，并只检查 `16/page` 硬预算；没有第二层
  uncertainty decision。
- `backend/app/candidates/advisor.py::CandidateAdvisor.review()` 对
  `plan_visual_batches()` 返回的每个 batch 顺序调用
  `_visual_review_result()`，之后才执行 schema validation、local projection 和
  coverage write。
- OCR 路径已有 `RuntimeRecognition._eligible_regions()`：
  embedded-image region 只有在 native coverage 不足时才进入 OCR，并受
  `16/page` 上限约束。visual-symbol VLM 路径没有等价的“local evidence 已解决则跳过”
  router。

### Proposal Admission Is Not VLM Escalation

proposal admission 和 VLM escalation 是两个不同 decision dimensions：

| Dimension | Question | Required bias | Current Owner | Current gap |
| --- | --- | --- | --- | --- |
| Proposal admission | 这里是否存在可能影响 symbol coverage 的局部视觉上下文？ | high recall，宁可保留可疑 source | `build_page_visual_observations()` | 已存在，不应承担 cost decision |
| Local resolution | native text、OCR、geometry 和 parser 是否已得到无冲突、可审计的确定结果？ | deterministic，证据不足不猜 | 尚无独立 production contract | 缺失 |
| VLM escalation | 哪些 unresolved ROI 必须请求 VLM Advisor？ | uncertainty-only，理由可解释且预算有界 | 当前被 `plan_visual_batches()` 隐式替代 | 全部 retained observations 默认升级 |
| Final business write | 哪些 candidate/coverage/result completeness 可以提交？ | fail closed，保持单一 Owner | `CandidateAdvisor` | 现有 Provider failure 会丢失整个 PDF 结果 |

high-recall proposal gate 的成功标准是“不漏掉需复核的 source”。production
uncertainty router 的成功标准是“不把本地已解决 source 继续送到远程模型”。前者不能
直接充当后者。

### Why 205 Observations Became 29 VLM Calls

成功 canary 的两页分别产生 `80` 和 `125` 个 visual observations，共 `205` 个。
`plan_visual_batches()` 将它们稳定打包为 `13` 和 `16` 个 batches。当前 loop 对每个
batch 恰执行一次 primary VLM call，因此形成 `13 + 16 = 29` 次调用。

该 canary：

- project: `d61ec678-0133-4a22-ba55-b7dc58d26edf`
- task: `5ddd2b20-1ca0-4ec1-a017-9dc17c7ed831`
- AutomaticResult: `578ca69b-5d6a-43ab-8597-26646ba1f1fa`
- outcome: `ready_for_review`
- elapsed: `513.4402794169728s`
- schema-valid visual calls: `29/29`

这是一个 current-source observed sample，不是 P50/P95 baseline。它证明 response
schema repair 和 correctness path 可以成功，也证明当前默认路由会让用户等待约
8 分 33 秒。正确性 canary 通过不等于 production experience 达标。

## Goals

1. native PDF parsing、bounded OCR 和 deterministic geometry/parser 先完成可解释的
   local resolution。
2. local result 明确且无冲突时，不构造 Provider、不生成 VLM batch、不消耗 call
   budget。
3. 只有 conflict、unknown symbol、low-evidence、无法完成 local parse 或 grouping
   ambiguity 的局部 ROI 才进入 VLM。
4. proposal admission 与 escalation 形成两个独立、可测试、可审计的阶段。
5. 单个 ROI 的 Provider/schema/timeout failure 不丢弃其他已经确定的正式结果。
6. Quality Owner 在本地结果可用后尽早开始审核，VLM enrichments 以幂等增量补充。
7. 在不降低 sealed-manifest recall、frozen-negative precision、Coverage Veto 和
   Quality Owner gate 的前提下，达到明确的 latency 和 call-count acceptance target。

## Non-Goals

- 不新增 current design 之外的 symbol families，不扩展为完整 ISO/GB/ASME 语义库。
- 不为 scanned PDF 建立完整 visual-symbol support；现有 support-level contract
  不变。
- 不切换 Vision Provider、model 或 public candidate enum。
- 不以一个模型 confidence 数字代替 deterministic evidence 或 Quality Owner review。
- 不允许 frontend、Provider、cache、Harness 或 telemetry 成为业务语义 Owner。
- 不把 full page、完整 PDF 或无界 tiles 发送给 VLM。
- 不在本 design turn 修改 production、tests、frontend、runtime config、现有 plan、
  contract matrix、Harness 或旧 spec。
- 不在 replacement evidence 完成前删除现有 high-recall path。

## Target Architecture

```text
PDF bytes
  |
  +-> Native Inventory Owner ----------------------+
  |     text / vector / page facts                 |
  |                                                v
  +-> bounded OCR Signal Provider ----------> Evidence Bundle
                                                   |
                                                   v
                                      Proposal Admission Owner
                                      high-recall VisualObservation
                                                   |
                                                   v
                                      Deterministic Local Resolver
                                      resolved / unresolved / blocker
                                         |         |          |
                                  resolved|         |escalate  |systemic
                                         v         v          v
                                   Local Result   ROI Planner  hard fail
                                                   |
                                            content-hash cache
                                              | hit     | miss
                                              v         v
                                         local validate VLM Advisor
                                              \         /
                                               v       v
                                           CandidateAdvisor
                                      single candidate/coverage/result write
                                                   |
                                     complete / partial_review_required
                                                   |
                                      progressive Quality Owner workbench
                                                   |
                                  unresolved blockers veto freeze/export
```

### Stage Contract

| Stage | Unique Owner | Input | Output | Fallback / failure |
| --- | --- | --- | --- | --- |
| Native inventory | existing Page Inventory Owner | source bytes | native text、vector facts、page identity | malformed/source mismatch 为 systemic blocker |
| OCR eligibility | `RuntimeRecognition._eligible_regions()` | embedded-image regions + native coverage | bounded OCR observations | OCR unavailable 只影响 eligible image regions；记录 unresolved source |
| Proposal admission | `build_page_visual_observations()` | native line/span + canonical path items | high-recall `VisualObservation` | geometry canonicalization/reconstruction mismatch fail closed |
| Local resolution | proposed `backend/app/candidates/local_symbol_resolution.py::resolve_visual_observation()` | observation + associated native/OCR text + geometry context + current parser facts | `LocalResolution` | 无冲突证据才 resolved；其余返回 reason-coded unresolved |
| Escalation decision | proposed `backend/app/candidates/symbol_routing.py::route_visual_observation()` | `LocalResolution` records | `EscalationDecision` per observation | invalid/missing decision blocks before Provider construction |
| ROI planning | proposed `backend/app/candidates/symbol_routing.py::plan_symbol_escalation_batches()` | only escalated observations | deduped, merged, bounded `EscalationBatch` | budget overflow becomes partial unresolved coverage，不静默丢弃 |
| Cache lookup | proposed `backend/app/candidates/symbol_cache.py::VisualSymbolCache`，Signal Provider role | versioned content identity | schema-valid cached Advisor response + provenance | miss/invalid provenance 继续 Provider；不得猜测或修复 |
| Vision request | existing Qwen adapter | bounded local crop + allowlisted context | frozen schema suggestion | timeout/transport/schema failure only marks affected ROI unresolved |
| Local validation and final write | `CandidateAdvisor` | local resolutions + validated cache/VLM suggestions | immutable preview revisions，then one terminal AutomaticResult with completeness | systemic integrity failure blocks all；localized failures produce `partial_review_required` |
| Manual closure | existing Review aggregate / Quality Owner commands | result + unresolved coverage | explicit promote/ignore/correct evidence | unresolved blockers veto freeze、balloon 和 export |

新组件的 role boundary 固定如下：

- `resolve_visual_observation()` 是 Local Resolution Owner，只能提交
  `LocalResolution` evidence；不得选择 escalation、写 candidate/coverage/result
  或调用 Provider。
- `route_visual_observation()` 是 Escalation Decision Owner，只能提交一个
  pre-VLM `RoutingDecision`；不得读取 cache/Provider outcome、改写 local evidence
  或写 candidate/coverage/result。
- `plan_symbol_escalation_batches()` 是 ROI Scheduling Owner，只能对已经
  `escalate` 的 IDs 做 dedup、merge、order 和 budget；不得改变 routing disposition、
  丢弃 source、制造 `non_inspection` 或写 candidate/coverage/result。
- `VisualSymbolCache` 是 Signal Provider，只返回 versioned Advisor evidence 和
  provenance；不得修复语义、选择 disposition 或提交 final result。
- `CandidateAdvisor` 编排以上 outputs，并保持唯一 automatic candidate、coverage、
  preview-head 和 terminal AutomaticResult writer。

### Result Completeness

production routing 必须新增一个 additive、Owner-submitted completeness dimension：

```text
complete
partial_review_required
```

`partial_review_required` 不是 warning，也不是 formal success：

- `CandidateAdvisor` 先发布 immutable `RecognitionPreviewRevision`，local result 是
  revision 1，后续 cache/VLM enrichments 只能创建带 parent/version 的 immutable
  successor；一个 project 同时只有一个 canonical preview head；
- preview 只允许查看和定位，不创建 working copy，不接受 Review commands，也不
  成为 export/receipt evidence；
- 所有 escalation groups 到达 success、failure、budget 或 cancellation terminal
  后，`CandidateAdvisor` 从 canonical preview head 提交恰好一个 immutable
  `AutomaticResult`，其 completeness 为 `complete` 或
  `partial_review_required`；
- 已确定 candidates、references、non-inspection dispositions 和完整 lineage 可以形成
  immutable automatic result 并进入 workbench；
- 每个未解决 ROI 必须保留 bbox、source IDs、escalation reason、failure stage 和
  `requires_confirmation=true`；
- Quality Owner 可以审核不受影响的 items，并对 unresolved source 执行既有显式
  source commands；
- 只要 blocking unresolved ROI 未被 Quality Owner 明确收口，freeze、balloon
  confirm 和 export 仍被 Veto Gate 阻断；
- source reconstruction、coverage identity、schema ownership 或 cache provenance
  发生 systemic corruption 时不得创建 partial result。

这里的“不是 formal success”精确指：它不是 completeness、Quality Owner freeze、
balloon 或 export success。它仍是由 backend Owner 持久化的正式 immutable
`AutomaticResult`，不能被 warning、frontend state 或临时 preview 替代。

后续 implementation plan 必须先完成 stable contract amendment，再改变现有
`AutomaticResult=0 on any Provider failure` 行为。不得以 frontend-only state
模拟 partial result。

## Uncertainty Contract

### Routing Decision Shape

每个 admitted `VisualObservation` 必须恰有一个 immutable routing record：

```json
{
  "schema_version": "symbol-routing-decision/1",
  "router_version": "symbol-uncertainty-router/1",
  "visual_observation_id": "<stable id>",
  "input_sha256": "<canonical local evidence hash>",
  "disposition": "locally_resolved | escalate | block",
  "local_resolution_reason_codes": [],
  "escalation_reason_codes": [],
  "block_reason_codes": [],
  "local_resolution_ref": "<optional immutable ref>",
  "escalation_group_id": "<required only for escalate>",
  "requires_confirmation": true
}
```

三个 reason arrays 都使用稳定排序和去重。恰好一个 array 必须非空，并与
`disposition` 同名匹配；其余两个必须为空。router 不读取 project ID、absolute
path、page ordinal bias、wall clock、remaining call slots、Provider output 或
Quality Owner label 来改变决策。

### Pre-VLM Decision Reason Codes

`reason_codes` 只记录 pre-VLM decision evidence。三个 disposition 使用互不重叠的
allowlisted enums。

`locally_resolved` 只允许：

| Code | Testable condition |
| --- | --- |
| `native_symbol_explicit` | allowlisted symbol glyph、value 和 source lineage 均来自同一 native observation group |
| `deterministic_geometry_complete` | family-specific geometry predicate、bbox 和 negative controls 全部通过且没有冲突 |
| `local_projection_complete` | typed/coarse/composite parser 或 family-specific deterministic validator 得到完整、唯一 projection，required values 均来自同一 local evidence group |

一个 locally resolved record 可以包含多个上述 reasons，但至少包含一个
family-specific geometry/text reason 和 `local_projection_complete`；只有 glyph
存在不能单独提交业务结果。

`escalate` 只允许：

| Code | Testable condition | Why VLM may help |
| --- | --- | --- |
| `local_evidence_conflict` | native/OCR text、geometry 或 parser 给出至少两个互斥结论 | 需要局部视觉上下文解除冲突 |
| `local_parse_incomplete` | symbol family 可定位，但 required value/frame/group 无法由同一 local source 完成 | 模型可提出受约束的 component association |
| `unknown_symbol_pattern` | geometry 不匹配任何已批准 deterministic family，但仍通过 proposal gate | 模型只能在现有九类 allowlist 内建议；未知类仍保持 unresolved |
| `ambiguous_component_grouping` | 同一局部有多个 symbol/value，存在两个以上合法 grouping | 模型可建议 grouping，local validator 再提交 |
| `missing_local_discriminator` | family 候选共享相同 local facts，缺少区分类别的必要 visual discriminator | 模型可识别局部形态，但不能直接写业务语义 |
| `local_validator_disagreement` | 两个独立 deterministic checks 对 bbox/source relation 得出不同 verdict | 模型输出只作为 Advisor evidence，最终仍需本地验证 |

`block` 只允许：

| Code | Required behavior |
| --- | --- |
| `source_reconstruction_mismatch` | systemic fail closed；不构造 Provider |
| `visual_geometry_invalid` | affected page fail closed；不让模型修复 geometry |
| `routing_contract_invalid` | systemic fail closed；不采用默认 route |
| `coverage_lineage_incomplete` | affected result 不可 complete；不得猜 source |

router 遇到未识别 pre-VLM reason、空 reasons 或 disposition/reason enum 不匹配时，
必须返回 `routing_contract_invalid`；不得选择默认 escalation。

### Post-Escalation Attempt And Outcome Codes

cache、budget 和 Provider 发生在 routing decision 之后，必须写入独立 immutable
records，不得回填或改写 pre-VLM `RoutingDecision`。

每次 cache lookup、Provider attempt、retry 或 cancellation 先追加 event：

```json
{
  "schema_version": "symbol-escalation-attempt/1",
  "escalation_group_id": "<stable group id>",
  "routing_decision_sha256": "<frozen pre-VLM decisions>",
  "attempt_index": 0,
  "event_code": "<one allowlisted event code>",
  "cache_provenance_ref": "<optional>",
  "provider_request_id": "<optional>"
}
```

attempt event 只记录发生过的动作，不表示 group terminal：

| Event code | Required behavior |
| --- | --- |
| `cache_hit_valid` | current schema/local validator 通过后消费，并记录 producer/consumer provenance |
| `cache_miss` | 没有 compatible entry，允许进入 Provider attempt |
| `cache_provenance_invalid` | quarantine cache record，按 miss 继续；不让 Provider 修复 cache |
| `provider_unavailable` | Provider construction/capability unavailable，未产生 request ID |
| `provider_response_valid` | response schema-valid；还需 per-observation local projection |
| `provider_schema_invalid` | 当前 attempt invalid；只有 bounded retry policy 允许时才继续 |
| `provider_timeout` | 当前 attempt timeout；late response 只能进入 audit |
| `provider_transport_failure` | 当前 attempt transport failure；不缓存 failure |
| `retry_scheduled` | 只允许现有 bounded retry budget，记录前一 attempt identity |
| `not_started_budget_exhausted` | group 未调用 Provider，进入 terminal unresolved |
| `cancelled_after_project_budget` | stop new call；已发出的 late response 不改 terminal head |

所有 attempts 停止后，每个 escalation group 恰好写一个 terminal outcome：

```json
{
  "schema_version": "symbol-escalation-outcome/1",
  "escalation_group_id": "<stable group id>",
  "routing_decision_sha256": "<frozen pre-VLM decisions>",
  "outcome_code": "resolved | partial_unresolved | unresolved | budget_exhausted | cancelled",
  "observation_outcomes": [
    {
      "visual_observation_id": "<stable id>",
      "outcome_code": "<one allowlisted observation outcome>"
    }
  ],
  "attempt_event_sha256s": ["<ordered immutable event hashes>"],
  "terminal": true
}
```

`observation_outcomes` 必须与 group input IDs exact-set equal，每个 ID 恰好一次并按
stable reading order 排列。允许同一 group 同时包含 resolved 和 unresolved
observations；此时 group code 只能是 `partial_unresolved`。

| Observation outcome code | Required behavior |
| --- | --- |
| `cache_resolved` | cache suggestion 和 local projection 均通过 |
| `provider_resolved` | Provider suggestion 和 local projection 均通过 |
| `provider_no_detection` | actionable unresolved，不伪装 `non_inspection` |
| `provider_projection_rejected` | schema-valid response 未通过 bbox/source/family projection |
| `provider_unavailable` | Provider 未构造或 capability unavailable |
| `provider_schema_invalid` | bounded retry 后仍 invalid |
| `provider_timeout` | bounded attempt terminal timeout |
| `provider_transport_failure` | bounded attempt terminal transport failure |
| `routing_budget_exhausted` | 未执行 observation 进入 unresolved coverage |
| `cancelled_after_project_budget` | cancellation 后 unresolved，late response 仅 audit |

### No Magic Confidence Threshold

router 不得使用 `confidence < X` 这一条规则决定 escalation。允许 confidence 作为
audit fact，但 decision 必须来自可解释 evidence matrix：

- family discriminator 是否存在；
- required value 是否来自同一 source/crop；
- geometry predicate 是否完整；
- text、OCR、geometry、parser 是否冲突；
- grouping 是否唯一；
- bbox/source lineage 是否闭合。

每个 locally resolved family 必须有 versioned boolean rule table、明确 required
facts 和 negative controls。任何 threshold 变更都需要 fixture + sealed-manifest
evidence，不能根据单次 production sample 自动拟合。

### Must-Fail-Closed Cases

以下情况禁止自动提交完整业务语义：

- 未知 symbol family 或超出当前九类 allowlist；
- GD&T frame 缺 datum/value、frame grouping 冲突或 geometry 不完整；
- counterbore/depth 的 value 不来自同一 local evidence group；
- datum/revision geometry 未通过现有 deterministic validator；
- Provider detection 缺 visual observation ID、bbox、associated text lineage 或
  `requires_confirmation=true`；
- local resolution 与 Provider suggestion 冲突；
- 任一 cache identity/schema/model/proposal/router version 不匹配；
- 任一 Quality Owner 必须确认的 symbol 尚未人工收口。

fail closed 允许生成 `partial_review_required` result 和 unresolved source，不允许
自动降级为 ordinary text、`non_inspection`、warning 或已覆盖。

### Bounded High-Recall Fallback

现有 all-observations route 只保留为：

1. `verification_high_recall`: fixture、shadow comparison 和 formal recall gate；
2. `legacy_high_recall`: deployment-level rollback。

它不得在 production uncertainty mode 中因一个 ROI 不确定而自动触发。fallback
必须由明确 mode/feature flag 选择，整次 project 只有一个 final write path；禁止
dual write、per-ROI readthrough 或 silent shadow promotion。

## Performance Design

### ROI Deduplication And Merge

在 call budget 计算前执行下列 deterministic 顺序：

1. 按 canonical local-evidence hash 去除同页 exact duplicate ROI；
2. 只有 source IDs、reason-code set 和允许的 symbol-family set 相同，且 bbox
   overlap/adjacency 满足 versioned merge rule 时才合并；
3. 不跨 page 合并 crop，不把两个不同 text owners 仅因位置接近而合并；
4. batch order 固定为
   `(page_index, reason_priority, bbox.y0, bbox.x0, escalation_group_id)`；
5. 每个 admitted observation 在 local resolution、escalation batch 或 unresolved
   coverage 中 exact-once，不得因 dedup 消失。

### Cross-Project Content-Hash Cache

cache key 必须与 project ID 无关，并至少绑定：

```text
canonical crop SHA-256
canonical associated-text allowlist SHA-256
ordered visual observation local-evidence hashes
router version
proposal version
prompt version
response schema version
adapter version
model identity
PyMuPDF/crop canonicalization version
```

约束：

- cross-project reuse 只允许同一 deployment 和同一 tenant/security boundary；
- project-scoped crop bytes 不复制到共享 cache；共享记录只保存 canonical response、
  content identity 和 provenance refs；
- schema-valid detection 或 schema-valid no-detection 可以缓存；timeout、transport、
  schema-invalid、budget-exhausted 和人工 verdict 不缓存为 model result；
- cache hit 仍须通过当前 schema、bbox/source allowlist 和 local projection validator；
- provenance 记录 producer request ID、response hash、created-at、model/schema/router
  identity、hit project 和 validation outcome；
- cache identity version 改变时直接 miss，不做 best-effort compatibility repair；
- legacy high-recall cache 只能由 legacy mode 读取，production uncertainty mode
  使用独立 namespace。

retention、tenant boundary 和 access policy 必须在 implementation plan 中绑定现有
storage/security contract；未确认前不得启用跨租户共享。

### Bounded Concurrency And Budgets

P0 初始 production budget 固定为：

| Budget | Limit | Exhaustion behavior |
| --- | ---: | --- |
| In-flight VLM calls per project | `2` | queue remaining escalation groups |
| Primary VLM calls per page | `4` | remaining groups -> `routing_budget_exhausted` |
| Primary VLM calls per project | `8` | remaining groups -> `routing_budget_exhausted` |
| Schema retry | existing maximum `1/project` | retry也计入 time，且不能扩大 primary group budget |
| VLM wall time per page | `45s` | affected groups unresolved |
| VLM wall time per project | `90s` | stop new calls；in-flight 按 bounded cancellation contract 收口 |

这些 limits 是 visual-symbol 子预算，继续嵌套在现有 unified text + visual
`MAX_CALLS_PER_PAGE=16` ceiling 内。任一页面必须同时满足
`visual_primary_calls <= 4` 和
`actual_visual_calls_including_retry + text_review_calls <= 16`；visual router 不得
抢占超过 unified ceiling 的 slots，text scheduler 也不得借 unused visual budget
绕过自己的既有 eligibility contract。

budget 是 hard ceiling，不是“尽量”。同一 project 的稳定结果不得依赖 task completion
race。Provider global rate limit 属于 infrastructure scheduler，不得改变 business
priority 或 silently drop ROI。

### Progressive Workbench

processing lifecycle 必须显式区分：

```text
local_processing
local_ready
vlm_enriching
ready_for_review
partial_review_required
```

- `local_ready` 后立即展示 locally resolved candidates、source、normalized result
  和 local/uncertain badge；
- VLM completion 通过 versioned、idempotent incremental result update 补充，不覆盖
  既有 preview revision；每次更新创建 immutable successor，不原地修改；
- UI 显示 local-resolved、cache-resolved、VLM-pending、VLM-resolved 和 unresolved
  counts，不显示 raw model response；
- Quality Owner 可在 enrichment 期间查看、定位 local results，但 mutation controls
  保持 disabled；只有 terminal `ready_for_review` 或
  `partial_review_required` AutomaticResult 才能创建 working copy 和执行 commands；
- freeze/export control 必须读取 backend completeness/Veto contract，不能用 spinner、
  HTTP status 或 frontend count 自行判断可用性；
- refresh/reconnect 后从 backend result versions 恢复同一 state，不依赖
  browser-local pending list。

### Latency And Call-Count Targets

以下是 future acceptance SLO，不是当前 baseline 声明。baseline 必须在 shadow
阶段同时记录 legacy 29-call path 和新 router，不能用单次 canary 伪造 percentile。

测量 cohort 至少包含 sealed current two-page source、current-four、sanitized
positive/negative fixture 和 approved perturbation set；每类至少 `20` 次独立 project
execution，报告样本数、cache warm/cold、queue wait、runtime identity 和原始分布。

| Metric | Clock boundary | P50 target | P95 target | Hard acceptance |
| --- | --- | ---: | ---: | --- |
| Local-ready latency | worker start -> backend `local_ready` persisted | `<=10s` | `<=20s` | sealed two-page cold-cache run `<=20s` |
| User-visible local result | upload accepted -> workbench renders local result | `<=15s` | `<=30s` | browser evidence shows usable local items before VLM terminal |
| Final enrichment latency | worker start -> `ready_for_review` or `partial_review_required` | `<=45s` | `<=90s` | no accepted sample exceeds project VLM budget without explicit partial state |
| Primary VLM calls per two-page project | persisted Provider call records | `<=2` | `<=6` | `<=8/project` and `<=4/page` |
| Cache-warm VLM calls | identical content identity replay | `0` | `0` | result/provenance exact and no Provider construction |

correctness gate 优先于 latency target。若达到 latency 需要降低 sealed recall、允许
frozen-negative candidate、跳过 unresolved coverage 或绕过 Quality Owner gate，
verdict 必须是 failed，不得调低验收口径。

## Correctness And Auditability

### Owner And Quality Gates

- Proposal admission Owner 不根据 call slots 删除 observation。
- Local resolver 不提交 final candidate；它只产生 deterministic evidence。
- Qwen adapter 仍是 Advisor，不提交 disposition、candidate、coverage 或 result
  completeness。
- Cache 只返回带 provenance 的 Advisor evidence，不成为 truth Owner。
- `CandidateAdvisor` 保持唯一 automatic candidate/coverage/result write Owner。
- Coverage service 继续阻断 missing/conflicting disposition。
- Quality Owner 明确 manual command 仍是 unresolved source 的唯一人工收口路径。
- Frontend 和 Harness 只消费/验证 Owner 输出，不推导正式成功。

### Required Audit Record

每个 observation/group 至少保留：

- proposal version、router version、reason codes 和 routing disposition；
- canonical local-evidence/input hash；
- source observation IDs、bbox 和 grouping identity；
- local resolver rule/digest 和 validation outcome；
- cache hit/miss、cache key、producer provenance 和 revalidation outcome；
- Provider/model/prompt/schema/adapter identity、request ID、duration、usage 和
  sanitized failure stage；
- response hash 和 schema validation outcome，不保留未授权 raw diagnostics；
- final candidate/coverage/result version；
- Quality Owner promote/ignore/correct/freeze command identity 和 audit summary。

日志、API、cache、Harness evidence 和 committed fixtures 继续通过 credential、
base64、private-path 和 raw-response privacy scan。

### Production Versus Verification Mode

#### Current-main default promotion amendment — 2026-08-03

用户已明确要求把先前完成但未启用的低延迟路径用于重新识别，并持续测试并发以取得当前 Provider/样本下的合适频率。此决定批准 current-main 的新项目默认路由从 `legacy_high_recall` 提升为 `production_uncertainty`，但不批准删除 legacy rollback、扩大既有 Provider call/wall/retry budget，或把并发提升到既有验证上限 `2` 以上。

- base `compose.yaml` 是所有 repo-owned Compose consumers（dev-local、feature worktree、QA overlay、server/deploy-main）的 public mode selection Owner；本次 repo-wide promotion 必须在 base、QA 与 server rendered config 中为 `api/worker` 显式得到 `QI_SYMBOL_RECOGNITION_MODE=production_uncertainty`，不得从 canonical `.env` 选择 routing。`Settings` 与 DB server default 继续保持 `legacy_high_recall` fail-safe；project intake/lifecycle 把 deployment selection 冻结为 `recognition_mode + recognition_router_version` immutable pair，已有项目不迁移、不重写。
- `CandidateAdvisor` 继续是 production ROI scheduling 与 in-flight window 的唯一 Owner。首轮 live tuning 只验证既有 `MAX_VISUAL_IN_FLIGHT=2`，并以同一输入的 legacy serial baseline、call count、wall time、Provider failure category 和 final semantics 判断是否保留 `2`；不得用 blind concurrency escalation 代替 uncertainty routing。
- rollback 不得删除 mode override 或依赖 `.env`/backend fallback；必须把 base Compose 的 API/worker literal 显式改为 `legacy_high_recall` 并重建 API/worker。rollback 只做 rendered config 与 effective settings 的 zero-paid identity proof；若已耗尽本 amendment 的两个 successor 额度，不得创建第三个 successor。已经冻结或生成的 production result 保持 immutable，任何 post-rollback successor 需要新的 paid-run authorization。
- promotion acceptance 要求 static fail-safe 仍为 legacy、rendered Compose 对 API/worker 都是 production、production concurrency/failure tests、fresh API/worker identity、至少一次真实 reprocess success，以及无 `rate_limited`/budget/wall failure。若 `2` 不稳定，只允许回到 serial/停止并形成新的 bounded amendment；不得在本 amendment 内尝试 `3+`。

| Mode | Purpose | Provider routing | Final write authority |
| --- | --- | --- | --- |
| `production_uncertainty` | 默认用户路径 | only reason-coded escalations | new router through `CandidateAdvisor` |
| `shadow_uncertainty` | 对照旧路径，不影响用户结果 | router 可生成 shadow plan；是否调用 Provider 需独立 live budget | legacy path only；shadow 永不写正式结果 |
| `verification_high_recall` | recall/negative regression evidence | all admitted observations within existing cap | test/Harness evidence only |
| `legacy_high_recall` | deployment rollback | existing all-observations path | legacy path through same `CandidateAdvisor` |

mode 必须在 run/project evidence 中明确记录。`shadow_uncertainty`、Harness 或
verification output 不得被 frontend 展示为 formal result。

## Migration And Rollout

### Phase 0: Contract And Offline Router

1. 先 amend stable result completeness、routing reason codes、cache provenance 和
   Quality Owner veto contracts。
2. 用 current immutable inventory/geometry evidence 实现纯 local resolver/router；
   禁止 Provider construction。
3. 对每个 admitted observation 证明 exact-one routing disposition 和 deterministic
   replay。

### Phase 1: Shadow Evaluation

同一 immutable input 同时计算：

- current legacy plan：`205 observations -> 13/16 batches -> 29 calls`；
- new uncertainty plan：local-resolved count、escalated count、deduped batches、
  projected calls、budget/unresolved count。

shadow 只比较 plan 和离线 projection，不双写 candidate/result。需要 live Provider
comparison 时必须另有明确 Heavy plan、固定 call budget 和 sanitized evidence。

### Phase 2: Recall Regression Gate

promotion 前必须同时通过：

1. sealed positive labels exact-match recall 不低于 verification high-recall mode；
2. frozen-negative candidate count 保持 `0`；
3. reference、non-inspection、ambiguous 和 candidate dispositions 不互相覆盖；
4. every admitted observation exact-once local/escalated/unresolved coverage；
5. current two-page source cold-cache primary calls `<=6`，hard max `<=8`；
6. current-four 无新增 blocking regression；
7. cache disabled/enabled、single-thread/concurrency=`2` 得到相同 final semantics；
8. independent reviewer 接受 Owner uniqueness、old-path mark、partial failure 和
   Quality Owner gate。

### Phase 3: Feature Flag Promotion

future implementation 使用一个 backend-owned mode flag，初始默认
`legacy_high_recall`：

```text
legacy_high_recall
shadow_uncertainty
production_uncertainty
verification_high_recall
```

promotion 顺序固定为 legacy -> shadow -> bounded canary ->
production uncertainty。一个 project 在创建时冻结 mode 和 router identity，处理中
不得切换。rollback 只对新 project 恢复 `legacy_high_recall`；已生成 result 保持
immutable，不重写、不删除。

`shadow_uncertainty` 是 transitional mode，真实 consumer 仅为 promotion
comparison。它必须在 `production_uncertainty` promotion 后第一个 development cycle
结束前删除；届时离线/Harness comparison 直接调用 pure router，不保留 runtime
shadow flag。backend mode flag 的 `legacy_high_recall` rollback option 最迟在下述
old-path deadline 到期时删除；`verification_high_recall` 随后只允许 test/Harness
entry，不再是 production runtime mode。

### Old Path Mark And Exit

当前路径在 canary promotion 前是 `preserve`，不是 removal candidate。canary
promotion 时必须写入下列 `mark`，并把 `last_verification` 更新为当时 fresh rollback
drill，不得沿用本 design 日期作为未来证据：

```text
[REMOVAL_CANDIDATE] current all-observations visual batch route
  reason: verification-era high-recall routing is too slow for default production
  owner: CandidateAdvisor with production uncertainty router
  real_consumer: verified deployment rollback for newly created projects
  trigger: two consecutive approved evaluation cycles pass recall, latency, partial-failure, cache, browser and Quality Owner gates
  deadline: end of the second development cycle after production_uncertainty canary promotion
  last_verification: <fresh legacy rollback drill run ID and date recorded at canary promotion>
```

到期时：

- 若 trigger 通过，删除 `legacy_high_recall` production rollback role 和对应 backend
  runtime flag branch，只保留 verification-only pure/test implementation；
- 若 verified real consumer 仍存在，必须重新 `mark` 并给出新 deadline；
- 若 consumer inventory 不清楚，verdict 为 blocked，不能把 flag 永久化。

### Cache Compatibility And Rollback

- new router 使用新 cache namespace，旧 `/5` high-recall cache 不隐式导入；
- legacy mode 继续读取 legacy identity；
- new cache schema/model/router 变更通过 versioned miss 迁移，不原地改写旧 record；
- rollback 不删除 shared cache，legacy mode 只忽略不兼容 namespace；
- rollback 后第一项 future verification 必须证明一个旧 project/replay 仍返回原
  immutable result ref，随后证明新 project 走 legacy high-recall path。

## Acceptance Criteria

### P0 Functional And Correctness

1. proposal admission 和 escalation 是两个独立 pure interfaces；unit test 可以构造
   admitted-but-local-resolved observation，并证明 Provider construction=`0`。
2. 每个 admitted visual observation 恰有一个 `locally_resolved / escalate / block`
   routing disposition，reason codes schema-valid、稳定排序且可重放。
3. current nine families 的 locally resolved rules 各有 positive、near-miss 和
   conflict negative controls；没有单一 confidence threshold。
4. sealed positive-label recall 不低于 `verification_high_recall`，frozen-negative
   candidate count=`0`。
5. Provider/cache suggestion 必须经过现有 schema、bbox/source allowlist 和 local
   projection validator；Provider 不成为 disposition Owner。
6. unknown、GD&T incomplete、composite conflict、datum/revision invalid geometry
   全部 fail closed，并以 unresolved source 进入 Quality Owner workbench。

### Performance And Call Count

7. reference cohort 按本文 measurement contract 生成真实 P50/P95，不把
   `513.44s/29 calls` 单样本称为 percentile baseline。
8. local-ready、user-visible local result、final enrichment latency 达到本文
   `10/20s`、`15/30s`、`45/90s` P50/P95 targets。
9. two-page project primary calls 达到 P50 `<=2`、P95 `<=6`，并机械证明
   `<=4/page`、`<=8/project`。
10. concurrency=`2` 与 concurrency=`1` 的 candidate、coverage、result
    completeness 和 audit hashes 语义等价；completion order 不改变 final result。

### Partial Failure

11. 单个 ROI timeout、transport 或 schema-invalid 时，其他 local/cache/VLM-resolved
    candidates 形成 immutable `partial_review_required` result；失败 ROI 保留完整
    source、reason 和 confirmation evidence。
12. partial result 可以进入 workbench，但 unresolved blocker 存在时 freeze、balloon
    confirm 和 export 均被 backend Veto Gate 阻断。
13. source reconstruction、routing contract 或 coverage lineage systemic failure
    不得创建 partial result。
14. retry、budget exhaustion 和 cancellation 都有 exact call record；不得出现
    orphan in-flight result 或 late response 覆盖已提交 version。

### Cache

15. identical content identity 跨两个 project、同一 tenant replay 命中 cache，
    Provider construction/calls=`0`，并保留 producer/consumer provenance。
16. crop、text allowlist、router、proposal、prompt、schema、adapter、model 或
    PyMuPDF identity 任一改变都必须 cache miss。
17. invalid provenance、schema-invalid response 和 transient failure 不得作为 cache
    hit；跨 tenant lookup 必须 miss。

### Observability And Browser UX

18. metrics 至少报告 admitted/local-resolved/escalated/deduped/cache-hit/call/
    unresolved counts、reason-code distribution、stage latency 和 budget outcome，
    且不含 credential、raw image 或 private path。
19. Chrome integrated browser test 证明 local results 在 VLM terminal 前可见和可审核，
    pending/resolved/unresolved counters 增量更新，refresh 后状态一致。
20. browser test 证明 raw model response 不可见，enrichment 期间 mutation controls
    disabled，terminal 后不存在 late response 改写 AutomaticResult，且 partial
    state 下 freeze/export controls 明确阻断。
21. current workbench 的 raw text、normalized result、source定位、promote/ignore、
    save/freeze 语义保持不变。

### Quality Owner And Rollout

22. Quality Owner gate 同时覆盖 sealed positives、frozen negatives、unresolved
    reasons、partial result 和 browser evidence；自动化指标不能替代人工 verdict。
23. `production_uncertainty` promotion 前完成 shadow comparison、recall regression、
    bounded canary、cache cold/warm、partial-failure 和 independent review evidence。
24. feature flag rollback 只影响新 project；旧 results、audit 和 cache provenance
    不被改写。
25. old path 在 replacement gate 通过前不删除，通过后按 explicit deadline 退役
    production role，不保留永久 dual path。

## Required Evidence

| Layer | Required new evidence | Minimum focus |
| --- | --- | --- |
| Unit: local resolver | family rule tables、conflicts、unknown、fail-closed | 9 families + negative controls |
| Unit: router | exact-one disposition、reason codes、no-confidence-only、determinism | all allowlisted reasons |
| Unit: ROI planner | dedup/merge、stable order、page/project/time budget、concurrency equivalence | cold and warm cache |
| Contract | routing decision、result completeness、cache provenance、mode identity | valid + malformed + version mismatch |
| Integration | native/OCR/local -> zero-call result；mixed local/VLM；partial failure；systemic failure | active and failure paths |
| Provider fixture | escalated-only prompt、schema validation、bounded retry、redacted records | `external_calls=0` |
| Cache integration | cross-project same-tenant hit、cross-tenant miss、identity invalidation | Provider construction asserted |
| Browser | local-first render、incremental enrichment、refresh、partial veto、manual command race | Chrome MCP integrated run |
| Harness | shadow legacy/new comparison、sealed recall、latency/call distribution、rollback | literal run IDs and immutable evidence |
| Independent review | Owner uniqueness、old-path lifecycle、cache isolation、Quality Owner gate | accept required before promotion |

Future implementation plan 必须绑定真实 test paths 和 commands；本文不发明尚不存在的
passing tests。至少应新增或等价覆盖：

```text
test_locally_resolved_visual_observation_skips_provider
test_escalation_reasons_are_explainable_and_deterministic
test_router_never_uses_confidence_as_sole_gate
test_roi_dedup_preserves_exact_once_coverage
test_project_budget_yields_partial_review_required
test_single_roi_provider_failure_preserves_local_result
test_systemic_lineage_failure_blocks_all_results
test_cross_project_cache_hit_revalidates_without_provider
test_cache_identity_and_tenant_mismatch_miss
test_concurrency_does_not_change_final_semantics
test_quality_owner_veto_blocks_partial_freeze_and_export
test_progressive_workbench_survives_refresh_and_late_response
```

## Scope Tiers

### P0

- current nine symbol families；
- separate proposal/local-resolution/escalation contracts；
- deterministic reason-coded router；
- ROI dedup/merge、bounded concurrency、page/project/time budgets；
- same-tenant content-hash cache and provenance；
- complete/partial-review result contract；
- progressive workbench and Quality Owner veto；
- shadow、feature flag、rollback and old-path exit gate；
- unit/integration/contract/browser/Harness/independent-review evidence。

### Later Optimization

- broader multi-project benchmark corpus and per-document-class SLO；
- cache eviction/retention tuning after measured storage evidence；
- adaptive provider batching that preserves deterministic final semantics；
- more symbol families、standalone symbols and scanned-document support；
- learned local classifier only after a separate labeled-data/privacy spec；
- provider diversification or circuit-breaker strategy after a separate Owner review。

### Non-Goals

- full standards interpretation；
- automatic Quality Owner approval；
- generic full-page Vision；
- silent best-effort success；
- dynamic online threshold training；
- cross-tenant cache；
- parallel final result writers；
- plan amendment or implementation in this spec turn。

## Rollback Design

1. rollout 前冻结 `legacy_high_recall` 为可验证 deployment rollback path。
2. new result/cache/routing records 必须 additive 和 versioned；旧 reader 不得误读为
   complete。
3. rollback 只切换新 project mode，不修改 active/terminal project、historical
   AutomaticResult、working copy、reviewed result 或 exports。
4. rollback 后禁止从 new namespace readthrough 到 legacy cache。
5. rollback 后先验证 old project immutable replay，再验证一个新 project 的 legacy
   routing、Quality Owner gate 和 call records。
6. 若 additive result completeness 无兼容 reader，rollback verdict 为 blocked；
   不得通过删除 partial data 恢复。

## Risks And Open Design Decisions

1. current nine families 中哪些 cases 可由 deterministic resolver 直接
   `locally_resolved`，仍需在 implementation plan 前冻结 exact rule tables 和
   negative controls；本 spec 只冻结 evidence contract，不伪造已完成规则。
2. `partial_review_required` 改变现有“任一 visual Provider failure ->
   AutomaticResult=0”行为，必须先完成 stable contract、persistence/API 和 migration
   compatibility review。
3. cross-project cache 的 tenant、retention 和 storage policy 必须绑定现有 security
   Owner；未证明隔离前只能保持 project-local cache。
4. `4/page`、`8/project`、`45s/page`、`90s/project` 是 initial acceptance ceilings，
   不是测得的最佳值。若 shadow recall gate 无法在这些 ceilings 内通过，必须回到
   contract Owner replan，不能静默提高预算或降低 recall。
5. progressive preview revisions 需要明确 single-head compare-and-swap、retry 和
   cancellation contract；terminal AutomaticResult 提交后，late VLM response
   只能进入 audit，不能成为第二 final writer。
6. current sealed two-page sample 不能代表任意工程图。P50/P95 promotion evidence
   必须扩展到本文定义的多样化、重复执行 cohort。

## Completion Boundary

本文完成只表示 production uncertainty router 的 design contract 已写明。它不表示：

- latency 或 call-count targets 已达到；
- partial result schema 已实现；
- cross-project cache 已启用；
- feature flag 已创建；
- old high-recall path 已退休；
- Provider、browser、Harness 或 current-four 已重新运行；
- unique current plan 已 amend 或 implementation 已获授权。
