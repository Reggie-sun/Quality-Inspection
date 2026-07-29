# Engineering Drawing Symbol Recognition Design

## Status

- Date: `2026-07-29`
- Status: `v2 implemented; v3 context-compaction approved; production TDD authorized`
- Selected scope: 当前失败 PDF 闭环
- Selected lane: `Heavy`
- Execution authorization owner: unique current plan; this design does not authorize execution
- Activation state: original Task 0 complete at `994cbe4`; historical v2 SR-2B
  Quality Owner gate closed on `2026-07-28`; v3 Quality Owner gate closed on
  `2026-07-29`, authorizing only the proposal-only TDD boundary below

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

本节记录当前 runtime 的 `visual-observation/1` baseline。下方
`2026-07-28 Hybrid Proposal-Gate Amendment` 已批准退休其中“不检查 line text”和
“每个 geometry-qualified line 必定形成 observation”的 admission clauses；在 exact
v2 rule table、overlay evidence 和 Quality Owner verdict 独立 commit 前，v1 仍只是
实际运行基线，不能被报告为已完成的 v2 contract。

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

### 2026-07-28 Current-Source Capacity Amendment

SR-4 Step 8 已按 final algorithm、sealed source 和 current code 重算，当前 runtime
truth 为：

| Page | Native lines | Visual observations | Natural-order batches | Priority-order batches |
| --- | ---: | ---: | ---: | ---: |
| 0 | 174 | 132 | 17 | 19 |
| 1 | 265 | 203 | 19 | 22 |

该结果重复执行完全一致，Provider calls 为 `0`。因此上方 84/182、10/13 只能作为
pre-freeze exploratory prose；Git history 中没有对应 executable script、artifact、
tool identity 或 test，不能作为 acceptance/runtime evidence。当前实现没有显示
first-fit guard、off-by-one 或 member-cap bug；主要 rejection surface 是
`7.5%` crop area 和 `1536px` sides，priority order 只是额外放大器。

用户批准先做 bounded capacity feasibility，不批准 silent filtering、threshold
tuning、observation dropping、full-page Vision 或提高 Provider call budget。冻结
边界如下：

1. feasibility 阶段保留全部 `132/203` observation IDs 和现有 proposal、dedup、
   padding、`7.5%` area、`300 DPI`、`1536px`、`32` members、`16/page` contracts；
2. 每个 ID 必须在 certificate 中出现恰好一次，且独立 validator 必须重新计算每个
   crop 的全部 limits；candidate search 与 validator 不共享 mutable state；
3. search 顺序、fitness、state bound 和 tie-break 必须 deterministic；不得记录
   sealed-source observation IDs、coordinates 或 membership 作为 production rule；
4. bounded search 未找到 certificate 只证明
   `capacity_feasibility_unproven`，不能宣称数学上不可行，也不能自动改变 contract；
5. 只有两页都得到 `<=16` certificate，才允许先把新的 generic packing algorithm
   精确写入本节，再按 TDD 替换 stable-first-fit；在 exact algorithm delta commit
   前不得修改 production；
6. certificate 不成立时，必须回到 contract Owner，在“容量/cost/privacy policy”
   与“proposal/dedup semantics + 新正负样本证据”之间另行决策。

OSS 对照只融合 license-safe 的算法思想：deterministic sort、best-fit fitness、
bounded exact/heuristic search 和 independent solution checking。外部 rectangle
packing 允许移动 items，而本 contract 保留 PDF 原坐标、以 padded union crop 判定，
两者问题不同；因此不引入 `rectpack`、OR-Tools、PackingSolver 或其他 dependency，
也不复制其实现。

这些阈值是首版 current-PDF contract，不是用户配置。后续修改必须以新的负样本或
漏检证据进入 amendment，不能为单一坐标写 exact-input 特判。

### 2026-07-28 Hybrid Proposal-Gate Amendment

上述 bounded feasibility search 已按冻结的 deterministic state bound 执行。page 0
在 depth `76`、expanded states `248890`、frontier `4096` 时停止；page 1 在
depth `72`、expanded states `249792`、frontier `4096` 时停止。两页均为
`capacity_feasibility_unproven`，Provider calls 为 `0`。这不是数学不可行证明，
但不足以授权 packing-only production change。Contract Owner 随后选择
`proposal/dedup semantics + 新正负样本证据`，并批准使用 hybrid high-recall
proposal gate 和完整 Quality Owner 复核。

本 amendment 只设计 proposal correction；在下述 exact rule table、overlay 和
Quality Owner gate 全部冻结前，不授权 production RED、production edit、SR-4
Step 8 或 Provider call。

#### Single Proposal Owner And Data Flow

`backend/app/pdf/visual_observations.py::build_page_visual_observations()` 是 proposal
admission 的唯一 Owner：

```text
native line/span + canonical path items
→ provisional line context
→ pure proposal features
→ hybrid admission gate
→ existing bbox/dedup/order
→ VisualObservation v2
→ PageInventory
→ existing coverage / priority / packing / Provider / projection
```

`inventory.py` 只提供 native observations 和 drawings 并持久化 Owner 输出。
`automatic_result.py`、`symbol_review.py` 和 `advisor.py` 只能消费 retained
observations，不得再做第二次 proposal filter、merge、ranking 或 budget truncation。
`CandidateAdvisor` 继续是唯一 automatic candidate/coverage write Owner。

#### Hybrid Admission Contract

Owner 先按现有 `96 pt` item extent、`12 pt` both-axis gap 和 `1%` context area
构造 provisional line context，再计算一个 internal-only immutable feature record。
允许的 feature 仅包括：

- `normalized_text` 的形态，例如 digit presence、uppercase alphanumeric short token
  和 token length；不得把原文或具体 token 值写入 feature record；
- canonical path opcode/style 的 count 和 boolean facts，例如 close path、fill、
  dash 和 distinct style；
- path-item、line 和 provisional context 的 width、height、area、count、relative
  gap 与 aggregate dimensions。

禁止使用 page index、absolute position、source SHA、observation ID、label ID、
approved label bbox、parser/candidate/Provider result、wall-clock order 或 runtime
sample statistics。production runtime 不训练、拟合或自动选择阈值。

最终 gate 是一张 static、explicit、versioned boolean rule table：

- geometry admission branch 保留具有可解释 compact/frame/marker evidence 的
  provisional context；
- short technical-token rescue branch 防止 datum、revision 和紧凑 measurement
  context 被 geometry branch 单独漏掉；
- 每个 rejection 必须有稳定的 internal reason code，供 preflight overlay 使用；
  reason code 不进入 API、DB、Provider prompt、coverage 或 formal result；
- 不允许 top-k、score cutoff、random selection 或按剩余 call slots 静默丢弃；
- retained observations 若仍需 `V > 16`，继续
  `symbol_route_budget_exhausted`，不得把 rejected context 伪装成
  `non_inspection` 或已覆盖。

exact predicate、全部 snapped thresholds、branch order、tie-break 和 rule digest
必须先写回本节并独立 commit，之后才可写 production RED。规则候选可以由 sealed
labels 做 offline calibration，但 rule grammar 必须保持上述通用特征边界；manifest
和 label facts 不得被 production import 或读取。

#### Exact Rule Reproduction Correction — 2026-07-28

首次逐字执行 commit `e795744` 中冻结的 no-write renderer 时，机械 gate 正确
fail closed：page 0 / page 1 只得到 `62 / 105` retained observations、
positive overlap `21/26 / 28/30`，而不是冻结的 `79 / 124` 和
`26/26 / 30/30`。根因不是 source、manifest、PyMuPDF 或阈值漂移，而是 plan
transcription 有两处不一致：

1. 历史 calibration 计算的是
   `sum(bool(style["dashes"]))`；PyMuPDF 的 solid pattern `"[] 0"` 也为 truthy。
   plan 后来把该 feature 收紧并误写为“排除 solid 的 `dash_count`”，但仍沿用了
   历史 counts 和 digests。
2. 冻结 observation-ID digest 来自
   `sha256("\n".join(sorted(ids)).encode("utf-8"))`；renderer 却改成了 ordered
   JSON list digest。

在原 wide branch 的全部其他前置条件内，历史 truthy-style count 与 selected
canonical path-item count 的命中集合完全一致：page 0 均为 `23`，page 1 均为
`39`；真正的 non-solid dash count 两页均命中 `0`。因此 exact reproduction
冻结为通用 feature `item_count=len(selected canonical path items)`，不是根据
label 重新拟合阈值。修正后的 branch 为：

```python
if (
    common
    and features.fill_count <= 1
    and features.max_item_width > Decimal("60.000")
    and features.item_count > 3
):
    return _ProposalDecision(True, "geometry_wide_multi_item")
```

其余 thresholds、branch order、quantization、bbox/dedup、priority 和 crop limits
保持不变。exact canonical rule JSON 为：

```json
{"branch_order":["geometry_compact","geometry_wide_multi_item","geometry_filled","short_token_rescue"],"feature_quantum":"0.001","geometry_common":{"max_item_height_min_exclusive":"2.000","mean_item_height_max":"34.000"},"geometry_compact":{"context_area_max":"6000.000","fill_count_max":1,"max_item_width_max":"60.000"},"geometry_filled":{"context_area_min_exclusive":"5800.000","fill_count_min_exclusive":1,"max_item_height_max":"42.000"},"geometry_wide_multi_item":{"fill_count_max":1,"item_count_min_exclusive":3,"max_item_width_min_exclusive":"60.000"},"proposal_rule_version":"visual-observation/2","schema_version":"visual-proposal-gate/1","short_token_rescue":{"context_area_max":"6000.000","pattern":"[A-Z0-9]{1,3}"}}
```

SHA-256 固定为
`ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7`。
observation-ID set digest 固定使用 lexicographically sorted IDs、以单个 `\n`
连接、无尾随换行的 bytes；batch-membership digest 继续使用 stable ordered nested
list 的 compact canonical JSON。独立 no-write reproduction 已恢复 page 0
`79 / 13`、page 1 `124 / 16` 及原冻结的四个 ID/batch digests；这只冻结 exact
candidate，仍不构成 Quality Owner approval。

#### Preserved Geometry, Dedup And Scheduling

本轮保持以下合同不变：

- retained bbox 仍是 associated native line 与当前入选 path items 的 clipped union；
- geometry SHA、associated text IDs、public `VisualObservation` fields 和
  `proposal_kind="text_adjacent_vector_context"` 的含义不变；
- exact geometry 只在 associated text IDs 相同时去重，IoU `>=0.8` 仍要求相同
  associated IDs；不做跨 text-owner coalescing；
- priority、stable first-fit、padding、`7.5%` page area、`300 DPI`、`1536px`
  side、`32` observations 和 `16/page` budget 不变；
- 每个 retained visual ID 继续恰有一个 initial coverage entry，并进入
  expected/required ID 集合。

只读 current-source exploration 已证明，单独做 exact-geometry merge 或 IoU merge
不能把 page 1 降到 `<=16` batches；按 local components 拆细还会增加 batch count。
因此这两条路径不进入 implementation。

#### Version, Reconstruction And Cache Identity

proposal semantics 改变时：

1. `PROPOSAL_RULE_VERSION` 必须从 `visual-observation/1` 升为
   `visual-observation/2`，使 retained observation IDs 全部重新绑定 exact rule；
2. `symbol_review.py` 不得继续维护独立硬编码的
   `VISUAL_PROPOSAL_VERSION`；cache identity 必须复用 proposal Owner 的单一版本
   常量；
3. inventory observation 与 private `VisualGeometryContext` 必须保持一一对应；
4. reconstruction 继续用相同 source bytes、PyMuPDF version、canonicalization 和
   gate 重建 exact observations；missing、extra、order、ID 或 geometry mismatch
   都在 Provider construction 前 blocking。

本轮不改变为 multi-line context，因此不扩展 `VisualGeometryContext.line_bbox_pdf`，
也不引入 keeper-bbox 与 associated-text union 的双重事实。

#### Calibration Evidence And Quality Owner Gate

一个只读、无坐标特判的 hybrid candidate 在当前 source 上得到：

| Page | Current observations | Candidate observations | Candidate batches | Positive regions with visible overlap |
| --- | ---: | ---: | ---: | ---: |
| 0 | 132 | 79 | 13 | 26 / 26 |
| 1 | 203 | 124 | 16 | 30 / 30 |

该表只证明通用 feature space 存在 bounded candidate，不是 approved rule、formal
overlap、release evidence 或 production expected count。它不得替代完整视觉复核。

exact gate 冻结前必须重新生成：

1. 两页 `200%` 完整 overlay，明确区分 retained 和 rejected provisional contexts；
2. 六个带 token 的 positive `revision_marker`；
3. 五个按 N5 处理的无 token 闭合三角 negative；
4. 全部 GD&T frame 与独立 boxed datum；
5. diameter、depth、counterbore、surface roughness 各至少一个代表区域；
6. 标注最密集、最容易漏标或误框的区域；
7. 全部 `56` positive labels 与 `16` frozen-negative regions 的 gate disposition。

机械 preflight 还必须证明：

- repeated observation-ID digest、rule digest 和 batch-membership digest 完全一致；
- 每个 retained ID exact-once，全部 crop/member/pixel/area limits 为 true；
- 两页各自 `V <= 16`；
- rejected context count 和 reason-code counts 可复算；
- Provider construction/calls 为 `0`。

Quality Owner approval 必须绑定：

- sealed manifest SHA-256
  `0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448`；
- `proposal_rule_version="visual-observation/2"`；
- exact rule digest；
- 两页完整 overlay 和全部局部放大图的 digests；
- `annotation_status=approved` 与 `unlabeled_target_count=0`。

existing sealed manifest bytes 不修改、不重生成。Quality Owner 未明确批准以上 exact
evidence 时，不得把 exploratory overlap 写成 formal success。

#### Quality Owner Approval Evidence — 2026-07-28

Quality Owner 收到两页 `200%` 完整 overlay、五张 zoom、完整 report、全部 exact
digests，以及 `FN-03/FN-04/FN-08/FN-11` retained-overlap 风险提示后，明确回复
“可以”。该人工 verdict 现按以下 compact、sorted-key canonical JSON 冻结：

```json
{"annotation_status":"approved","manifest_sha256":"0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448","overlay_scale_percent":200,"overlay_sha256":{"page-1-proposal-gate-overlay-200pct.png":"da25c8e0f04c4468deb094bb6be9f8565fd9d855ad3b40c44bad8cb40da15202","page-2-proposal-gate-overlay-200pct.png":"8335c1e22ba02474ef9ddf7fdd111dd86cbd9ebc056cf8ce429155e62fda0ec7"},"proposal_gate_report_sha256":"13f73e1c790b277c6d317c016e1df5e41c52eb62a07d336b69b5f9d6df7152d9","proposal_rule_sha256":"ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7","proposal_rule_version":"visual-observation/2","reviewed_frozen_negative_region_count":16,"reviewed_positive_label_count":56,"schema_version":"visual-proposal-gate-verdict/1","unlabeled_target_count":0,"zoom_sha256":{"zoom-core-symbol-representatives.png":"a9773c5cab2caa24b83160dd0ce44a2cf51a2af037145affb62c9807f6fb3219","zoom-densest-region.png":"bcae9e7852bd78cee21ae5b5d5e66aaf482b375118593c8b21dde21f22dc2d0d","zoom-gdt-and-boxed-datum.png":"a0060d71ebbdd8ce2f6b594bdb4d08ab4c228cfa7a5490811cc83ce3fd55fdaa","zoom-n5-negative.png":"2a61789008b0b731378dcbf63f7c697df7710ae9a687c0a94e43381d8938ad4c","zoom-revision-positive.png":"941d8db1b45047993c1aa8bf436749f2897c6ccb37011133cd21511026293a9e"}}
```

该 verdict JSON 的 SHA-256 为
`9b7a6aa061315f7e8501c348e57b21219b597a2374fb8ffca976bedc978f50ef`。
`unlabeled_target_count=0` 来自同一 sealed run、绑定相同 manifest SHA 和
`overlay_scale_percent=200` 的
`visual-symbol-annotation-verdict.json`；不是从 manifest 猜测或补写。

Step 2 的 final stable handles 为：

| Page | Provisional | Retained | Batches | Observation-ID SHA-256 | Batch-membership SHA-256 |
| --- | ---: | ---: | ---: | --- | --- |
| 0 | 132 | 79 | 13 | `15f476cac29683c425b85b541ad528b38f1983fb5673871466626038ef1852f5` | `dc7b19187c7346e61f9344d63197f6e815ab3f85af1c6316e2e00888ed8bf0d8` |
| 1 | 203 | 124 | 16 | `4f082c0ce52fb649cd9c84c16b685ced29133dc12c3b37392df63767043a4e16` | `8a6f8ef3f3c50f85841de792f7bbc078062d4d8c1da75beaa17768b002a50ea2` |

两次 renderer 的全部八个文件逐 byte 相同；exact-once、crop/member/pixel/area
limits、reason counts 和全部 `56` positive / `16` frozen-negative label references
均通过，Provider construction/calls=`0`。该 approval 只关闭 SR-2B proposal
admission gate，不声称 production implementation、SR-2C、SR-4 Step 8、SR-5 或
任意工程图通用准确率已经通过。

#### V3 Context-Compaction Recovery Candidate — 2026-07-28

historical v2 approval 和 artifacts 保持 immutable。fresh sealed run
`20260728T095023589634Z-740b6624` 证明 v2 已满足 79/124 observations、
13/16 batches 和 Provider budget，但 `P1-P16`、`P2-P18`、`P2-P27` 的最佳
proposal overlap 分别只有 `0.156364`、`0.032575`、`0.368643`，低于 LIVE-01
固定的 `intersection_area / min(area) >= 0.5`。perfect Provider kind 也不能弥补
该 proposal geometry 缺口，因此旧 v2 verdict 不得被解释为本次 v3 approval。

proposal admission 的唯一 Owner 仍是
`backend/app/pdf/visual_observations.py::build_page_visual_observations()`。旧路径把
`12 pt` 邻域内全部 `<=96 pt` path items 合并成一个 source union：一条远端宽线或
高线会稀释真正 glyph bbox；同一局部 glyph 即使在 compact subset 中仍满足既有
gate，也可能被 over-area precheck 丢弃。v3 直接替换这两处 context selection，
不保留 v2 fallback/shadow Owner，不使用 source/page/label/absolute coordinate、
approved bbox、candidate、Provider 或 evaluator result。

base feature、snapping 和四个 v2 admission branches 全部保持。Owner 另计算
`compact_items`：只保留每个 bbox width `<=60.000 pt` 且 height `<=42.000 pt`
的已选 canonical path item。然后按以下 exact order 决定实际 context：

1. base source union 超过 page area `1%` 时，只有 compact union 同时不超过该 page
   cap、compact `context_area <=6000.000`、short token fullmatch、compact
   `item_count >40`，且 compact decision exact 为 `short_token_rescue`，才以
   compact context retain，reason 为 `dense_short_token_compact_rescue`；
2. base source union 不超过 page cap，且 base decision exact 为
   `geometry_wide_multi_item` 时，只有 compact union 也不超过 page cap 且 compact
   decision exact 为 `geometry_compact`，才用 compact context 替换 base context，
   reason 为 `wide_compact_replacement`；
3. 其余 base-area-valid context 继续使用原 v2 decision/context；不满足上述条件的
   over-area context 继续 fail closed。

exact canonical rule JSON 为：

```json
{"base_branch_order":["geometry_compact","geometry_wide_multi_item","geometry_filled","short_token_rescue"],"compact_item_filter":{"max_item_height_max":"42.000","max_item_width_max":"60.000"},"context_transform_order":["dense_short_token_compact_rescue","wide_compact_replacement","base_admission"],"dense_short_token_compact_rescue":{"base_context_area_relation":"greater_than_page_area_cap","compact_context_area_max":"6000.000","compact_context_area_relation":"less_than_or_equal_to_page_area_cap","compact_item_count_min_exclusive":40,"compact_reason_required":"short_token_rescue"},"feature_quantum":"0.001","geometry_common":{"max_item_height_min_exclusive":"2.000","mean_item_height_max":"34.000"},"geometry_compact":{"context_area_max":"6000.000","fill_count_max":1,"max_item_width_max":"60.000"},"geometry_filled":{"context_area_min_exclusive":"5800.000","fill_count_min_exclusive":1,"max_item_height_max":"42.000"},"geometry_wide_multi_item":{"fill_count_max":1,"item_count_min_exclusive":3,"max_item_width_min_exclusive":"60.000"},"proposal_rule_version":"visual-observation/3","provisional_context":{"axis_gap_max":"12.000","item_extent_max":"96.000","page_area_ratio_max":"0.010"},"schema_version":"visual-proposal-gate/2","short_token_rescue":{"context_area_max":"6000.000","pattern":"[A-Z0-9]{1,3}"},"wide_compact_replacement":{"base_context_area_relation":"less_than_or_equal_to_page_area_cap","base_reason_required":"geometry_wide_multi_item","compact_context_area_relation":"less_than_or_equal_to_page_area_cap","compact_reason_required":"geometry_compact"}}
```

SHA-256 固定为
`8b7b67f4e303c7cfb7648c9dc2b11530198216f4799ee485f49199f0e99a8cfa`。
rule/version 变化使全部 v3 observation IDs 和 cache identities safe miss；v2
artifacts、cache、run 和 verdict 不修改、不删除。

no-write calibration 枚举 page 0 / page 1 的 `148 / 244` raw adjacency contexts，
其中 `132 / 203` 通过 base area cap；v3 最终得到 `80 / 125` observations 和
`13 / 16` official priority batches。`56/56` positives 的最大 overlap 均
`>=0.5`，16 个 frozen negatives 的 overlap 风险仍为 `4 any / 3 >=0.5`，与 v2
相同。该表只冻结 candidate，不是 Quality Owner approval。

production RED 前必须以 exact source SHA
`58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec`
和 sealed manifest SHA
`0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448`
运行 no-write/no-Provider renderer 两次，逐 byte 比较两页 200% full overlays、
五张 zoom 和 canonical report。report 必须覆盖 56 positives、16 frozen
negatives、exact rule/ID/batch digests、80/125 counts、13/16 batches、
exact-once、all crop limits、repeatability 和 Provider construction/calls=0。
Quality Owner 必须看到完整图片并明确批准 exact v3 evidence；overlap count、
本节 calibration 或先前“可以”都不能代替该 verdict。

#### V3 Quality Owner Approval Evidence — 2026-07-29

Quality Owner 收到两页 `200%` 完整 overlay、五张 zoom、完整 report、全部 exact
SHA-256，以及 `FN-03/FN-04/FN-08/FN-11` retained-overlap 风险提示后，明确回复
“批准”。两次 renderer 各自只生成八个文件且逐 byte identical；report 机械验证
`148/244` raw contexts、`132/203` base-area contexts、`80/125` final
observations、`13/16` official batches、`56/56` positives、`16` frozen
negatives、exact-once、全部 crop/member/pixel/area limits、repeatability 和
Provider construction/calls=`0`。

该人工 verdict 按以下 compact、sorted-key canonical JSON 冻结：

```json
{"annotation_status":"approved","manifest_sha256":"0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448","overlay_scale_percent":200,"overlay_sha256":{"page-1-proposal-v3-overlay-200pct.png":"354f61573dd684a7e9883aa66a0fa183750f82e735e30a88eb17994632070e39","page-2-proposal-v3-overlay-200pct.png":"570383d0f500eac266a23a8215f792934070b5cc9d08ddb8c69c03f767534b3d"},"proposal_gate_report_sha256":"95292be8fc086f0ae44487a6ebc460158be5c198abb0c0ed9c8bc21d954eb919","proposal_rule_sha256":"8b7b67f4e303c7cfb7648c9dc2b11530198216f4799ee485f49199f0e99a8cfa","proposal_rule_version":"visual-observation/3","reviewed_frozen_negative_region_count":16,"reviewed_positive_label_count":56,"schema_version":"visual-proposal-gate-verdict/1","unlabeled_target_count":0,"zoom_sha256":{"zoom-core-symbol-representatives.png":"1c247a0e64a26c94075e4b6b791da9d5d5799b206157664441eca1379283b706","zoom-frozen-negative-overlaps.png":"fe53df50630ac85f1293c5a8113f96519b3de995ad6f6e9b75a8e6ab27883540","zoom-gdt-and-boxed-datum.png":"7dfd248718a69604216ccb12f968c22bfddf74bbdcc15a2bc9b140efb36e0b98","zoom-recovered-proposal-gaps.png":"659a066e3e239febea08cb8a947cb99c545af006e1a106b942ef8e6f1d8605ec","zoom-revision-and-n5.png":"f186cb19fdc6a4f49e7670723971f27fbcf6236f016f56d368f890b07b552138"}}
```

canonical verdict SHA-256 为
`05a6e3ac42d5b172e119631940c7df4890950f026ba074f8eda7fa4c539e8e80`。
page 0 / page 1 的 observation-ID SHA-256 分别为
`83d905ec82987c4719f755a1e7a31af246c210a3d4a12113334460c7b9c3a203` /
`a0cc85f52868487d56f108f08e1b6c42eb4b54584759987b32c9bdeef733ffdd`，
ordered batch-membership SHA-256 分别为
`7dcbf89d4903dbe5c90633bef6d7cb6ddecd0317d5280b1c619dca848a8944ca` /
`925a0bc1016be66b5368b284ab8fe81bf7815fab22a597ba87970acf11d9e055`。

该 approval 只关闭 v3 proposal admission visual gate 并授权 proposal-only TDD；
它不声称 production implementation、fresh Provider/live run、frontend、D7-T3
或任意工程图通用准确率已经通过。

#### Old Path Retirement And TDD Boundary

本 amendment 退休：

- “proposal builder 不检查 line text”；
- “每个 geometry-qualified native line 必定形成 visual observation”；
- SR-2A 中只允许替换 packing primitive 的 production Step 3/4。

`pack_visual_batches()` 本身继续保留 stable first-fit。新的 implementation plan
必须按以下顺序执行；stable contract Owner rows 只能在 Quality Owner Step 3
明确批准后由 SR-2B Step 4 修改：

1. exact rule correction 先只提交 accepted design、subordinate plan 和 current
   plan；再生成 overlays/zooms 并取得 Quality Owner verdict，approved 后才由
   Step 4 提交 artifact digests、verdict 和 stable contract Owner rows；
2. PDF RED：三个 geometry admission branches、short-token rescue、noise
   rejection、threshold boundaries、
   v2 ID/order repeatability 和 reconstruction tamper blocking；
3. cache RED：proposal version single source 和 identity invalidation；
4. minimum production implementation in proposal Owner；
5. current-source no-write/no-Provider preflight；
6. ADV-09 overflow/no-Provider、coverage exact-one 和 SR-4 focused regression；
7. independent review 后才允许 SR-4 Step 8。

任一 positive 漏失、frozen negative 误框、digest 不一致、reconstruction mismatch
或 `V > 16` 都回到 design。不得通过放宽 crop/call cap、恢复 full-page Vision、
silent filtering 或 Provider-side semantics 把 failure 改写为 success。

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
- Activation evidence: original Task 0 已由 commit `994cbe4` 激活 subordinate
  proposal；SR-4 exact preflight 随后证明现有 proposal 需要 `19/22` priority
  batches，bounded feasibility 结果为 `capacity_feasibility_unproven`。用户现已批准
  hybrid proposal-gate design 和完整 Quality Owner 重核，旧的 packing-only
  continuation 不再拥有 production authorization。
- Validation action: `pause before SR-2C`。exact rule、两次 evidence run、
  overlays、zooms 和 Quality Owner verdict 已冻结；本 approval turn 不执行
  production RED，也不创建第二套 current plan。
- Writer ownership and order: 同一 backend file group 只有一个 writer，frontend 在
  backend projection 冻结后顺序开始，reviewer 保持只读。
- Next verification: subordinate `SR-2C Step 1` 的 proposal-owner PDF RED；本
  approval turn 在该 step 前停止，不能提交当前 SR-4 worktree changes 或调用
  Provider。

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

hybrid proposal-gate architecture、exact predicate、feature semantics、canonical
rule JSON、rule/report/artifact digests 和 Quality Owner verdict 均已冻结。当前
execution gate 是 `proposal-gate-approved`，只授权按唯一 current plan 从
subordinate `SR-2C Step 1` 进入 proposal-owner TDD；本 approval turn 不执行该
step。仍不得提交当前 SR-4 worktree changes、进入 SR-4 Step 8 或 SR-5、调用
Provider，或把该 current-PDF approval 外推为通用准确率。
