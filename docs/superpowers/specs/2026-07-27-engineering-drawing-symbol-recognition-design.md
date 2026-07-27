# Engineering Drawing Symbol Recognition Design

## Status

- Date: `2026-07-27`
- Status: `Approved semantic design`
- Selected scope: 当前失败 PDF 闭环
- Selected lane: `Heavy`
- Execution authorization owner: unique current plan; this design does not authorize execution
- Activation state: Task 0 complete at `994cbe4`; Option A clarification active

本文只定义能力、Owner、数据合同、失败边界和验收口径。它不切换当前
implementation plan，也不独立授权 production code、runtime config、contract
matrix 或 Harness 变更；执行授权和顺序只来自唯一 current plan。

## Context

质量人员在当前真实工程 PDF 的审核工作区中能看到大量尺寸文本，但图上的直径、
深度、沉孔、表面粗糙度和几何公差符号没有稳定进入候选检验项。结果不是单纯的
显示缺字：纯矢量符号在进入 Qwen 之前就没有成为可路由的 observation。

当前 first-PDF 的 source SHA-256 为：

```text
58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec
```

该 hash 已存在于 current P0 plan。本文不记录 PDF bytes、宿主机路径、项目 ID、
Provider credential 或完整 Provider response。

受影响的主体包括：

- 质量人员：候选列表缺少图纸上可见的检验要求，无法可信地完成审核与 freeze。
- 自动处理链：Coverage Ledger 只覆盖文本 observation，无法证明视觉符号没有被
  静默丢弃。
- 后续气泡和导出：它们只消费 reviewed items，不能补回上游未生成的符号候选。

现在必须处理，是因为该缺口已经在 current first-PDF 的真实处理结果中出现，并且
会直接破坏“图纸可见检验要求 → 审核项 → 气泡 → SIP”的完整性。不能用人工口头
说明、提高 Qwen 调用上限或导出后补项替代上游修复。

## Verified Current State

以下事实于 `2026-07-27` 从 current source、容器内 runtime 数据和受控页面渲染中
核对：

| Surface | Current fact | Consequence |
| --- | --- | --- |
| Page 1 inventory | 814 native chars、533 vector drawings、363 observations；全部 observation 为 native text，OCR 为 0 | 533 个 drawing 只参与页面分类，没有形成可路由视觉来源 |
| Page 2 inventory | 1213 native chars、986 vector drawings、533 observations；全部 observation 为 native text，OCR 为 0 | 纯矢量符号不在 candidate/coverage 输入集合中 |
| Qwen Advisor | 32 次调用，每页 16 次；3 次 promotion、29 次 `local_parse_failed` | 预算主要消耗在已有文本，无法发现没有文本 observation 的符号 |
| Coverage | 另有 135 个 ambiguous 文本 observation 未被 Advisor 复核 | 当前调用上限按文本阅读顺序截断，不能表达符号优先级 |
| Working copy | 276 items：249 linear、21 thread、2 diameter、2 radius、1 angle、1 weld | 图纸中可见的粗糙度、GD&T、沉孔等视觉要求没有形成相称的审核项 |
| UI | typed item 的 `normalized_text` 已存在于 backend payload，但 frontend `ReviewItem` 未声明或展示该字段 | 已补出的 `Φ` 仍可能只以缺符号的 `raw_text` 呈现 |

当前代码链路与上述 runtime 事实一致：

- `backend/app/pdf/inventory.py:107-178` 只从 `page.get_text("dict")` 构建
  `TextObservation`；`page.get_drawings()` 只在第 159 行计数。
- `backend/app/pdf/schemas.py:9-42` 只定义 `TextObservation` 和
  `PageInventory.observations`，没有 visual observation。
- `backend/app/processing/runtime_recognition.py:49-117` 仅在 `hybrid` 页面上对
  embedded image regions 做 OCR；`runtime_recognition.py:134-166` 不遍历 vector
  drawing。
- `backend/app/processing/automatic_result.py:144-231` 只遍历选中的文本
  observation 创建候选与 coverage。
- `backend/app/candidates/advisor.py:194-281` 只路由已有 candidate 或 ambiguous
  文本 observation，并按每页 16 个截断。
- `backend/app/candidates/advisor.py:594-683` 要求 ambiguous promotion 再通过
  `parse_annotation()`；复杂符号建议因此落到 `local_parse_failed`。
- `backend/app/candidates/parser.py:58-117` 只解析 linear、diameter、thread、
  radius 和 angle。
- `backend/app/review/service.py:113-121` 只从 raw result candidates 创建
  working-copy items。

结论：当前实现符合既有 Qwen plan，但该 plan 只实现了文本候选复核，没有实现
视觉符号发现。这是已验证的能力缺口，不是近期 UI 修改引入的回归。

## Root Cause

根因位于 candidate 生成之前：

```text
vector symbol
  └─ page.get_drawings()
       └─ only contributes vector_drawing_count
            └─ no observation ID / bbox / coverage entry
                 └─ no candidate route
                      └─ Qwen never sees the symbol
```

有些符号即使作为缺失或异常 glyph 附近的文本 crop 被 Qwen 看见，也会在第二个
边界失败：

```text
Qwen suggestion
  └─ frozen candidate-review/1 response
       └─ parse_annotation(normalized_text)
            └─ unsupported complex symbol
                 └─ local_parse_failed
```

因此只改 prompt、只扩 Unicode replacement、只提高 `MAX_CALLS_PER_PAGE` 或只改
frontend display 都不能闭环该问题。

## Goals

- 为 current first-PDF 中人工标注的视觉符号建立稳定、可定位的
  `VisualObservation`。
- 让 Qwen 只对有界局部 observation batch 提供受 schema 约束的符号类别建议。
- 由 candidate domain 的确定性 validator 提交 candidate、reference context、
  non-inspection 或 ambiguous disposition。
- 复用现有 `Candidate`、`CoarseCandidate`、composite 和 review contracts，不让
  Provider 成为业务语义 Owner。
- 每个疑似视觉 observation 都进入 Coverage Ledger，预算耗尽不得静默跳过。
- 在 UI 中同时保留图纸原文和规范化识别结果，让补出的符号可见。
- 以 current PDF 的 sealed live manifest 完成逐区域验收，同时用脱敏 fixture
  提供可重复测试。

## Non-Goals

- 不承诺完整 ISO、GB、ASME 或企业符号库。
- 不支持当前 PDF 中不存在的 countersink、视觉 weld symbol、完整 datum
  reference graph 或完整 GD&T 语义解释。
- 不把 standalone center mark、section label、dimension arrow、leader、hatch 或
  零件轮廓自动变成检验项；通过 local validator 的 `revision_marker` 初始状态固定为
  `non_inspection`，Provider、validator、automatic processing 或 frontend inference
  均不得自动为其创建 inspection item。既有 Quality Owner 显式
  `promote_source` / `ignore_source` 人工命令不在此禁令内。
- 不发现没有邻近 native line 的 standalone visual symbol；current source 的目标
  families 均有数值、datum letter 或 revision number 锚点。
- 不对纯扫描 PDF 建立正式支持；现有 `scanned = unsupported` routing 保持不变。
- 不让 Qwen 直接写 disposition、正式 item type、feature kind、数值、公差、
  inspection method、balloon 或 export。
- 不发送完整页面或完整 PDF 给 Vision Provider。
- 不修改已有 `AutomaticResult`、working copy、reviewed result 或 export。
- 不引入第二个 Vision service、shadow pipeline、fallback、feature flag 或通用
  detection framework。
- 不在本 spec turn 修改 `MAIN_CONTRACT_MATRIX.md`、P0 traceability、current plan、
  Harness 或 production code。

## Scope

### Current-PDF Positive Families

首版只覆盖 current source 中已经通过页面渲染观察到的下列视觉家族：

| Symbol family | Examples in current source | Expected business projection |
| --- | --- | --- |
| `diameter` | `Φ/∅/⌀` 与 18、20、22、40、100、202 等尺寸组合 | 现有 `diameter_dimension`；`feature_kind=unknown`；强制确认 |
| `depth` | 螺纹或直径后的深度符号与深度值 | 补入规范化 `深` 后必须通过现有 typed parser；强制确认 |
| `counterbore` | 沉孔符号与 `Φ + depth` 多行组合 | 现有 `composite`，保留规范化符号和有序 sub-requirements；强制确认 |
| `surface_roughness` | 表面纹理符号与 `3.2` | 现有 `CoarseCandidate(coarse_type="roughness")`；强制确认 |
| `gdt_parallelism` | `∥ 0.1 A` frame | 现有 `CoarseCandidate(coarse_type="geometric_tolerance")`；强制确认 |
| `gdt_perpendicularity` | `⊥ 0.1 A` frame | 现有 `CoarseCandidate(coarse_type="geometric_tolerance")`；强制确认 |
| `gdt_flatness` | flatness frame | 现有 `CoarseCandidate(coarse_type="geometric_tolerance")`；强制确认 |
| `datum_reference` | boxed `A/B/C` 与 datum pointer | `reference_context`，不单独生成检验项 |
| `revision_marker` | closed triangle 与内部 revision token | 初始 `non_inspection`、`candidate_id=null`；不自动生成检验项；强制确认 |

视觉 weld symbol 不在 current source 中。技术要求中的“焊接”文本继续走现有
technical-requirement path，不据此扩大视觉检测范围。

以上恰好是九个 evaluation-positive recognition families。这里的
evaluation-positive 只表示 live evaluation 要求识别命中，不表示生成 inspection
item。`revision_marker` region 只有在下文既有 closed-triangle + inner revision-token
validator 全部通过时才属于第九个 positive family；颜色不是 classifier。一个通过
validator 的 `revision_marker` label 不得同时标为 `frozen_negative`。

### Frozen Negative Families

live manifest 和脱敏 fixture 都必须标注以下恰好九个负样本家族：

| `negative_family` | Frozen negative scope |
| --- | --- |
| `part_or_hole_geometry` | 零件外轮廓、孔轮廓、圆弧和长直线 |
| `hatch_center_or_cross` | 剖面线、中心线、center mark 和十字线 |
| `dimension_leader_or_section_line` | dimension arrow、leader、extension line 和 section cutting line |
| `view_or_section_label` | `A-A/B-B/C-C/IV/V` 等视图或剖面标签 |
| `revision_table_or_invalid_marker` | revision table grid/cells，以及未通过 closed-triangle + inner revision-token validator 的 triangle-like geometry |
| `datum_like_letter_or_table_cell` | datum-like 普通字母或表格单元格 |
| `watermark_logo_title_or_signoff` | watermark、logo、title block 和签字栏 |
| `isometric_hole_slot_or_edge` | isometric view 中的普通孔、槽和板边 |
| `ordinary_text_number_material_or_requirement` | 普通文本、数字、材料信息和技术要求正文 |

`revision_table_or_invalid_marker` 不包含通过 validator 的 `revision_marker`；颜色同样
不能把 region 移入或移出该 negative family。

负样本可以进入确定性 `non_inspection`，也可以在证据不足时保持可复查
`ambiguous`；它们不得形成 candidate。

## Approaches Considered

### Approach A: Extend The Text-Anchored Advisor

继续从已有文本 observation 扩大 crop，并让 Qwen 补 `Φ`、深度和粗糙度符号。

优点：

- 改动面最小；
- 可复用现有 `candidate-review/1` 和 cache。

缺点：

- 没有文本锚点的矢量符号仍然完全不可见；
- current 16-call budget 仍会先被 watermark、标题栏和普通 ambiguous 文本占用；
- counterbore、GD&T frame 等仍会受 typed parser 限制。

Verdict: reject。它只能修部分 diameter 显示，不能满足 current-PDF
逐区域 coverage。

### Approach B: Full-Page Or Fixed-Tile Vision Detection

把整页或固定网格送给 Qwen，让模型直接返回所有符号和坐标。

优点：

- 理论上不依赖 native text 或 vector extraction；
- 对 standalone symbol 的召回路径最直接。

缺点：

- 会扩大图纸数据暴露面；
- 大图缩放后的小符号定位不稳定；
- Provider bbox、漏检和 disposition 容易成为事实 Owner；
- 固定 tile 容易切断 frame、symbol 与 value 的关系；
- 成本和调用量难以与当前 contract 对齐。

Verdict: reject。它不满足 local-crop、deterministic-owner 和隐私边界。

### Approach C: Deterministic Visual Observations With Bounded Vision

先从 PDF 的 native-line-adjacent vector path facts 生成不带业务含义的
`VisualObservation`，再把多个 observation 组成有界局部 batch 交给 Qwen。
Provider 只返回 allowlisted symbol kind 和位置；本地 validator 决定投影。

优点：

- 能覆盖纯矢量符号；
- observation ID、bbox、source relation 和 coverage 可稳定复现；
- Provider 不决定 disposition 或正式 item schema；
- 多 observation 共用一个局部 crop，能把调用总预算保持在每页 16 次；
- 可用负样本和本地 validator 抑制零件几何误报。

缺点：

- 需要新增 visual observation contract 和 native-line-adjacent path-item
  proposal builder；
- 需要更新 coverage、source review 和 live acceptance；
- 当前 `CAND-004/P0-REC-005` 必须先完成正式 amendment。

Verdict: selected。

## Selected Architecture

```text
PDF bytes
  │
  ├─ native text extraction ───────────────> TextObservation
  │
  └─ deterministic visual proposals ──────> VisualObservation
                                                   │
deterministic text candidate snapshot              │
  │                                                │
  └────────────── CandidateAdvisor unified routing ┘
                         │
                         ├─ bounded local batch crop
                         ├─ Qwen schema-only suggestion
                         └─ deterministic local validation
                                      │
                         ┌────────────┼─────────────┐
                         │            │             │
                     candidate  reference/non   ambiguous
                                  inspection
                         └────────────┼─────────────┘
                                  Coverage Ledger
                                        │
                                immutable raw result
                                        │
                                  human review
```

### Single Owner

`backend/app/candidates/advisor.py::CandidateAdvisor` 继续作为唯一 Vision
integration Owner。它新增 `visual_symbol` route kind，但不新建第二个 Advisor、
第二个 automatic raw candidate writer 或并行 result path。既有 Review aggregate
继续只拥有 Quality Owner 显式 working-copy commands。

各角色固定如下：

| Component | Role | Allowed | Forbidden |
| --- | --- | --- | --- |
| PDF visual proposal builder | `Signal Provider` | 生成稳定 region fact、bbox、geometry hash 和邻近 text refs | 决定 symbol kind、candidate type 或 disposition |
| Qwen adapter | `Advisor` | 对局部 crop 输出冻结 schema 的 allowlisted symbol suggestion | 写正式 candidate、coverage、review 或 business field |
| Local symbol validator | `Validator` | 校验 schema、bbox、source association 和允许的 projection | 猜测缺失文本、孔/轴语义或标准规则 |
| `CandidateAdvisor` | `Owner` | 在 validator 通过后执行唯一 automatic raw candidate/coverage write | 绕过 validator 或保留第二个 visual path |
| Review aggregate | `Manual Command Owner` | 在 working copy 中执行 Quality Owner 显式 `promote_source` / `ignore_source` | 自动调用命令、模拟人工 override 或成为第二个 Vision Owner |
| Coverage service | `Veto Gate` | 阻断缺 source、coordinates、disposition 或预算溢出的结果 | 创建替代 candidate |
| Frontend | `Executor` | 展示 Owner 已提交的 source、normalized result 和 confirmation | 重新识别符号或生成正式语义 |

### Old Path Action

- `candidate_snapshot_from_inventory()` 的 deterministic text seeds：
  `preserve`，仍是 canonical text path。
- `CandidateAdvisor` 的现有 `text_review` route：`preserve`，折入同一个 unified
  route scheduler。
- visual symbol path：new capability inside the existing Owner，不建立
  bridge、shadow、dual-write、fallback 或 feature flag。
- current 每页前 16 个文本 route 的静默截断：`replace` 为统一预算调度。visual
  observation 不允许被静默截断；普通 text review 超出剩余预算时继续保持当前
  “原样保留、不写假 provenance”语义。

## Visual Observation Contract

在 `backend/app/pdf/schemas.py` 增加独立类型，不把视觉区域伪装成
`TextObservation`：

```python
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

`PageInventory` 新增：

```python
visual_observations: tuple[VisualObservation, ...] = ()
```

约束：

1. `bbox_pdf` 使用现有未旋转 CropBox 左上原点，并复用现有 clip 和 transform。
2. `observation_id` 由
   `visual-observation/1 + source_sha256 + page_index + proposal_kind +
   rounded_bbox + geometry_sha256 + sorted associated text IDs`
   计算 SHA-256 前 24 位。
3. bbox 坐标只为 ID 计算舍入到 `0.001 PDF point`；持久化值保留现有 float 精度。
4. 同一 PDF bytes、`proposal_rule_version="visual-observation/1"`、PyMuPDF version
   和 canonicalization parameters 重复执行必须产生完全相同的 observation
   顺序、ID 和 bbox。
5. `geometry_sha256` 来自规范化 vector path items，不包含 absolute path、
   object repr、xref-only identity 或运行时随机值。
6. visual observation 只表达“这里有需要复核的局部视觉结构”，不携带
   `symbol_kind`、confidence、candidate type 或 disposition。

## Deterministic Proposal Rules

vector geometry 的规范化固定如下：

1. 每个 `page.get_drawings()` item 先转换到现有未旋转 CropBox 坐标。
2. path item 按返回顺序序列化为
   `opcode + ordered point/rect/quad coordinates`；坐标仅在 hash 输入中量化到
   `0.001 PDF point`。
3. drawing 的 `width/dashes/lineCap/lineJoin/color/fill` 一并进入 canonical JSON；
   缺失 key 写 `null`。finite numeric 先用
   `Decimal(str(value)).quantize(Decimal("0.001"), ROUND_HALF_EVEN)` 转成无
   negative-zero 的 decimal string；color/fill 只允许 `null` 或 1～4 个同样
   规范化的 numeric components；`dashes` 只允许 string 并折叠 ASCII whitespace；
   lineCap/lineJoin 只允许 integer 或 integer array。JSON 使用 UTF-8、sorted
   keys 和无空白 separators。
4. path items 按
   `(bbox.y0, bbox.x0, bbox.y1, bbox.x1, canonical_path_bytes)` 排序。
5. `geometry_sha256` 是一个 native line context 中入选 path-item bytes 按上述
   顺序连接后的 SHA-256。
6. 遇到 PyMuPDF 未知 path opcode、NaN/Inf coordinate 或无法规范化的 style 时，
   当前页 visual proposal blocking，不允许跳过该 primitive 后继续。

proposal builder 按以下顺序工作：

1. 遍历 `PageInventory.observations` 中所有
   `source_type="native" && observation_level="line" && raw_text.strip() != ""`
   的 observations；不先按文字内容、parser 结果或页面区域过滤。span 只选择
   `parent_region_id == line.observation_id` 的 native spans，按 observation ID
   排序后作为 source relation，不单独产生 context。
2. 对 line bbox `L` 和 path-item bbox `P` 定义
   `gap_x=max(0, L.x0-P.x1, P.x0-L.x1)`、
   `gap_y=max(0, L.y0-P.y1, P.y0-L.y1)`。只有
   `gap_x <= 12 && gap_y <= 12` 的 individual path items 才可入选；
   path-item bbox 的 width 和 height 均不得超过 `96 PDF points`。
3. line bbox 与入选 path-item bboxes 的 union 面积不得超过页面面积的 `1%`；
   没有入选 path item 或超限的 line 不生成 visual observation。
4. 每个合格 native line 恰好形成一个 `text_adjacent_vector_context`，associated
   IDs 包含该 line 和其 selected spans。
5. 一个 path item 可以同时属于两个相邻 line contexts；proposal builder 不凭距离
   猜唯一文字 Owner。完全相同的 geometry digest 去重；IoU 大于等于 `0.8` 且
   associated text IDs 相同的 proposal 只保留稳定排序第一项。跨 context 的
   Provider detection 在下述 page-coordinate dedupe 中收敛。
6. 排序键固定为
   `(page_index, bbox.y0, bbox.x0, proposal_kind, observation_id)`。

不生成无邻近 native line 的独立 vector context。current source 中本 spec 的全部
positive families 都带数值、datum letter 或 revision number；standalone visual
symbol 需要未来独立 spec。

只读 exploratory dry-run 已用 individual path-item、`1%` context 和 `7.5%`
batch thresholds 核对 current source。结果为：

| Page | Native lines | Eligible contexts | 7.5% stable batches |
| --- | ---: | ---: | ---: |
| 0 | 174 | 84 | 10 |
| 1 | 265 | 182 | 13 |

同一 dry-run 证明按 `page.get_drawings()` 对 drawing/component 做全局连通聚类会让
两页都退化为一个整页 component，因此该旧思路明确 rejected，不得在 implementation
中恢复。

表中的 10/13 是 proposal 可行性证据，不是冻结的 acceptance count；该 dry-run
早于本 spec 固定 300 DPI 和 exact padding。implementation plan 的首个 PDF unit
RED 必须按本文最终算法重算 batch count，并证明两页各自 `V <= 16`；否则
production GREEN 仍被 budget gate 阻断。

这些阈值是首版 current-PDF contract，不是用户配置。后续修改必须以新的负样本或
漏检证据进入 amendment，不能为单一坐标写 exact-input 特判。

## Vision Request Contract

多个相邻 visual observations 可以共享一个 Provider crop，但每个 observation
保留独立 ID。batch 规则：

- 对成员 bbox union `U`，padding
  `p=min(24, max(6, ceil(0.10 * max(U.width, U.height)))) PDF points`；
  crop 是 `U` 四边各扩 `p` 后 clip 到现有未旋转 CropBox；
- crop 面积不得超过页面面积的 `7.5%`；
- crop 固定以 `300 DPI`（scale `300/72`）render；packing 时用
  `ceil(crop.width * 300/72)` 和 `ceil(crop.height * 300/72)` 预先计算，
  两边均不得超过 `1536 pixels`；
- 超限时按稳定 observation 顺序拆分，不允许降低分辨率吞掉小符号；
- 每个 crop 最多 32 个 visual observations；
- visual batch 优先于普通 text-review route；
- text review 与 visual batch 共用每页 16 次 Provider call 总预算。

统一 scheduler 使用以下精确算法：

1. visual observations 按固定优先级和既有稳定排序键排列：
   - priority 0：关联 parser-failed numeric/thread text；
   - priority 1：关联已有 `requires_confirmation` candidate；
   - priority 2：其余 `text_adjacent_vector_context`。
   同一 priority 内使用
   `(page_index, bbox.y0, bbox.x0, proposal_kind, observation_id)`。
2. 按该顺序执行 stable first-fit packing。一个 observation 只加入第一个同时满足
   7.5% page area、1536 pixels、32 observations 上限的现有 batch；都不满足时创建
   新 batch。单个 observation 在上述 padding 后仍超限时立即返回
   `visual_crop_oversize`，不得缩图或跳过。
3. 设 visual batch 数为 `V`。`V > 16` 时立即
   `symbol_route_budget_exhausted`；否则先执行全部 `V` 个 visual calls。
4. 剩余 `16 - V` 个 slots 按现有 text route sort key
   `(page_index, bbox.y0, bbox.x0, source_ids)` 选择。
5. text routes 超额时保持现有 candidate/coverage 不变且不写 Advisor provenance；
   visual observation 不存在未调度状态。

Provider 输出使用新的 `visual-symbol-review/1` JSON Schema：

```json
{
  "schema_version": "visual-symbol-review/1",
  "detections": [
    {
      "visual_observation_id": "0123456789abcdef01234567",
      "symbol_kind": "diameter",
      "bbox_normalized": [0.1, 0.2, 0.3, 0.4],
      "associated_text_observation_ids": ["native-line-id"],
      "requires_confirmation": true
    }
  ]
}
```

冻结约束：

- root 和 detection 都是 `additionalProperties=false`；
- `detections` 最多 128 项；
- `visual_observation_id` 必须来自当前 batch；同一 ID 最多 4 个 detections；
- `(visual_observation_id, symbol_kind, rounded bbox)` 必须唯一；
- `bbox_normalized` 四个值必须在 `[0, 1]`，并满足 `x0 < x1`、`y0 < y1`；
- associated text IDs 必须是 prompt 中随 crop 提供的 allowlist 子集；
- `requires_confirmation` 必须为 `true`；
- `symbol_kind` 只允许：
  - `diameter`
  - `depth`
  - `counterbore`
  - `surface_roughness`
  - `gdt_parallelism`
  - `gdt_perpendicularity`
  - `gdt_flatness`
  - `datum_reference`
  - `revision_marker`
- Provider 不返回自由文本 transcription、item type、disposition、confidence、
  nominal、tolerance 或 feature kind。

同一 visual observation 的多个 detections 由本地 Owner 按 bbox reading order
组合，支持 diameter + depth 和 counterbore + diameter + depth。组合后仍只允许
一个 primary disposition 和至多一个 candidate。

某个 visual observation 没有 detection 时，本地 Owner 写
`ambiguous + requires_confirmation=true + visual_no_detection`。该 entry 不进
active item list，但必须保留在 source review，可由人工 promote 或 ignore；因此
Provider 的“没看到”不是不可逆排除，也不等同于 `non_inspection`。current live
manifest 中任一 positive label 落入该状态都直接 fail。

## Local Validation And Projection

validator 先校验 schema、batch identity、bbox、source refs、重复 detection 和
crop containment，再按固定映射投影：

| `symbol_kind` | Local rule | Output |
| --- | --- | --- |
| `diameter` | 将 canonical `Φ` 只加入 `normalized_text`，并用 associated native text 通过 `parse_annotation()` | `diameter_dimension`；保留原 `raw_text`；`feature_kind=unknown`；confirmation |
| `depth` | 将 canonical `深` 与 associated typed annotation 组合，必须通过现有 parser 且保持原 item type | 更新已有 typed candidate 或生成 typed candidate；confirmation |
| `counterbore` | canonical `⌴`、diameter 和 depth 必须都有当前 crop 的 source evidence；数值子要求必须通过现有 parser | 现有 `composite`；有序 sub-requirements；confirmation；不新增正式 counterbore enum |
| `surface_roughness` | 必须关联当前 crop 中的 roughness value text | 四字段 `CoarseCandidate`，`coarse_type="roughness"` |
| `gdt_parallelism` | canonical `∥`，frame value/datum 只取 associated source text | 四字段 `CoarseCandidate`，`coarse_type="geometric_tolerance"` |
| `gdt_perpendicularity` | canonical `⊥`，其余同上 | 四字段 `CoarseCandidate`，`coarse_type="geometric_tolerance"` |
| `gdt_flatness` | canonical `⏥`，其余同上 | 四字段 `CoarseCandidate`，`coarse_type="geometric_tolerance"` |
| `datum_reference` | 必须关联 boxed datum letter；不提交 inspection item | `reference_context`，`requires_confirmation=false` |
| `revision_marker` | 必须满足下述 closed-triangle + inner revision token validator | 初始 `non_inspection`、`candidate_id=null`、`requires_confirmation=true`；可由 Quality Owner 显式人工恢复 |

Provider 的 detection 仍一律提交 `requires_confirmation=true`。只有本地 Owner 完成
boxed-letter + datum geometry 校验并投影为非 item 的 `reference_context` 时，才按
上表把 coverage confirmation 关闭；candidate projection 不允许 downgrade。

qualifying `revision_marker` 的 automatic Owner decision 精确为
`disposition="non_inspection"`、`candidate_id=null`、
`requires_confirmation=true`。Provider、local validator、automatic processing 和
frontend inference 都不能调用、伪造或模拟人工 override；只有 Quality Owner 显式
提交现有 `promote_source` 命令并提供全部既有必填 manual fields 后，working copy
才可创建一个 manual item。显式 `ignore_source` 只确认 non-inspection。

payload 构造固定如下：

- associated text 按
  `(page_index, direction_angle_degrees % 360, bbox.y0, bbox.x0,
  observation_id)` 排序。`BBox` 和坐标转换分别复用
  `app.pdf.coordinates.BBox` 与
  `PageTransform.normalize_bbox()/clip_bbox()`，不得另建坐标约定。
- typed projection 的 `raw_text` 是上述 native `raw_text` 以换行连接的原串；
  `normalized_text` 才加入 canonical visual token。
- 单行 depth：如果 primary、depth symbol 和 depth value 属于同一个 native line，
  组合后的 normalized string 必须通过 `parse_annotation()`，并使用 parser 的
  typed payload。
- 多行 depth：复用 `grouping.py` 的 composite shape。order 0 是现有 primary
  requirement；order 1 是
  `{"order": 1, "kind": "depth",
  "raw_text": depth_observation.raw_text,
  "value": Decimal(depth_value)}`。
- counterbore：使用同一 composite shape；order 0 是
  `diameter_dimension` primary，order 1 是 depth modifier。
  `normalized_text` 的第一行只在本地加 canonical `⌴`，不增加
  `counterbore` field、sub-requirement kind 或 public enum。
- roughness CoarseCandidate 精确为
  `raw_text=ordered_source_text`、`coordinates=source_bbox_union`、
  `coarse_type="roughness"`、`requires_confirmation=true`。UI 只根据该
  Owner field 渲染粗糙度图形标识。associated line 必须恰有一个可由
  `Decimal` 解析的 ASCII decimal token；0 个或 2 个以上 distinct values 均为
  `visual_local_parse_failed`，不从图形估值。
- GD&T CoarseCandidate 使用相同四字段；`raw_text` 是
  `canonical_symbol + " " + ordered_source_text`，
  `coarse_type="geometric_tolerance"`。associated line 必须恰有一个 decimal
  tolerance token；其余 datum tokens 只接受单个 ASCII uppercase letter，并按
  source order 保留。0 个或 2 个以上 distinct tolerance values 均保持 ambiguous。
- revision marker 的 local validator 只接受一个由 3 条 straight segments
  组成的 closed path：首尾距离 `<=0.5 PDF point`，bbox width/height 各在
  `[4,24] PDF points`，且恰有一个匹配 `[A-Z0-9]{1,3}` 的 associated native
  token，其 bbox center 位于 triangle 内或距 triangle bbox `<=2 PDF points`。
  只有全部条件通过时才是 `revision_marker`，automatic projection 只能提交上述
  initial `non_inspection` decision，不能创建 inspection item；不满足任一条件时
  保持 ambiguous，不根据颜色或模型 confidence 判定。

同一 visual observation 的 primary projection 只接受以下 detection-kind sets：

- `{diameter}`、`{depth}`、`{diameter, depth}`；
- `{counterbore, diameter, depth}`；
- `{surface_roughness}`；
- `{gdt_parallelism}`、`{gdt_perpendicularity}`、`{gdt_flatness}`；
- `{datum_reference}`；
- `{revision_marker}`。

同 kind 多个不重叠 detections、缺少 counterbore 的 diameter/depth、混合两个
inspection families 或任何未列集合，都保持
`ambiguous + visual_projection_conflict`。组合内 primary candidate 按上表映射：
diameter/depth 使用 typed/composite path，counterbore 三件套使用 composite，
roughness/GD&T 使用 coarse；datum/revision 不产生 candidate。

若已有 candidate 已含 depth/thread_depth：

- 新视觉值与现有 Decimal 相等时，只追加 visual source、coordinates union 和
  confirmation；
- 新视觉值不同、出现两个 depth values、或 visual symbol 关联到两个 primary
  candidates 时，保持原 candidate bytes 不变，并把 visual observation 置为
  `ambiguous` + `visual_projection_conflict`；
- 不允许 last-write-wins、取最大值、取最近值或由 Provider 选择。

所有 candidate projection 都必须：

- `requires_confirmation=true`；
- `coordinates` 仍是单个四元组，精确取 symbol bbox 与全部参与 text bboxes 的
  union：
  `(min(x0), min(y0), max(x1), max(y1))`；不改为 bbox collection；
- `source_location_ids` 同时包含 visual observation ID 和 text observation IDs；
- 保留原 `raw_text`，把补出的 canonical symbol 放在 `normalized_text`；
- 不因 `Φ` 猜测 `hole`，继续使用 `feature_kind=unknown`；
- 不从图形常识补造单位、数量、深度、through、datum 或 tolerance；
- 不把 Provider 的 symbol kind 直接当 confirmed business field。

缺关联文本、parser 失败、bbox 越界、重复 ID、未知类型、confirmation downgrade 或
数值冲突时，不创建 candidate。对应 visual observation 保持 `ambiguous`，并写入
脱敏 rejection code：

- `visual_schema_invalid`
- `visual_bbox_invalid`
- `visual_source_mismatch`
- `visual_duplicate_detection`
- `visual_local_parse_failed`
- `visual_projection_conflict`

不得保存或显示 Provider explanation 作为 rejection reason。

## Candidate Identity And Deduplication

- Provider bbox 先从 batch-normalized 坐标反算到 page PDF coordinates。对同页、
  同 `symbol_kind` 且
  `intersection_area / min(area_a, area_b) >= 0.8` 的 detections 做 page-level
  dedupe；按 `(page_index, bbox.y0, bbox.x0, visual_observation_id)` 保留第一项，
  并把其余 visual/text source IDs 合入 keeper。该规则跨 batch 相同，不依赖
  Provider response order。
- 如果 visual detection 关联到一个已有 text candidate，更新该 candidate 的
  `normalized_text`、coordinates、confirmation 和 source union，保留原
  `candidate_id`，不得创建第二项。
- 如果没有已有 candidate，candidate ID 由
  `visual-candidate/1 + sorted visual/text source IDs + projection type`
  计算。
- 只在 source relation 和 bbox 指向同一标注时合并；不得因为两个视图文字相同而
  自动合并。
- counterbore composite 的 sub-requirement 顺序按页面 reading order 固定；
  quantity 不累加。
- visual candidate 进入现有 duplicate Advisor 后，跨视图仍只能产生人工确认
  suggestion。
- local Owner 在每条 visual coverage entry 的 `advisor_review` 中只保留
  `route="visual_symbol"`、`schema_version`、排序后的 `symbol_kinds` 和
  `rejection_code`；不保留 Provider 原文。live eval 用该 `symbol_kinds` 做 exact
  group matching。

## Coverage Contract

`VisualObservation.observation_id` 复用 Coverage Ledger 的 observation identity
语义，不把 drawing count 当 expected coverage。

每个 visual observation 恰有一个 primary disposition：

- `candidate`
- `reference_context`
- `non_inspection`
- `ambiguous`

每条 entry 必须含 observation ID、source location、PDF coordinates、
`requires_confirmation` 和 disposition。candidate entry 必须有 candidate ID。
缺任一字段、一个 observation 有多个 primary disposition、visual batch 未执行或
visual budget 溢出都属于 blocking。

普通 text-review routes 超出剩余 Provider budget 时可以保持原 snapshot；visual
observations 不允许这样处理。如果 visual batching 在单页仍需要超过 16 次调用，
processing 必须以 `symbol_route_budget_exhausted` fail closed，不能截断后形成
formal success。

source review 必须保留并区分两种 pending source：

- `ambiguous + visual_no_detection`：没有 detection，初始无 item；Quality Owner 可用
  既有 `promote_source` 补齐 manual fields 后创建 manual item，或用
  `ignore_source` 解析为 non-inspection；
- qualifying `revision_marker`：初始为
  `non_inspection + candidate_id=null + requires_confirmation=true`，同样只允许
  Quality Owner 通过显式 `promote_source` 做人工 override，或用显式
  `ignore_source` 确认 non-inspection。

低置信度、Provider、validator、automatic processing 和 frontend inference 都不能
自动触发任一 command 或改变上述初始 disposition。

## UI Contract

本能力只要求最小展示变更：

1. `frontend/src/api/types.ts::ReviewItem` 增加可选
   `normalized_text?: string`，与 backend 已有 payload 对齐。
2. 当 `normalized_text` 与 `raw_text` 不同时：
   - `图纸原文` 继续显示并编辑 `raw_text`；
   - `解析结果` 显示只读“识别结果”，包含 canonical symbol；
   - 不用 normalized value 覆盖 source field。
3. coarse candidate 继续只暴露
   `raw_text/coordinates/coarse_type/requires_confirmation`。
   visual coarse candidate 的 `raw_text` 在 UI 中标为“图形转写”，不得标成 native
   OCR 原文；roughness 图形标识只由 Owner 已提交的 `coarse_type` 驱动。
4. `ambiguous + visual_no_detection` 显示“图形符号待确认”；qualifying
   `revision_marker` 显示“修订标记（非检验）待确认”。两者都显示 page、bbox 和
   局部 preview，但不显示 raw Provider response。
5. reference context 不进入 active inspection item list；qualifying
   `revision_marker` 的 initial non-inspection state 也不进入，只有后续 Quality
   Owner 显式 `promote_source` 才能创建 manual item。
6. 前端不得根据 glyph、CSS icon 或字符串重新决定 item type。
7. `projects/router.py::_project_pages()` 必须把 `visual_observations` 加入现有 source
   lookup，`raw_text` 固定投影为“图形符号待确认”；不得创建第二个 workbench
   endpoint。
8. 两种 pending visual source 继续复用现有两个 Quality Owner commands：
   - `promote_source`：人工填写 non-blank `raw_text`、现有 `CandidateType`、scope、
     balloon flag 和 page；成功后才把该 source 变为 candidate/manual item；
   - `ignore_source`：成功后 disposition 变为 non-inspection、
     `requires_confirmation=false`。
   对 qualifying `revision_marker`，promote 是明确的人工作业 override，不改变 live
   evaluation 的 initial Owner expectation。前端只能提交用户触发的命令，不能根据
   symbol、copy、CSS 或模型输出自行调用；不新增 visual-only mutation API。

该 UI delta 必须与
`2026-07-27-inspection-item-information-hierarchy-design.md` 的“图纸原文 /
解析结果”分组一致，不恢复重复标题或第二套详情层级。

## Error Handling

| Failure | Required behavior |
| --- | --- |
| Visual proposal cannot produce stable geometry | processing error；不调用 Provider |
| Provider unavailable or request fails | 使用现有 blocking Advisor failure policy；不退回 text-only formal success |
| Provider root response violates JSON Schema | blocking Advisor failure；不产生本 batch dispositions 或 raw result |
| Valid response 中某个 detection 未通过 local projection | affected observation 为 `ambiguous`，保存脱敏 rejection；原 candidate bytes 不变 |
| Crop or bbox transform invalid | blocking if source coordinates are missing；不得猜坐标 |
| One detection conflicts with existing candidate | 保留原 candidate；visual observation 为 `ambiguous` |
| One padded observation exceeds crop limits | `visual_crop_oversize`；项目不得 ready-for-edit |
| Visual budget exceeds 16 calls/page | `symbol_route_budget_exhausted`；项目不得 ready-for-edit |
| Ordinary text-review budget exhausted | 保持当前 unreviewed text object，不写假 provenance |
| Cache bytes/hash、schema 或 audit-ref mismatch | 保留 bytes 供诊断并按现有 blocking Advisor failure policy 失败；不得删除后静默重调 |
| User rejects a visual candidate | 现有 review command 保存操作记录和 source lineage |
| Unresolved visual ambiguity at freeze | freeze/confirm blocker；不得通过 warning 转 formal success |

state/error contract 固定如下：

- `build_automatic_result()` 只有在 visual scheduling、Provider calls、local
  validation 和 coverage 全部完成后，才能执行当前
  `processing → ready_for_edit` transition。
- Provider call、root schema 或 cache failure 使用现有
  `code="vision_provider_call_failed"`、`stage="candidate_advisor"`、
  `cause_category="transient_provider_failure"`，并转为 `processing_failed`。
- `symbol_route_budget_exhausted` 使用同名 code、
  `stage="candidate_advisor"`、`cause_category="processing_defect"`，并转为
  `processing_failed`。
- `visual_crop_oversize` 使用同名 code、`stage="candidate_advisor"`、
  `cause_category="processing_defect"`，并转为 `processing_failed`。
- coverage 缺失/冲突继续使用 `code="coverage_blocking"`、
  `stage="coverage"`，并转为 `processing_failed`。
- 上述 failure 都不得创建 `AutomaticResult` 或 working copy；成功 logical job 已有
  result ref 时继续由现有 idempotency winner 返回，不得被迟到 failure 覆盖。

## Privacy, Security And Cost

- Provider 只接收 bounded local crop、当前 batch IDs、allowlisted nearby text 和
  frozen schema。
- 不发送完整 PDF、完整页面、宿主机路径、project ID、operator ID、credential、
  Authorization header 或数据库 identity。
- crop 和 validated response 只通过受控 `LocalFileStorage` resource ref 保存；
  DB/API/log 只保存 hash、版本、request ID、duration、usage、rejection code 和
  resource refs。
- raw SDK body、Provider explanation 和完整 base64 不进入 DB、API、log、receipt
  或 Git。
- cache key 必须包含 source hash、visual observation IDs、crop hash、model、
  prompt version、schema version、adapter version、
  `proposal_rule_version="visual-observation/1"` 和 PyMuPDF version。
- 同一 logical task replay 不增加外部调用；同一 verified crop cache hit 不重复
  计费。
- text review 与 visual review 共用每页最多 16 次调用，不通过简单提高 cap 解决。

## Reprocessing And Immutability

- 已有 `AutomaticResult`、working copy 和 reviewed result 不原地补符号。
- current source 必须通过新 project upload 或经另行批准的 versioned reprocess
  logical task 生成新 raw result。
- 同一 `logical_task_key` 重投继续返回同一成功 result，不在旧 result 上追加
  candidates。
- 新结果继续使用现有 Candidate/CoarseCandidate/composite payload；本 spec
  不新增 public `CandidateType` 或 `CoarseType` enum。
- implementation 必须证明旧 text-only raw result 仍可创建 working copy、审核和
  导出。

## Contract Amendments Required Before Implementation

本能力会改变稳定 internal schema 和 Vision routing scope，因此必须在 implementation
plan 开始前完成以下正式 amendment：

| Contract | Required delta |
| --- | --- |
| `PDF-007` | 将稳定 visual observation ID/bbox/source relation 从 `P0-partial` 落到 current P0 enforcement |
| `CAND-001` | 明确 recall-first seed 可以消费经验证的 visual observation，不等同于 Provider 直接造 candidate |
| `CAND-004` | 从“局部 candidate crop”扩展为“局部 candidate 或 suspicious visual-observation crop”；Provider 仍只是 Advisor |
| `CAND-005` | expected coverage 集合加入 visual observation IDs；预算截断为 blocking |
| `CAND-006` | ambiguous visual source 必须可定位、复查、promote 或 ignore |
| `ITEM-002/003` | 明确 raw source text 与 visual-assisted normalized text 分离；`Φ` 仍不推断 hole |
| `P0-REC-005` | 拆分现有 text-candidate review 与 visual-symbol review 的 Provider contract selector |
| `P0-REC-009/010` | 增加 visual observation coverage 和 source-review selector |

amendment 必须在同一个 approved implementation plan 中记录 delta、Owner、旧路径
动作、allowed paths、RED tests、rollback 和 live selector。不得只修改 generated
Harness mirror；Markdown Owner 必须先更新。

## Evaluation Fixtures

### Sanitized Fixture

仓库新增人工构造、无真实图纸内容的两页 vector fixture，固定包含：

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

fixture 必须以 vector paths 与 native text 组合生成，不能直接把 expected candidates
写入 result。每个 positive/negative bbox 均由独立 manifest 指定；12 个 frozen
negative regions 必须共同覆盖上述九个 `negative_family` enum values，且每个家族
至少一个 region。

fixture tooling 固定为
`backend/tests/helpers/symbol_fixture.py::build_symbol_fixture(tmp_path)`：

- 使用 PyMuPDF drawing primitives 和 `insert_text()` 在 test temp directory
  生成 PDF，不提交 binary PDF；
- target symbol paths、native text 和 negative geometry 使用不同 helper
  functions，recognition production code 不 import test helper；
- helper 返回 `pdf_path` 和独立 eval manifest；manifest 只在 pipeline result
  生成后比较，不能注入 proposal、prompt 或 fake Provider decision；
- 输入 identity 固定为 helper file SHA-256、`symbol-fixture/1` generator version
  和 PyMuPDF version；相同 input identity 重复生成的 PDF SHA-256、page boxes
  和 manifest 必须一致；
- Provider contract/unit tests使用冻结 JSON fake，fixture E2E 使用 canonical
  runtime seam 注入 fake Provider，`external_calls=0`。

### Sealed Live Manifest

current source 的人工标注 manifest 只进入
`.agent/harness/runs/<run-id>/artifacts/`，不提交 PDF bytes、宿主机路径或 screenshot。
schema 固定为：

```typescript
type VisualSymbolEvalManifest = {
  schema_version: "visual-symbol-eval/1";
  source_sha256:
    "58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec";
  annotation_owner_role: "quality_owner";
  annotation_status: "approved";
  pages: Array<{
    page_index: number;
    labels: Array<{
      label_id: string;
      bbox_pdf: [number, number, number, number];
      symbol_kinds: Array<
        | "diameter"
        | "depth"
        | "counterbore"
        | "surface_roughness"
        | "gdt_parallelism"
        | "gdt_perpendicularity"
        | "gdt_flatness"
        | "datum_reference"
        | "revision_marker"
        | "frozen_negative"
      >;
      negative_family?:
        | "part_or_hole_geometry"
        | "hatch_center_or_cross"
        | "dimension_leader_or_section_line"
        | "view_or_section_label"
        | "revision_table_or_invalid_marker"
        | "datum_like_letter_or_table_cell"
        | "watermark_logo_title_or_signoff"
        | "isometric_hole_slot_or_edge"
        | "ordinary_text_number_material_or_requirement";
      expected_disposition:
        | "candidate"
        | "reference_context"
        | "non_inspection"
        | "ambiguous";
      expected_projection:
        | "diameter_dimension"
        | "thread"
        | "composite"
        | "roughness"
        | "geometric_tolerance"
        | null;
    }>;
  }>;
};
```

manifest schema 在 root、page 和 label 各层都使用
`additionalProperties=false`。`negative_family` 的条件语义是 exact：

- 当且仅当 `symbol_kinds` exact equal `["frozen_negative"]` 时，
  `negative_family` 必填；
- positive label 必须省略 `negative_family`，出现该字段即 schema failure；
- 所有 frozen-negative labels 的 distinct `negative_family` set 必须 exact equal
  上述完整九值 enum，且每个值至少有一个 label。

`label_id` 与 bbox 由 Quality Owner 在 implementation plan 的第一个
live-preparation step 标注，并随 approved manifest bytes 冻结；label 总数和
per-family counts 一律由 runner 从这些 bytes 机械派生。runner 必须在调用 Provider
前校验 source hash、page count、bbox bounds、label ID 唯一性、九个 positive
families 各至少一个 label，以及完整九类 negative-family coverage。

一个 label 表示一个完整 annotation group，因此同一 diameter + depth 或
counterbore + diameter + depth 组合写入一个 `symbol_kinds` 数组，并只声明一个
expected projection。数组必须非空、无重复并按本文 symbol-kind allowlist 顺序
排序。`frozen_negative` 不得与其他 kind 共存；只有 frozen-negative label 允许
`expected_disposition="ambiguous"`，current-scope positive label 必须声明
candidate、reference context 或 non-inspection。`revision_marker` label 必须使用
`symbol_kinds=["revision_marker"]`、`expected_disposition="non_inspection"` 和
`expected_projection=null`，并且必须省略 `negative_family`。

live result 的比较算法固定如下：

1. 对 candidate 取其 `source_location_ids` 中所有 visual observations 的 bbox
   union；没有 visual source 的 candidate 不参与本次 visual eval。annotation
   group 的 detected kinds 只取对应 coverage `advisor_review.symbol_kinds` 的
   sorted unique union。
2. candidate 与 label 只有在 page 相同、detected kinds 与 label
   `symbol_kinds` exact equal、expected projection 相同，且
   `intersection_area / min(candidate_visual_area, label_area) >= 0.5` 时形成 edge。
3. 每个 positive candidate label 必须恰有一个 edge；每个参与 visual eval 的
   candidate 也必须恰有一个 positive-label edge。degree 为 0 或大于 1 都直接
   fail，不运行猜测式 matching。
4. reference/non-inspection label 使用相同 symbol-kind equality 和 overlap 公式
   比较 coverage entry 的 visual bbox 与 disposition。一个组合 label 只匹配一个
   合并后的 annotation group，不按 detection 数拆 edge。
5. 任一 candidate 与 `frozen_negative` label 达到同一 overlap threshold，即计为
   false positive 并 fail。

live manifest 必须在任何 production edit 前由质量人员完成 bbox 标注并 seal；
未冻结 label count 和 bboxes 时 implementation plan 只能执行 fixture RED，不得
开始 production GREEN。这是输入准备 gate，不留给实现者选择算法或验收口径。

sealing mechanism 固定为：

1. implementation plan 新增
   `.agent/harness/scripts/stage-symbol-eval.py`，只接受 source PDF 和 manifest
   input paths，不把 paths 写入 output。
2. 脚本验证 source hash、2-page identity、schema、bbox、projection、九类 positive
   family completeness，并从 manifest 机械计算 distinct negative-family set 与
   每个 negative family 的 label count。只有 set exact equal 完整九值 enum 且每个
   count `>=1` 时才可写入新的 immutable Harness run artifact。
3. manifest SHA-256、label count、per-positive-family counts、per-negative-family
   counts 和 script/contract hashes 进入 run `input_identity`；脚本据此计算
   `negative_family_count=9`，不接受人工或 CLI 输入的数字作为覆盖证明；seal 后修改
   任一 byte 都使 receipt stale。
4. Quality Owner 在 200% page render 上完成第二遍 overlay 检查，只人工确认
   `overlay_scale_percent=200` 与 `unlabeled_target_count=0`。独立 human verdict
   中的 `negative_family_count=9` 由脚本从已机械验证的 manifest 写入，不由人输入；
   verdict 不写姓名、宿主机 path、PDF bytes 或 screenshot。
5. runner 只接受 literal staging run ID，不接受 `latest` alias。production tests
   只读 sealed manifest，不读原 host label path。

这不是把 expected bbox 注入 recognition。recognition 只能读取 PDF；eval runner
在 result 完成后单向比较 manifest。

## Acceptance Criteria

1. current source bytes 的 SHA-256 必须精确等于
   `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec`；
   不同 bytes 不得复用本验收结论。
2. sealed live manifest 中每个 `expected_disposition="candidate"` label 恰好匹配
   一个 candidate；不得漏检或一对多重复。
3. 每个 `reference_context` label 恰好有一个 coverage entry，且不进入 active
   inspection item list；每个通过 validator 的 `revision_marker` label 恰好匹配
   pre-manual-command Owner 的
   `non_inspection + candidate_id=null + requires_confirmation=true` coverage entry，
   automatic result 和初始 working copy 均无对应 item。live symbol evaluation 在
   任何人工 source command 前完成比较；之后只有显式 Quality Owner
   `promote_source` 才可创建 manual item，`ignore_source` 则无 item 收口。
4. sealed manifest 的 distinct `negative_family` set 恰好等于完整九值 enum、每个
   family 至少一个 label，且所有 frozen negative labels 产生的 candidate 数量为 0。
5. `diameter` projection 的 `normalized_text` 包含 `Φ`，原 `raw_text` 不被覆盖，
   `feature_kind="unknown"` 且 `requires_confirmation=true`。
6. `depth` projection 只有在 associated text 通过现有 typed parser 时成立；
   depth 数值必须来自同一 crop 的 native source。
7. `counterbore` projection 使用现有 `composite`，canonical `⌴` 在
   `normalized_text` 中可见，diameter/depth sub-requirements 顺序稳定，不新增
   public enum。
8. roughness 和三个 current GD&T kinds 只输出四字段 CoarseCandidate，且
   `requires_confirmation=true`。
9. candidate 的 `source_location_ids` 同时包含 visual 与关联 text observation
   IDs；coordinates 包含所有这些 source bboxes。
10. 同一 text annotation 已有 candidate 时，视觉识别只更新该 candidate，不新增
    重复 candidate。
11. 每个 visual observation 恰有一个 coverage disposition；缺失、冲突或无坐标
    时 processing blocking。
12. visual batch 需要超过每页 16 次调用时返回
    `symbol_route_budget_exhausted`，不得截断后成功。
13. current live run 的 Vision 调用总数每页不超过 16，并且调用顺序在相同输入上
    可重复。
14. invalid schema、越界 bbox、未知 observation ID、重复 detection 或
    confirmation downgrade 均不能修改 candidate。
15. Provider 不可用时项目不能进入 `ready_for_edit`；不得以 text-only result
    作为 formal success。
16. 同一 logical task replay 返回同一 result ref，Provider call count 增量为 0。
17. 旧 text-only fixture 的 candidate payload、coverage、working-copy creation
    和 export regression 全部保持通过。
18. frontend 同时显示“图纸原文”和不同的“识别结果”；补出的 `Φ/深/⌴/∥/⊥/⏥`
    在识别结果中可见。
19. UI 必须区分 ambiguous no-detection 与 qualifying revision-marker noninspection；
    两者都可定位到正确 page/bbox，并只在 Quality Owner 显式操作后执行 promote 或
    ignore；模型 response 不对用户暴露。
20. Provider call record、API response、logs、sealed receipt 和 committed fixture
    通过 secret/base64/private-path scan。
21. current source 必须以新 project 或批准的 versioned reprocess 运行；旧
    AutomaticResult bytes 和 candidate count 保持不变。
22. synthetic fixture、focused tests 和 sealed current-PDF live comparison 全部
    通过后，才能声称该 spec 完成。synthetic fixture 不能替代 live proof。

## Testing Plan

| Layer | Required coverage | Minimum new checks |
| --- | --- | ---: |
| Unit: PDF | stable visual ID、path-item context、threshold negatives、bbox transform、batch split | 5 |
| Unit: Advisor | strict schema、source allowlist、bbox validation、9-kind mapping、dedupe、budget blocking | 9 |
| Unit: Coverage | visual candidate/reference/non-inspection/ambiguous、conflict blocking | 4 |
| Provider contract | `visual-symbol-review/1` valid/invalid fixtures、call-record redaction/cache identity | 2 |
| Integration | vector PDF → observation → Provider fake → candidate/coverage → working copy；failure path；idempotency | 6 |
| Frontend | normalized symbol display、coarse symbol display、ambiguous visual source action | 3 |
| E2E fixture | upload → automatic → review for positives；negative regions create no items | 2 |
| Live acceptance | sealed current source manifest exact comparison | 1 |

Minimum new checks: 32。

### Required Test Cases

下面 32 项是最小检查清单。parameterized test 可以覆盖同一项内列出的多个
allowlisted kind，但不得用一个宽泛 smoke 代替跨 layer 的独立断言。

| ID | Proposed test | Required assertion |
| --- | --- | --- |
| PDF-01 | `test_visual_observation_id_and_order_are_stable` | 相同 PDF bytes 重跑得到相同 ID、顺序、bbox 和 geometry hash |
| PDF-02 | `test_small_nearby_path_items_form_text_adjacent_context` | `≤96 pt` 且距 native line `≤12 pt` 的 path item 形成一个 context，并绑定排序后的 text IDs |
| PDF-03 | `test_large_distant_or_page_geometry_is_rejected` | 大轮廓、远离文字、union `>1%` page 的 geometry 不形成 observation |
| PDF-04 | `test_visual_bbox_round_trip_and_union` | PDF/normalized 坐标 round-trip，candidate bbox 恰为 source bbox union |
| PDF-05 | `test_visual_batches_use_stable_first_fit` | 相同 observation 序列得到相同 batch membership、crop 和 call order |
| ADV-01 | `test_visual_symbol_response_accepts_only_exact_schema` | exact `visual-symbol-review/1` payload 可进入 validator |
| ADV-02 | `test_visual_symbol_response_rejects_invalid_identity_or_shape` | extra field、unknown ID、越界 bbox、duplicate detection 和未知 kind 全部 fail closed |
| ADV-03 | `test_diameter_enriches_existing_candidate` | existing candidate ID 保持，raw source 不改，normalized 显示 `Φ`，`feature_kind=unknown` 且需确认 |
| ADV-04 | `test_depth_uses_same_crop_typed_value_or_stays_ambiguous` | 只接受同 crop native typed value；冲突或缺值不猜测 |
| ADV-05 | `test_counterbore_maps_to_stable_composite` | composite sub-requirements 顺序稳定，normalized 显示 `⌴`，不新增 public enum |
| ADV-06 | `test_surface_roughness_maps_to_four_field_coarse_candidate` | 只产生冻结四字段 `roughness` coarse payload，并需确认 |
| ADV-07 | `test_gdt_kinds_map_to_four_field_coarse_candidate` | `parallelism/perpendicularity/flatness` 分别映射 `∥/⊥/⏥`，不提升 Provider 为语义 Owner |
| ADV-08 | `test_reference_revision_and_no_detection_dispositions` | datum 仅在本地 validator 通过后为 reference；通过 closed-triangle + inner-token validator 的 revision marker 仅为 `non_inspection`，invalid marker 不能成为 `revision_marker`；no-detection 保持可恢复 source review |
| ADV-09 | `test_unified_scheduler_is_deterministic_and_blocks_visual_overflow` | exact priority/tie-break 生效；visual calls `>16/page` 返回 `symbol_route_budget_exhausted` |
| COV-01 | `test_visual_candidate_has_one_complete_coverage_entry` | candidate disposition 有 visual/text lineage 和完整 coordinates |
| COV-02 | `test_visual_reference_noninspection_and_ambiguous_are_distinct` | 三种 disposition 不互相覆盖，confirmation 状态符合本 spec |
| COV-03 | `test_visual_missing_source_coordinates_or_conflict_blocks` | 缺 source、缺 coordinates、一个 observation 多 disposition 均为 blocking |
| COV-04 | `test_visual_confirmation_cannot_be_downgraded` | Provider 或 projection 不得把 required confirmation 降级 |
| PROV-01 | `test_qwen_visual_symbol_schema_and_cache_identity` | request/response schema、crop hash、schema version 和 cache key 一致 |
| PROV-02 | `test_qwen_visual_symbol_records_are_redacted_on_success_and_failure` | 成功/invalid-schema call records 均无 image bytes、private path、credential 或模型原文泄漏 |
| INT-01 | `test_vector_fixture_builds_visual_candidate_and_working_copy` | sanitized PDF 从 observation 到 candidate/coverage 再到 working copy |
| INT-02 | `test_diameter_depth_and_counterbore_group_as_one_annotation` | 组合标注只生成一个 primary candidate/disposition，不重复 item |
| INT-03 | `test_roughness_gdt_and_datum_project_without_schema_expansion` | coarse/reference projections 使用现有 public shapes |
| INT-04 | `test_visual_provider_failure_prevents_ready_for_edit` | Provider/schema/cache/budget failure 不生成 AutomaticResult 或 working copy |
| INT-05 | `test_visual_no_detection_remains_actionable_source_review` | no-detection source 可定位并执行现有 promote/ignore command |
| INT-06 | `test_visual_processing_replay_is_idempotent` | logical task replay 返回同一 result ref，Provider call 增量为 0 |
| FE-01 | `ReviewPanel.test.tsx: shows raw_and_normalized_symbol_text_separately` | “图纸原文”与“识别结果”不互相覆盖 |
| FE-02 | `InspectionItemTable.test.tsx: renders_coarse_symbol_and_confirmation` | roughness/GD&T 图标、coarse type 和 confirmation 可见 |
| FE-03 | `PdfWorkspace.test.tsx: locates_and_actions_visual_source` | visual bbox 定位正确，并复用 promote/ignore；不显示模型 response |
| E2E-01 | `test_symbol_fixture_positive_flow` | fixture positives 完成 upload → automatic → review，匹配 manifest |
| E2E-02 | `test_symbol_fixture_negative_regions_do_not_create_items` | 12 个 negative regions 不生成 candidate/reference/inspection item |
| LIVE-01 | `test_sealed_current_pdf_symbol_manifest` | literal run ID 下 positives、non-inspection、reference、negative 和 exact-one matching 全部通过 |

Task 5 还必须增加 supporting regression
`test_revision_marker_stays_noninspection_until_explicit_promote_source`：automatic result
和 initial working copy 必须保持 non-inspection coverage 且无 item，任何 automatic
path 都不得 promote；显式 Quality Owner `promote_source` 可创建一个 manual item，
显式 `ignore_source` 则无 item 收口。该 regression 不新增 logical ID，32 项表和
count 保持不变。

focused verification 的第一版命令必须由 implementation plan 精确绑定，但至少包括：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py -q

npm --prefix frontend test -- \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
```

现有行为回归不得只写成“跑相关测试”。implementation plan 至少绑定以下已存在
的 suite：

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
  backend/tests/integration/test_review_working_copy.py -q

npm --prefix frontend test
npm --prefix frontend run build
```

回归 gate 要求上述现有 tests 不删除、不改成 skip，不通过放宽 snapshot 或 candidate
count 来掩盖差异；随后再运行 fixture E2E 和 sealed current-PDF live selector。

## Expected File Surface

下表是 implementation plan 的最大预期边界，不是本 spec turn 的写权限：

`2026-07-27` 已核对现有 interfaces：

- `PageInventory` 位于 `backend/app/pdf/schemas.py`；
- native inventory 位于 `backend/app/pdf/inventory.py::build_inventory()`；
- canonical snapshot 位于
  `backend/app/processing/automatic_result.py::candidate_snapshot_from_inventory()`；
- Vision Owner 位于 `backend/app/candidates/advisor.py::CandidateAdvisor`；
- source-only review commands 当前由
  `InspectionWorkbench`、`InspectionItemTable` 和 `PdfWorkspace` 消费。

`backend/app/pdf/visual_observations.py` 和
`backend/app/providers/visual_symbol_review.schema.json` 是预期 new files；其余表项
当前均存在。implementation plan 仍须在写入前复核 HEAD，防止并发提交导致接口
漂移。

| File or module | Expected change |
| --- | --- |
| `backend/app/pdf/schemas.py` | 增加 `VisualObservation` 和 additive page field |
| `backend/app/pdf/inventory.py` | 构建 deterministic visual proposals，不提交业务类型 |
| `backend/app/pdf/visual_observations.py` | 新增纯 signal builder、path-item context、stable ID |
| `backend/app/candidates/advisor.py` | 统一 text/visual routing、batch budget、唯一 automatic raw final write |
| `backend/app/processing/automatic_result.py` | 将 visual IDs 加入 expected coverage；不得另建 result path |
| `backend/app/candidates/coverage.py` | visual disposition、budget blocker、完整性检查 |
| `backend/app/providers/qwen_vl.py` | 解析新冻结 schema；adapter 仍不拥有 disposition |
| `backend/app/providers/visual_symbol_review.schema.json` | 新增 exact Provider response schema |
| `backend/app/processing/runtime_recognition.py` | 把 visual observations 和 unified Advisor 接到 canonical task |
| `backend/app/processing/pipeline.py` | 记录脱敏 visual failure stage |
| `backend/app/review/service.py` | 投影 visual source lineage，剥离 Provider diagnostics |
| `backend/app/projects/router.py` | 把 visual observations 投影到现有 workbench sources |
| `frontend/src/api/types.ts` | 声明 `normalized_text` 和 visual source projection |
| `frontend/src/components/review/ReviewPanel.tsx` | 显示识别结果，不覆盖图纸原文 |
| `frontend/src/components/workbench/InspectionItemTable.tsx` | 在统一列表中显示并处理 ambiguous visual source |
| `frontend/src/components/pdf/PdfWorkspace.tsx` | 按 visual source bbox 定位并显示局部来源 |
| `backend/tests/helpers/symbol_fixture.py` | 生成 deterministic sanitized vector fixture 和独立 manifest |
| `backend/tests/**`, `frontend/src/**/*.test.tsx` | 32 个以上 focused checks |
| `docs/contracts/MAIN_CONTRACT_MATRIX.md` | 先改 stable contract Owner rows |
| `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md` | 新增/修订 P0 selectors |
| approved implementation plan | 唯一 task 顺序、allowed paths、rollback 和 live gate |
| `.agent/harness/scripts/stage-symbol-eval.py` | 校验并 seal current-source live labels |
| `.agent/harness/**` | 只在 contract Markdown 更新后生成 mirror、schema 和 selectors |

implementation plan 必须再次核对实际 import/call-site，删除不存在或不需要的文件；
不得因为本表列出就机械创建 wrapper。

## Rollback Plan

1. implementation 必须以独立、可 revert 的 task commits 交付；contract amendment、
   backend behavior、frontend display 和 Harness closure 分开提交。
2. backend rollout 不引入数据库 migration、public candidate enum 或双写，所以
   rollback 以 revert visual-observation/Advisor commits 为主。
3. rollback 前停止新 processing submission，等待 active logical tasks 到终态，
   不删除或改写已生成 raw results。
4. 新结果只使用现有 Candidate/CoarseCandidate/composite payload，旧版本仍能读取；
   visual source ID 只是 additive source relation。
5. rollback 后第一项验证是现有 text-only Advisor/provider/processing focused
   suite；随后验证一个旧 raw result 能创建 working copy 并完成 review/export。
6. rollback 不能把已经暴露的 visual candidates 从旧 project 中静默删除。若出现
   payload incompatibility，rollback verdict 为 blocked，必须先恢复兼容 reader。
7. 不保留 disabled visual feature flag、shadow scorer 或 legacy fallback 作为
   rollback 手段。

## Effort Estimate

| Work package | Human engineering estimate |
| --- | ---: |
| Contract amendment、live manifest schema、RED fixtures | 0.5–1.0 day |
| Visual observation extraction and negative filters | 1.0–1.5 days |
| Provider schema、unified routing、validator、candidate mapping | 1.5–2.0 days |
| Coverage、review source projection、immutability regression | 1.0 day |
| Frontend normalized/source display | 0.5 day |
| Integration、E2E、sealed live gate、independent review | 1.5–2.0 days |

Total: 6–8 human engineering days。该估算不包含扩展到完整标准符号库、scanned
support 或通用 accuracy benchmark。

## Execution Selection

- Selected lane: `Heavy`。本能力改变 stable internal schema、`CAND-004` Vision
  routing scope、candidate/coverage 跨模块 data-integrity boundary，并需要 live
  contract verification。
- Selected plan: 当前
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
  保持不变；本文不是 implementation plan，也不成为第二套 current plan。
- Selection evidence: current first-PDF runtime、source code call chain、页面渲染和
  用户选择“当前图纸闭环”共同证明需要新 visual observation 能力。
- Activation evidence: Task 0 已由 commit `994cbe4` 把 subordinate proposal、
  `SR-1 → SR-8` 顺序和全部执行边界激活到唯一 current plan；用户批准的 Option A
  clarification 现已生效。
- Validation action: `continue`；下一步是 current plan 的 `SR-1` contract/Harness
  RED，不再请求 design/proposal approval，也不再运行 `writing-plans` 或重复 Task 0。
- Writer ownership and order: 同一 backend file group 只有一个 writer，frontend 在
  backend projection 冻结后顺序开始，reviewer 保持只读。
- Next verification: `SR-1` 先运行
  `test_symbol_eval_contract.py`、`test_contract_architecture.py` 和
  `test_live_run_contract.py` 的 contract/Harness RED；不能先修改 production code
  或调用真实 Provider。

## Risks

- path-item context 过宽会把工程几何当符号。通过硬上限、负样本和 candidate
  projection validator 控制，不能依赖模型 confidence。
- path-item context 过窄会切断 symbol 与 value。associated text IDs、batch crop 和 live
  manifest 必须同时验证。
- current PDF 的 watermark、revision-table/invalid-marker geometry、qualifying
  revision markers 和 center marks 数量多，若 proposal priority 错误会耗尽预算。
  visual budget 必须按 observation batch 而不是 text reading order 分配。
- counterbore 完整工程语义超出当前 typed schema。本版只保留 canonical symbol、
  diameter/depth sub-requirements 和人工确认，不声称完成标准语义解析。
- 展示 normalized text 可能被误认为原始 OCR。UI 必须明确区分“图纸原文”和
  “识别结果”。
- 本能力只有 current-PDF closure，不得把该 live pass 外推为任意工程图准确率。

## Active Execution Gate

本 semantic design 和 Option A clarification 已获批准；Task 0 activation commit
`994cbe4` 已完成，唯一 current plan 继续拥有执行授权和顺序。下一步只能进入
`SR-1` contract/Harness RED；不得再次请求 spec/plan approval、运行
`superpowers:writing-plans`、创建第二份 current plan、先改 production code 或先调用
真实 Provider。
