# Structured Geometric Tolerance Recognition Design

## Status

- Date: `2026-08-01`
- Status: `proposed`
- Selected lane for future implementation: `Heavy`
- Execution authorization owner: unique approved implementation plan
- Current-state evidence: `docs/superpowers/audits/2026-08-01-geometric-tolerance-recognition-current-state.md`

本文定义结构化几何公差识别的目标能力、唯一 Owner、数据合同、失败边界和验收
口径。它不切换 current P0 plan，不授权 production code、migration、runtime config、
contract matrix、Harness 或 frontend 变更。

## Problem Statement

当前视觉响应已经能区分 `gdt_parallelism`、`gdt_perpendicularity` 和
`gdt_flatness`，但业务候选只保存 `raw_text + coarse_type + coordinates +
requires_confirmation`。这使 subtype、数值、datum 和 modifier 无法被 API、review、
UI 或 export 可靠消费。

真实 `∥ | 0.1 | A` 还暴露了更早的关联缺口：datum `A` 已被 native PDF extraction
提取并位于视觉 ROI 内，但当前 proposal 只关联触发 ROI 的单个 line/span，因此 `A`
没有进入 recognition input contract。

## Goals

- 把 feature-control frame 识别为一个有序、可追溯、可人工复核的 typed candidate。
- 至少支持本 Specs 定义的 GD&T subtype、数值、datum、diameter zone 和材料条件。
- 支持单 segment、多 datum、复合/多层 frame，保留 frame cell 顺序。
- 对 native、hybrid、scanned 输入使用同一 canonical domain contract。
- 原始视觉/OCR 证据可追踪，但 Provider、OCR、frontend 和 database 不成为业务语义
  Owner。
- 在 `AutomaticResult -> review working copy -> reviewed result -> workbench API -> UI`
  全链路保持结构化字段。
- 对不完整或冲突 frame fail closed，进入人工确认，不以猜测补齐。
- 保持原图 raw text/glyph、bbox、source IDs 和 confidence provenance。

## Non-Goals

- 不在前端从 `raw_text` 反向解析 GD&T。
- 不让 VLM 直接提交正式业务 candidate、review status 或 export 语义。
- 不把 datum feature symbol 单独自动创建为 inspection item。
- 不把未确认的 standards 语义在数据层强制解释；ASME/ISO/GB 差异通过
  `standard_context` 与 raw symbols 保留。
- 不在没有替代路径和 migration exit gate 时删除旧 coarse data reader。
- 不承诺任意字体、任意损坏扫描件或任意企业私有符号零人工确认通过。

## Ownership And Retirement Boundary

### Single Owner

`backend/app/candidates` 内的 canonical `GeometricToleranceNormalizer` 是唯一业务语义
Owner。它消费经过验证的 frame/cell evidence，提交 typed candidate 或明确失败码。

以下层只提供证据或消费结果：

- PDF inventory：拥有 text/vector/raster observation 与坐标；
- OCR/VLM：拥有 raw evidence 和 confidence signal；
- Provider validator：拥有 frozen response 合法性；
- persistence：只保存 canonical payload；
- API：只序列化 typed union；
- frontend：只展示/编辑 canonical fields；
- export：只消费 frozen reviewed result。

### Old Path To Replace

目标路径落地后，应替代：

- `symbol_review.project_visual_observation()` 中 `gdt_* -> CoarseCandidate` 分支；
- `automatic_result._coarse_type()` 对已支持 GD&T glyph 的 generic fallback；
- frontend 以 `coarse_type="geometric_tolerance"` 作为唯一业务展示的路径。

所有识别到或疑似 GD&T 的新输入都必须先进入 `GeometricToleranceNormalizer`；已支持
输入提交 typed subtype，不支持或不确定输入只能提交 typed `unknown` 或 Coverage
ambiguity，**不得继续生成新的 GD&T `CoarseCandidate`**。旧 coarse reader 只能读取
历史数据。退出条件必须包含历史 consumer inventory、backfill/read compatibility、
deadline 和可验证的删除 commit；不得永久双写或建立 shadow semantic owner。

### Unchanged Contract

- Provider 不拥有正式 disposition。
- Coverage Ledger 必须 exact-once 覆盖每个 frame proposal。
- blocking/fatal failure 不能降级成 formal success。
- review/freeze/export 仍只消费同一 reviewed result。
- coordinates 使用 PDF space；render space 只作为显示投影。

## Target Data Contract

### Candidate Discriminator

typed union 新增：

```json
{
  "item_type": "geometric_tolerance",
  "schema_version": "geometric-tolerance-candidate/1"
}
```

`category` 和 `measurement_type` 不建立重复 Owner：

- canonical discriminator 是 `item_type="geometric_tolerance"`；
- API 如为兼容需要输出 `category`，其值必须由 `item_type` 派生，不能独立写入；
- `measurement_type` 不进入 v1，避免与 `tolerance_type` 重复。

### Canonical Candidate

```json
{
  "item_type": "geometric_tolerance",
  "schema_version": "geometric-tolerance-candidate/1",
  "raw_text": "∥ | 0.1 | A",
  "normalized_text": "∥ | 0.1 | A",
  "tolerance_type": "parallelism",
  "tolerance_symbol": "∥",
  "tolerance_value": "0.1",
  "diameter_modifier": false,
  "modifiers": [],
  "datum_references": [
    {"datum": "A", "modifiers": []}
  ],
  "frames": [
    {
      "segments": [
        {
          "tolerance_value": "0.1",
          "diameter_modifier": false,
          "modifiers": [],
          "datum_references": [
            {"datum": "A", "modifiers": []}
          ]
        }
      ]
    }
  ],
  "standard_context": "unspecified",
  "coordinates": [0.0, 0.0, 1.0, 1.0],
  "source_location_ids": [],
  "evidence_ref": "asset://...",
  "confidence_decision": {
    "band": "low",
    "review_disposition": "review_required",
    "policy_version": "candidate-confidence/1",
    "evidence_codes": []
  },
  "requires_confirmation": true
}
```

Rules：

- 数值使用 decimal string，禁止 binary float 成为 canonical value。
- `datum_references` 保序；不得 set 化或字母排序。
- `frames[]` 是多层/复合结构的唯一 canonical shape；禁止另建 parent/child group
  表达同一层级。
- top-level type/symbol/value/datum fields 是第一 frame 第一 segment 的便利投影，必须
  由 `frames[0].segments[0]` 和 canonical subtype mapping 派生；不能独立写入。
- `tolerance_symbol` 由 `tolerance_type + standard_context` 的版本化 canonical mapping
  派生；原图 glyph 只保留在 `raw_text`/evidence。
- `normalized_text` 由 canonical `frames[]` serializer 单向生成，禁止 producer 或 UI
  独立修改后与结构字段分歧。
- `raw_model_output` 不直接内嵌 API/working copy；使用不可变 `evidence_ref` 指向脱敏
  artifact，并由权限边界控制读取。
- `source_image_id` 不作为必需字段；canonical provenance 使用现有
  `source_location_ids`，raster crop 通过 evidence manifest 关联。
- `review_status` 继续使用现有 item `status`；不新增同义状态字段。

### Tolerance Type Enum

v1 canonical enum：

```text
straightness
flatness
circularity
cylindricity
profile_of_line
profile_of_surface
angularity
perpendicularity
parallelism
position
concentricity_or_coaxiality
symmetry
circular_runout
total_runout
unknown
```

`unknown` 必须保留 raw symbol、cell evidence 和 `requires_confirmation=true`；不能被
自动映射到最相似 subtype。标准废弃/差异项由 `standard_context` 和 reviewer 决定，
不在 Provider prompt 内静默归一化。

### Modifiers

每个 modifier 保存：

```json
{
  "kind": "maximum_material_condition",
  "raw_symbol": "M"
}
```

v1 kind 精确冻结为：

- `maximum_material_condition` (`M`)
- `least_material_condition` (`L`)
- `regardless_of_feature_size` (`S`，仅在适用 standards context 下解释)
- `unknown`

直径 zone 由 `diameter_modifier` 独立表达，不混入通用 modifier list。任何 modifier
必须保留 raw glyph，避免字体/OCR alias 导致不可逆归一化。

### Composite And Multi-Layer Frames

- `frames[]` 是唯一多层容器；每个 frame 包含有序 `segments[]`，每个 segment 有独立 value、zone、modifier 和
  datum reference list。
- 多层 frame 只使用有序 `frames[]` 表达，不把换行拼成一个 `raw_text` 后丢失层级。
- repeated datum、common datum、组合 datum 的语法在 normalizer 内验证；证据不足时
  整个 candidate 保持 review-required，不拆出未经确认的多个 inspection item。

## Recognition Architecture

```text
page observations
  -> frame proposal
  -> frame boundary validation
  -> ordered cell segmentation
  -> per-cell evidence extraction
       symbol cell: vector/template/VLM classification
       numeric/text cell: native text or OCR
       modifier/datum cell: constrained token recognition
  -> frozen evidence schema validation
  -> GeometricToleranceNormalizer
  -> typed candidate or explicit ambiguous/failure coverage
```

### Frame Proposal

- native vector PDF 优先用 line geometry 检测闭合/连续 cell boundary；text anchor 只能
  提供 proposal，不能限制 frame 内可见 text IDs。
- proposal 必须收集所有与 frame/cell 相交或位于受控 padding 内的 text observations，
  解决“独立 datum line 在 ROI 内却未关联”的现有缺口。
- raster/scanned page 使用受限 ROI detector 或 line segmentation；不得把整页直接交给
  Provider 作为 formal recognition input。
- proposal 输出 frame bbox、cell bboxes、source IDs、geometry confidence 和明确版本。

### Cell Segmentation

- vector path 可证明 vertical separators 时，优先确定性切分。
- raster line 粘连/断裂时允许 VLM 提供 cell-boundary evidence，但必须由本地 validator
  检查顺序、范围、重叠和 frame containment。
- cell order 按图纸阅读顺序固定，不按模型返回顺序直接提交。
- 无法稳定分格时提交 `gdt_frame_segmentation_ambiguous`，不得退化成只取数字的
  coarse success。

### Provider Evidence Contract

新 Provider schema 应返回 evidence，而不是 business candidate，至少包括：

- `frame_observation_id`
- `cell_detections[]`
- 每个 cell 的 `cell_role`、bbox、symbol/token candidates、confidence signal
- 引用的 text observation IDs
- schema/prompt/model versions

Provider 不返回 `status`、`requires_confirmation`、正式 datum graph、final decimal 或
export 字段。本地 normalizer 必须验证：

- 所有引用 ID 属于当前 frame allowlist；
- bbox 位于 frame/crop 内；
- symbol/type mapping 唯一或明确 ambiguous；
- tolerance value 是合法 decimal string；
- datum 与 modifier 的顺序和 cell role 合法；
- 多 segment 结构无 silent truncation。

## Persistence And API Contract

### Persistence

- v1 可继续存入 `AutomaticResult.candidates JSONB`，但必须先由 exact Pydantic typed
  model 验证；“JSONB”不能等同于“无 schema”。
- ReviewWorkingCopy/ReviewedResult 必须保留 typed payload，不得降回 opaque coarse
  object。
- Provider evidence 保持单独不可变 artifact/cache；candidate 只保存 stable ref、
  source IDs 和派生 confidence decision。
- migration 必须说明 `automatic-result/1`、`/2` 历史 reader 的 consumer、期限和退出
  gate。新数据禁止同时写 typed 和 coarse 两个 semantic owner。

### API

- OpenAPI `ReviewItem` 改为 discriminated union，GD&T variant 精确声明本文字段。
- `/workbench.working_copy.items[]` 返回 typed candidate；overlay candidate 继续只拥有
  bbox/status 元数据。
- PATCH/review command 使用 field allowlist：允许 reviewer 修改 subtype、value、
  diameter flag、modifiers、datum order 和 raw/normalized text；所有修改进入 audit
  event。
- 未授权 consumer 不读取 `evidence_ref` 对应 raw Provider artifact。

## Frontend Contract

列表至少展示：

- 大类：`几何公差`
- subtype：`平行度`、`平面度` 等本地化名称
- canonical symbol
- tolerance value
- diameter zone 与 modifiers
- 按序 datum references
- review/confidence 状态

`∥ | 0.1 | A` 的默认可见文本应至少等价于“平行度 | 0.1 | 基准 A”；
`⏥ | 0.08` 应至少等价于“平面度 | 0.08”。

UI 不解析 `raw_text`，不把 unknown glyph 猜成已知 subtype。编辑器对每个结构化字段
独立呈现并保留原始 frame crop 作为证据；保存后再次读取必须与提交 payload 一致。

## Failure Semantics

| Failure code | Meaning | Required disposition |
| --- | --- | --- |
| `gdt_frame_not_found` | 无可信 frame boundary | ambiguous / review required |
| `gdt_frame_segmentation_ambiguous` | cell order/边界不确定 | review required |
| `gdt_symbol_unknown` | symbol 无唯一 subtype | typed unknown + review required |
| `gdt_value_missing` | 无唯一 tolerance decimal | blocking candidate ambiguity |
| `gdt_datum_association_ambiguous` | datum 在 ROI 内但归属不唯一 | review required；不得静默删除 |
| `gdt_modifier_unknown` | modifier 无法验证 | preserve raw + review required |
| `gdt_composite_truncated` | segment/layer 未完整覆盖 | fatal for formal success |
| `gdt_projection_conflict` | evidence 与 local grammar 冲突 | review required |

任何失败都必须进入 Coverage Ledger，包含 frame/source IDs、reason code 和可复查 bbox。

## Compatibility And Rollout Requirements

未来 implementation plan 必须显式记录：

1. problem boundary：只扩 GD&T typed path；
2. single owner：`GeometricToleranceNormalizer`；
3. old path：`gdt_* -> CoarseCandidate`；
4. unchanged contracts：coverage、review/freeze/export、Provider non-owner；
5. focused verification command；
6. historical data reader 和 retirement deadline；
7. current-four live corpus 的独立 reviewer gate。

禁止长期 shadow write。允许在 read boundary 将历史 coarse item 标记为
`legacy_geometric_tolerance`，但不得无证据从历史 `raw_text` 自动升级成 formal typed
candidate。

## Test And Evidence Matrix

### Required Minimal Semantics

| Case | Expected |
| --- | --- |
| `∥ | 0.1 | A` | parallelism, `0.1`, datum A |
| `⏥/▱ | 0.08` | flatness, `0.08`, no datum；glyph alias 有明确 policy |
| `⊥ | ⌀0.05 M | A | B | C` | perpendicularity, diameter zone, MMC, ordered A/B/C |
| position + L modifier | position, LMC, ordered datums |
| straightness without datum | datum list empty and valid |
| profile with datum | correct profile subtype and datum order |
| circular/total runout | distinct subtype |
| two-segment composite frame | both segments preserved in order |
| multi-layer frame | layer hierarchy preserved |
| unknown symbol | unknown + review required, no guessed subtype |

### Required Image Conditions

- native vector PDF crop；
- embedded raster crop；
- low resolution；
- skew/rotation；
- broken frame lines；
- line adhesion；
- scan noise；
- font/glyph aliases；
- datum letter near unrelated table/text negative；
- M/L/S lookalike negative。

### Required Test Layers

- unit：frame grammar、cell order、decimal、datum、modifier、failure codes；
- contract：Provider evidence schema、typed candidate schema、OpenAPI union；
- integration：inventory -> evidence -> normalizer -> JSONB -> working copy；
- API：GET/PATCH round trip，不丢字段；
- frontend：subtype/value/datum renderer 与 editor；
- E2E frozen provider：两个最小案例和 composite case；
- live Provider smoke：脱敏真实 ROI；
- current-four headed workbench：真实 PDF item、review save、reload；
- export：同一 frozen reviewed result 保持 subtype/value/datum。

Synthetic fixture 不能替代 live evidence。formal readiness 至少需要 sealed manifest，记录
source hash、crop hash、model/prompt/schema versions、candidate payload、API response 和
headed UI screenshot。

## Acceptance Criteria

1. Case A 从 inventory 到 UI 精确得到 parallelism、`0.1`、datum A；datum 不再仅是
   source-only context。
2. Case B 从 raw evidence 到 UI 精确得到 flatness、`0.08`；`▱/⏥` alias policy 在
   tests 中固定。
3. 所有支持 subtype 不依赖 frontend/raw-text parsing。
4. `AutomaticResult`、working copy、reviewed result、API 和 reload 后字段完全一致。
5. Provider raw subtype/confidence 可追溯，业务 candidate 不以内嵌 raw response 暴露。
6. datum/modifier/composite 任一不确定时 fail closed，Coverage 无 silent loss。
7. OpenAPI 生成类型包含 exact GD&T variant，不再是 opaque object。
8. current drawing workbench 的 headed UI coverage 与 API evidence 分开报告。
9. focused tests、integration、live ROI smoke、headed UI 和 export proof 均通过。
10. 独立 reviewer verdict 为 accept，且 old coarse path retirement 条件已记录。

## Open Decisions Before Implementation

- 首个 formal standards context 是 GB/ISO、ASME，还是 `unspecified + raw-preserving`？
- `▱` 是否作为输入 alias 接受，canonical 输出是否固定为 `⏥`？
- projected zone/tangent plane/free-state 等高级 modifier 是否进入后续 schema version？
- 历史 coarse GD&T 数据是只读保留、人工升级，还是有证据约束的 backfill？
- scanned frame detector 的首选实现和可接受 accuracy/latency gate 是什么？

这些决定会改变 schema 或 runtime 行为，必须在 future Heavy plan 中由用户明确批准，
不能由实现者自行扩大 scope。
