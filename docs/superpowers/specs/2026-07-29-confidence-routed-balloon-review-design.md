# Confidence-Routed Balloon Review Design

## Status

- Date: `2026-07-29`
- Status: `approved direction; durable spec awaiting user review`
- Selected lane: `Heavy`
- Validation action: `replan`
- Execution authorization: 本文不授权 production implementation；用户批准本文后才创建唯一 successor implementation plan

## Context

当前审核体验把大量自动识别项呈现为待审核候选。尤其是视觉符号链，
`visual-symbol-review/1` 要求每个 detection 都携带
`requires_confirmation=true`，后续 projection 也把直径、深度、沉孔、粗糙度和
GD&T 候选统一标记为待确认。与此同时，正式气泡只能在整个 item set freeze 后
批量生成，因此一个待确认项会阻止整批进入正式编号和气泡校验。

用户批准把流程改成 exception-based review：

```text
high confidence
  → 自动进入正式候选集
  → 立即显示红色自动通过气泡
  → 无需逐条点击审核
  → 人工仍可编辑、排除或改成无需气泡

medium / low confidence
  → 进入人工审核队列
  → 不自动排除
  → 审核完成后进入同一正式候选集
```

该行为覆盖全部自动识别项，包括 native text、OCR 和 visual symbol，不只覆盖新接入
的视觉符号。

本文中的 `confidence` 表示“该 candidate 是否具备自动进入正式候选集的完整证据”，
不是 Provider 对某个字符或符号的主观概率。识别信号很高但 typed semantics、
source ownership 或 coverage 不完整时，candidate 仍不得自动通过。

## Verified Current State

当前 source 的关键事实如下：

- `backend/app/candidates/schemas.py::Candidate` 只有
  `requires_confirmation`，没有 candidate-level confidence decision。
- `backend/app/providers/visual_symbol_review.schema.json` 把 detection 的
  `requires_confirmation` 固定为 `true`；Provider response 没有 confidence signal。
- `backend/app/candidates/symbol_review.py::project_visual_observation()` 对可生成
  candidate 的视觉 projection 统一写入 `requires_confirmation=true`。
- `backend/app/review/service.py::ReviewService.create_from_raw()` 把所有 raw
  candidates 投影为 `status="pending"` 的 working-copy items。
- `ReviewService.freeze_blockers()` 只要发现 active item 或 coverage entry 仍有
  `requires_confirmation` 就阻止 item-set freeze。
- `backend/app/balloons/service.py::BalloonService.generate_formal()` 只能在
  `items_frozen_at` 已存在后，为全部 `balloon_required=true` items 批量生成连续
  formal numbers 和 balloon geometry。
- `frontend/src/components/pdf/OverlayLayer.tsx` 把 freeze 前的 candidate marker
  统一显示为蓝色；红色目前只属于 backend 已生成的 balloon。
- `frontend/src/components/workbench/inspectionItemPresentation.ts` 把
  `status="pending"` 的 active item 统一呈现为待审核。
- SIP detail fields 仍要求每个 active item 有完整、已确认的标准、方法、角色等
  business fields；candidate confidence 当前不拥有这些字段。

因此，当前根因是缺少一个位于 local validation 之后的 confidence decision Owner，
不是单纯缺少颜色或前端过滤条件。

## Goals

- 让满足完整高置信度合同的自动识别项无需逐条点击即可进入正式候选集。
- 让 high-confidence item 在 freeze 前立即显示红色自动通过气泡，并保持可编辑。
- 只把 medium/low-confidence items 和 source-only ambiguity 放入人工审核队列。
- 对 native text、OCR 和 visual symbol 使用同一个 decision contract，同时允许
  source-specific signal normalization。
- 保留 immutable `AutomaticResult`、versioned working copy、review commands、
  continuous formal numbering、collision veto、immutable `ReviewedResult` 和
  atomic export。
- 保留 Provider 只是 Signal Provider / Advisor 的边界；Provider confidence 不得
  单独提交自动通过结论。
- 保存 policy version、evidence codes 和人工 override provenance，使自动能力与
  人工修改可独立评估。

## Non-Goals

- 不让 high-confidence candidate 直接创建 `ReviewedResult` 或自动发布导出。
- 不在 item set freeze 前持久化 `formal_number`；freeze 前红色 marker 使用
  provisional candidate number。
- 不让模型凭空补造 SIP 的 inspection standard、method、role、key-dimension 或
  project metadata。
- 不把 low-confidence source 自动排除；低置信度仍必须可定位、复查、promote 或
  ignore。
- 不改变 `manual_required`、hard collision、unreadable number 或 export
  consistency blocker 的 fatal 语义。
- 不引入第二套 review aggregate、frontend confidence calculator、shadow
  classifier、runtime feature flag 或 silent fallback。
- 不把颜色作为 confidence 或正式状态的业务事实；颜色只投影 backend 已提交的
  decision。

## Selected Direction

用户批准方案 A：证据门控的统一 `ConfidencePolicy Owner`。

未采用的方案：

- 直接按 OCR/LLM 原始数值阈值放行：当前视觉 schema 没有 confidence，且不同
  Provider 的自报分数不可直接比较。
- 只按 item type 白名单放行：实现较安全但只表达静态规则，不足以形成覆盖全部
  自动识别项的统一 confidence contract。

方案 A 使用 Provider signal、deterministic parser、local validator、source
relations、coverage 和 conflict checks 的合取证据。只有该 Owner 能提交
`auto_accepted`；frontend、Review bootstrap 和 Balloon service 只消费其结果。

## Problem Boundary

### Changed Decision Dimension

本次只改变一个 decision dimension：

`automatic candidate review disposition`

输入是已经通过 candidate projection 的 immutable evidence；输出是：

- `confidence_band = high | medium | low`
- `review_disposition = auto_accepted | review_required`
- `confidence_policy_version`
- `evidence_codes`

### Single Owner

新增唯一 `ConfidencePolicy Owner`，canonical implementation location 为：

`backend/app/candidates/confidence.py`

它位于 candidate projection/local validation 之后、
`build_automatic_result()` 之前。它不得重读 PDF bytes、重新调用 Provider、生成
candidate、修改 coverage disposition 或创建 balloon。

### Unchanged Owners

- Parser/Grouping/Visual projection 继续拥有 candidate semantics。
- Coverage Owner 继续拥有 coverage completeness 和 blocking verdict。
- Review aggregate 继续拥有人工 command、working-copy version 和 freeze。
- Numbering Owner 与 Placement Owner 继续拥有 formal number 和 geometry。
- Reviewed-result Owner 继续拥有最终 immutable result。
- Export orchestrator 继续拥有三产物 atomic publish。

## Confidence Decision Contract

### Immutable Automatic-Result Envelope

confidence decision 存在 candidate envelope，不进入 typed semantic payload：

```json
{
  "candidate_id": "candidate-identity",
  "payload": {
    "item_type": "thread",
    "raw_text": "M6",
    "normalized_text": "M6",
    "balloon_required": true
  },
  "source_location_ids": ["observation-identity"],
  "confidence_decision": {
    "band": "high",
    "review_disposition": "auto_accepted",
    "policy_version": "candidate-confidence/1",
    "evidence_codes": [
      "typed_schema_complete",
      "single_source_owner",
      "coverage_clear",
      "no_conflict",
      "source_signal_high"
    ]
  }
}
```

约束：

1. `confidence_decision` 是 Automatic-result Owner 冻结的不可变事实。
2. `payload` 继续只保存 candidate semantics；confidence 不得伪装为 confirmed
   business field。
3. `evidence_codes` 使用冻结枚举并按稳定顺序保存，不存 prompt、reasoning-like
   text 或 raw Provider response。
4. `policy_version` 必须精确匹配实现中的 canonical policy。
5. 新结果使用 `automatic-result/2`；既有 `automatic-result/1` 不改写。
6. legacy candidate 没有 `confidence_decision` 时，reader 必须 fail closed 为
   `review_required`，不得推测 high。

### Source Signal Normalization

`candidate-confidence/1` 把来源信号统一映射到 `[0, 1]`：

- native text：只有 deterministic parser exact match、typed schema 完整且没有
  confirmation requirement 时，source signal 为 `1.0`；否则没有 high signal。
- OCR：每个 Provider adapter 按自身冻结 contract 规范化；当前 Tencent OCR adapter
  明确把百分制值除以 `100`。不得根据数值是否小于 `1` 猜测量纲。规范化结果越界
  或非有限时为 invalid。
- visual symbol：`visual-symbol-review/2` detection 新增 `[0, 1]` 的
  `confidence_signal`。该值只是 Signal Provider 输出，必须再通过 local projection
  和 confidence policy。
- manual item：不进入 automatic confidence policy；其 acceptance source 固定为
  `manual`。

source signal 不得在 frontend 重新归一化。

### Band Rules

先执行 hard eligibility gates，再计算 band。

以下任一条件成立时 band 固定为 `low`：

- typed schema 不完整或 local projection 失败；
- `feature_kind=unknown` 且该 type 的正式语义需要 feature kind；
- complex fallback 只有四字段粗语义；
- source location 缺失、多个 candidate 冲突占用同一 source，或 source ownership
  不唯一；
- coverage 未检查、存在 blocking entry 或该 candidate 仍关联 ambiguous source；
- possible duplicate、cross-view conflict、projection conflict 或 Provider schema
  rejection 尚未解决；
- candidate 自身或其 coverage entry 仍有语义级 `requires_confirmation`；
- `balloon_required` 未确定；
- normalized value 覆盖 source truth、数值无法通过 Decimal/typed validation，或
  visual association 没有对应 local text/geometry evidence。

通过 hard eligibility gates 后：

- `high`：normalized source signal `>= 0.95`；
- `medium`：normalized source signal `>= 0.70` 且 `< 0.95`；
- `low`：normalized source signal `< 0.70`、signal invalid，或缺少足够的 positive
  evidence。

只有 `high` 映射为 `auto_accepted`。`medium` 和 `low` 都映射为
`review_required`。band 只决定人工队列排序和解释，不允许 low 自动排除。

### Threshold Governance

`0.95 / 0.70` 是 `candidate-confidence/1` 的 frozen thresholds，不是 runtime
config。

在启用某个 source/type family 的 high path 前，固定回归集必须证明：

- high bucket 中没有 false positive；
- 所有 frozen negative 都未进入 `auto_accepted`；
- threshold boundary 的 `0.949... / 0.950...` 和 `0.699... / 0.700...`
  均有测试；
- Quality Owner 明确批准该 family 的 high eligibility evidence。

不能满足上述条件的 family 仍使用同一 policy，但必须通过 eligibility gate
fail closed 到 `medium/low`。不得为了让 UI 出现更多红色气泡降低 threshold。

## Provider And Old-Path Retirement

### Provider Schema

`visual-symbol-review/1` 当前同时输出 detection 和
`requires_confirmation=true`，让 Provider surface 间接决定 review disposition。
新路径选择 `replace`：

- 新 runtime response schema 为 `visual-symbol-review/2`；
- 删除 detection 中的 `requires_confirmation`；
- 新增 `confidence_signal`；
- Provider 仍只输出 `visual_observation_id`、`symbol_kind`、bbox、associated text
  IDs 和 signal；
- candidate projection 不再无条件写入 confirmation state，而是提交 semantic
  completeness facts给 ConfidencePolicy Owner。

不得保留 v1/v2 双 runtime writer、readthrough、shadow comparison 或 fallback。
历史 Provider call record 和 `automatic-result/1` 仍是不可变证据，不属于 active
runtime compatibility path。

### Review Bootstrap

`ReviewService._current_item()` 当前把全部 candidates 写成
`status="pending"`。新路径选择 `replace`：

- `auto_accepted` candidate：
  - `status="auto_accepted"`
  - `requires_confirmation=false`
  - `acceptance_source="confidence_policy"`
  - 保留完整 `confidence_decision`
- `review_required` candidate：
  - `status="pending"`
  - `requires_confirmation=true`
  - `acceptance_source=null`
  - 保留完整 `confidence_decision`
- legacy candidate 缺少 decision：
  - `status="pending"`
  - `requires_confirmation=true`
  - `acceptance_source=null`

Review bootstrap 不重算 band，不读取 raw Provider score，也不根据 item type 自行
放行。

## Human Override Semantics

high-confidence item 自动通过后仍是普通 active working-copy item：

- 用户可以 edit、exclude、merge、split、设置 `balloon_required` 或修改来源关系；
- 任一人工语义修改继续走唯一 `ReviewService.apply()` command path；
- 人工修改后 `acceptance_source` 变为 `manual_override`，并保存原
  `confidence_decision` 作为 provenance；
- 人工 edit 已经是显式确认，不把 item 重新放回待审核队列；
- merge/split 产生的新 item 不继承 high band；其 acceptance source 为
  `manual_override`；
- 排除只改变 working copy，不改写 immutable AutomaticResult；
- 任何影响 item set、source 或 `balloon_required` 的修改继续标记 numbering
  stale。

若用户显式要求“重新按自动结果恢复”，必须复用现有可恢复/重建语义并创建明确
operation；不得静默覆盖 manual override。本 feature 不新增该命令。

## Review Queue And Freeze

人工队列只包含：

- `confidence_decision.review_disposition="review_required"` 的 active items；
- legacy candidates；
- unresolved source-only coverage entries；
- 人工操作后新产生但尚未显式完成的 ambiguous item。

`coverage.review_required_count` 继续只统计 unresolved coverage entries。backend
workbench projection 新增 `manual_review_count`，按唯一 review target 统计
`review_required` active items 与 source-only entries，candidate 与其 coverage
entry 不得重复计数。frontend 不得通过颜色或数组过滤重算该 count 或正式 blocker。

item-set freeze 保持以下条件：

- coverage blocking 为零；
- 所有 `review_required` item 和 source-only entry 已解决；
- 所有 active item 的 `balloon_required` 已确定；
- SIP metadata/detail blockers 已解决。

high-confidence item 不需要逐条 `resolve_confirmation` 或 `keep` command。

## Balloon And Numbering Semantics

### Before Freeze

high-confidence item 立即显示红色自动通过气泡，但它仍是 working-copy projection：

- 使用现有 deterministic candidate number；
- 不创建 `Balloon` row；
- 不写 `formal_number`；
- accessibility label 为
  `自动通过气泡 {number}，待统一编号`；
- legend 分成同一红色色相的两个可区分样式：
  - 红色空心：`自动通过，待统一编号`；
  - 红色实心：`正式气泡`；
- 点击红色气泡继续选中同一个 `item_id` 并允许人工编辑。

medium/low item 继续显示候选 marker，并在列表显示 confidence badge 和待审核原因。

### After Freeze

现有 `BalloonService.generate_formal()` 继续：

- 为全部 frozen `balloon_required=true` items 批量分配唯一、连续 formal
  numbers；
- 创建 backend Balloon rows；
- 执行 deterministic placement；
- 对 `manual_required`、collision、number/readability 和 source relation 执行
  Veto Gate。

freeze 后红色 marker 消费 backend Balloon projection，accessibility label 才能
使用 `正式气泡`。不得把 freeze 前 provisional number 冒充 final number。

## SIP Boundary

confidence policy 只拥有 candidate review disposition 和 balloon eligibility，
不拥有 SIP business fields。

- 如果 inspection standard、method、role、key dimension 等字段来自已批准的
  versioned business rule，可由该 rule Owner 写入 confirmed fields，并记录
  rule/version。
- 没有 approved rule 时，这些字段仍由人工填写并确认。
- Provider suggestion、confidence band 或红色气泡不能自动确认 SIP 字段。
- SIP blocker 和 candidate review queue 必须在 UI 中分开计数，避免用户误以为
  “自动通过气泡”仍要求逐条重复审核。

## Frontend Contract

### Item Status

frontend 新增明确状态：

- `auto_accepted`：高置信度、自动进入正式候选集；
- `pending`：中低置信度或 legacy item，等待人工；
- `confirmed`：人工已确认或人工 override；
- 现有 `excluded / manual / collision / source_pending` 保持不变。

### Visual Treatment

- `auto_accepted` candidate marker 使用现有正式气泡红色系 `#c23b3b`；
- selected 状态使用同一 hue 的实心高对比样式，不改为蓝色；
- medium/low 保持非红色候选样式，并通过文字 badge 显示
  `中置信度 / 低置信度`；
- color 不是唯一提示，screen-reader label 和 table status 必须同时表达状态；
- summary 新增 `自动通过` 和 `待人工审核` 两个独立 counts；后者只消费 backend
  `manual_review_count`；
- 默认审核 filter 首先展示待人工审核项，但“全部”仍包含可编辑的自动通过项。

### Editability

红色自动通过气泡、table row 和 detail form 复用现有 selection identity。用户点击
后可以：

- 修改识别字段；
- 排除；
- 改为无需气泡；
- 使用现有 merge/split；
- 查看 confidence band、policy version 和 evidence summary。

frontend 不允许修改 band 或 policy version。

## API And Persistence Compatibility

- AutomaticResult JSON schema 从 `/1` 升级到 `/2`，不需要数据库 migration。
- ReviewWorkingCopy 的 JSON items 新增 additive fields，不需要数据库 migration。
- Project workbench response 和 frontend `ReviewItem` 新增 additive confidence
  projection。
- `ReviewedResult` 继续冻结 working-copy item 和 balloon snapshot；必须保留
  `acceptance_source` 与 confidence provenance。
- export mapping 不把 confidence 字段写入 SIP business columns；manifest 新增
  `confidence_policy_versions`、`auto_accepted_item_count` 和
  `manual_override_item_count` 作为 provenance。
- 读取 legacy `/1` 时 fail closed；不回填、不改写、不猜测。

## Failure Handling

- confidence signal 缺失、非法、越界或非有限：band 为 low，进入人工队列。
- policy version 未知：processing 失败为 structured contract error，不创建
  AutomaticResult。
- candidate envelope 缺少 required confidence fields：新 `/2` result 拒绝持久化。
- high candidate 存在任一 eligibility veto：band 固定为 low，不得记录
  `auto_accepted`。
- frontend 遇到未知 band/status：显示待审核并阻止 freeze，不得默认红色。
- policy evaluation 异常：fail closed，不允许部分 candidates 自动通过后仍报告
  overall success。
- formal placement 失败：继续返回 `manual_required`，与 recognition confidence
  无关。

## Evaluation And Metrics

自动能力、人工效率和正式交付继续分层评估：

- automatic layer：
  - high/medium/low counts；
  - high false-positive count；
  - per-source/type band distribution；
  - eligibility veto distribution。
- review-efficiency layer：
  - manual queue size；
  - auto-accepted item 的人工修改率、排除率和 balloon override rate；
  - medium/low 的确认、修改和排除率。
- formal-delivery layer：
  - final active item/balloon counts；
  - formal numbering continuity；
  - collision/manual-required blockers；
  - reviewed/export identity consistency。

不得用 reviewed correctness 反向覆盖 raw automatic metrics。high item 后续被人工修改
必须同时计入 automatic false-positive/override analysis 和 reviewed success。

## Verification Contract

### Unit

- native exact parser high eligibility；
- OCR confidence normalization 的百分制、单位制、边界和 invalid values；
- visual `confidence_signal` schema boundary；
- `0.70`、`0.95` 及其相邻值；
- 每个 hard eligibility veto 都阻止 high；
- low 永不自动 exclude；
- evidence-code order 和 policy digest deterministic。

### Integration

- mixed high/medium/low AutomaticResult 创建一个 working copy；
- high item 无需 command 即不进入 `manual_review_count`；
- candidate 与对应 coverage entry 在 `manual_review_count` 中只计一次；
- medium/low 分别需要人工 resolve；
- legacy `/1` candidate fail closed；
- high item edit/exclude/balloon toggle 保留 immutable raw result 和 operation
  provenance；
- merge/split 不继承 high；
- SIP blocker 与 confidence queue 独立；
- freeze 后 formal numbers 覆盖 high 和人工确认项并保持连续；
- `manual_required` 和 collision 仍阻止 confirm。

### Frontend

- high item 显示红色自动通过气泡和非颜色状态文本；
- high item 不出现在默认人工队列，但在“全部”中可选中编辑；
- medium/low 显示正确 badge 和原因；
- red marker selection 与 table/detail identity 一致；
- manual edit 成功、失败重试和 dirty-selection guard 不退化；
- freeze 前 accessibility 不称为 formal number，freeze 后正式 label 正确。

### Browser

使用真实 PDF 和当前 production entry 验证：

1. 上传后至少一个经批准 family 的 high item 无需点击即显示红色自动通过气泡；
2. medium/low item 只出现在人工队列；
3. 编辑一个红色 item 后刷新，manual override 持久化；
4. 解决人工队列后 freeze；
5. formal numbering 连续且红色 marker 切换到 backend Balloon projection；
6. `manual_required` 或 collision 仍阻止 final confirm；
7. 最终 PDF、SIP Excel 和 manifest 仍引用同一 `reviewed_result_id`。

## Rollback

- implementation 使用可独立 revert 的 contract、backend、frontend 和 verification
  commits。
- rollback 前停止新 processing submissions，并等待 active logical tasks 到终态。
- rollback 不能删除或改写已有 AutomaticResult、working copy 或 reviewed result。
- `/2` raw results 和 confidence provenance 必须继续可读；若旧 reader 不能安全读取，
  rollback verdict 为 blocked，必须 forward-fix compatible reader。
- 已创建的 working copy 保留 auto/manual acceptance provenance；rollback 不把
  auto-accepted item 静默改回 pending，也不自动创建 formal balloon。
- rollback 后第一项验证是 legacy `/1` result 能创建 working copy 且全部
  confidence decision fail closed；随后验证 formal numbering、collision veto 和
  atomic export baseline。
- 不保留 disabled flag、shadow scorer、v1/v2 dual writer 或 frontend fallback
  作为 rollback 手段。

## Ownership And Old-Path Summary

| Surface | Old action | New owner/role |
| --- | --- | --- |
| `visual-symbol-review/1.requires_confirmation` | `replace` | v2 Provider 只提供 signal；ConfidencePolicy Owner 决定 review disposition |
| candidate projection 无条件 confirmation | `replace` | projection 提交 semantics/evidence，不提交 auto acceptance |
| `ReviewService._current_item(status="pending")` for all | `replace` | 消费 immutable confidence decision；legacy fail closed |
| frontend pending/color inference | `replace` | 只投影 backend status/band |
| formal numbering after freeze | `preserve` | Numbering Owner 仍是唯一 Owner |
| collision/manual-required Veto Gate | `preserve` | Balloon validator 仍是唯一 Veto Gate |
| SIP confirmation Owner | `preserve` | versioned business rule 或人工确认 |

control-plane complexity 增加一个必要 Owner，但删除 Provider 和 frontend 对 review
disposition 的隐式决定，最终 effective writer 仍只有一个。

## Planning Status

- Selected lane: `Heavy`
- Selected plan: 当前没有获批的 successor implementation plan；本文通过用户 review
  后创建唯一新 plan
- Selection evidence: 用户批准全部自动识别项使用方案 A，并明确 high-confidence
  item 显示红色气泡、无需逐条审核但保持人工可改
- Validation action: `replan`
- Writer ownership and order: 当前 turn 只有父 agent 修改本 spec；production code
  无 writer
- Unchanged contract: project-level freeze、formal numbering、balloon validation、
  immutable ReviewedResult 和 atomic export
- Old path action: Provider confirmation、projection confirmation、all-pending bootstrap
  统一 `replace`
- Next verification: spec placeholder/consistency/scope scan、exact diff review、commit，
  然后进入用户 review gate

## Acceptance Criteria

本设计完成的必要条件：

1. high-confidence item 不需逐条 command 即进入正式候选集；
2. high item freeze 前立即显示红色、可编辑的自动通过气泡；
3. medium/low 和 legacy items 仍需人工审核且不被自动排除；
4. Provider 不能单独决定 auto acceptance；
5. legacy results fail closed；
6. human override、raw automatic metrics 和 reviewed result provenance 分离；
7. formal number 仍只在 item-set freeze 后生成；
8. SIP、collision、manual-required 和 export blockers 不被 confidence 绕过；
9. active/failure/legacy/browser paths 都有验证；
10. 不保留第二 Owner、dual writer、shadow path 或 silent fallback。
