# P0-A2 WELLI Template-Aware Layout Noise Routing Design

## Status And Authority

- Date: `2026-07-30`
- Status: `approved for implementation planning`
- Selected lane: `Heavy`
- Verified base: `main@f9c8c2d`
- Scope: WELLI 固定工程图模板的 Native/high-confidence layout matching、
  table-cell-aware primary disposition 和同页重复水印降噪
- Current parent plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- Immediate predecessor:
  `docs/superpowers/plans/2026-07-30-p0-a1-r1-region-aware-standalone-number.md`
- Execution authorization: 本文只定义 design contract；不修改、替代或 amend
  current plan，也不授权 production code、test、Provider call、runtime config、
  database migration、Harness run、merge 或 export。

本文回答一个有界问题：在用户提供的图纸中，标题栏、更改栏、档案栏、图框编号和
重复水印均来自稳定的 WELLI 表格模板，是否应先用确定性规则过滤噪声。结论是应该，
但规则必须以“模板确认 + 单元格角色 + 工程语义保留”为边界，不能把整块表格矩形
一律删除。

本文已获用户批准进入 implementation planning；仍需通过 implementation plan
approval gate，锁定 task、allowed paths、TDD、回滚和验收命令，才能开始实现。

## Selection Record

- Problem boundary: 当前 P0-A1-R1 只对精确 metadata/比例/剖视标签及粗粒度
  standalone number 区域做 primary disposition，无法识别固定表格的结构角色，
  因而 revision marker、标题栏值和同页网格水印仍进入 candidate 或
  `ambiguous`。
- Single business Owner:
  `backend/app/candidates/disposition.py` 继续拥有 primary disposition；
  proposed layout matcher 只提供确定性 layout evidence，不写 candidate、
  Coverage、review、balloon 或 export。
- Geometry evidence producer:
  `backend/app/pdf/inventory.py::build_inventory()` 必须在 raw
  `page.get_drawings()` 尚可用时调用 matcher，并把最小 immutable match/assignment
  sidecar 保存到 `PageInventory`；Candidate Snapshot 不得重新打开 PDF 或建立第二条
  parser path。
- Old path action: `candidate_snapshot_from_inventory()` 的现有
  technical-requirement、P0-A1-R1 disposition、grouping/parser 和 Coverage 路径
  全部 `preserve`。模板高置信命中时，在既有 generic classifier 之前增加一个
  有界 decision source；模板未命中或证据冲突时，逐 observation 回到现有路径。
- Unchanged contract:
  observation identity/bbox/source relation、Coverage 完整性、candidate/item
  identity、confidence/review、formal numbering、balloon placement、reviewed
  result 和 export 均不改变。
- Provider boundary: layout-resolved 固定表格噪声的预期 VLM 调用数为 `0`；
  其他 unresolved visual sources 继续现有 Advisor path 并单独计数。未来新增 VLM
  能力仍只处理规则与 grouping 后 unresolved 的局部工程标注。
- First future verification: 对一组合成 WELLI page inputs
  （observations + drawings + page size）和一组明确不匹配的 inputs
  运行纯函数测试；匹配页的 revision marker 进入
  `reference_context`，不匹配页输出必须与 P0-A1-R1 baseline 相同。

## Context

### User Problem

当前页面会把大量 Native text box 直接投影为 candidate，继而在审核工作台显示候选
编号。用户提供的样本表明，很多噪声并不是任意版式，而是固定 WELLI 表格中的字段、
更改记录、档案信息、页码和重复水印。因此，第一优先级应是用可解释、可回滚的
layout rule 降噪，而不是把整页交给 VLM。

### Why P0-A1-R1 Is Not Enough

P0-A1-R1 已经完成以下部分：

- 精确 metadata label、比例和剖视标签的确定性 `non_inspection`；
- page-frame standalone number 的 `non_inspection`；
- 右下粗粒度 title-block standalone number 的保守 `ambiguous`；
- drawing body standalone number 恢复到 parser；
- observation、bbox、Coverage identity 和 lineage 保留。

它有意没有实现固定表格 profile、revision table cell roles、同页网格水印、
technical-requirement block grouping 或扫描件支持。因此 P0-A2 是 P0-A1-R1 上游
证据的增强，不是重写 parser 或 balloon 流程。

## Verified Current State

以下状态于 `2026-07-30` 在 `main@f9c8c2d` 和用户提供的 15-PDF corpus 上验证。

### Current Code Path

```text
PDF
  -> backend/app/pdf/inventory.py::build_inventory()
       -> Native line/span TextObservation
       -> page.get_drawings()
       -> VisualObservation proposals
  -> backend/app/processing/runtime_recognition.py
       ::RuntimeRecognition.build_inventory()
       -> hybrid-only bounded OCR
  -> backend/app/processing/automatic_result.py
       ::candidate_snapshot_from_inventory()
       -> technical requirement classifier
       -> classify_primary_disposition()
       -> composite/grouping/parser/coarse fallback
       -> Candidate + CoverageEntry
  -> CandidateAdvisor / confidence / review working copy
  -> provisional candidate marker
  -> freeze
  -> formal balloon / reviewed result / export
```

### Code Evidence

| Evidence | Current behavior | Consequence |
| --- | --- | --- |
| `backend/app/pdf/inventory.py::build_inventory()` | 从 PyMuPDF text dict 创建 immutable Native line/span observations；span 的 `parent_region_id` 指向 line observation | `parent_region_id` 已被 source lineage 使用，不能复用为 layout region |
| `backend/app/pdf/inventory.py::build_inventory()` | raw `page.get_drawings()` 只在 inventory 构建期间可用，当前不会保存到 `PageInventory` | matcher 必须在该函数内运行，并只保存 reduced/versioned match evidence |
| `backend/app/pdf/schemas.py::TextObservation` | 已有 ID、source type、raw/normalized text、page、PDF/normalized bbox、direction、confidence | P0-A2 不需要重造 Observation model |
| `backend/app/pdf/schemas.py::PageInventory` | 当前没有 layout match 或 table-cell assignment 字段 | P0-A2 需要一个 optional additive sidecar；不能要求 downstream 凭空取得 drawings |
| `backend/app/processing/runtime_recognition.py::RuntimeRecognition.build_inventory()` | 只对 `processing_route=="hybrid"` 且非 `unsupported` 页面调用 OCR | 当前两个 scanned/unsupported 页面不会进入 OCR |
| `backend/app/processing/automatic_result.py::candidate_snapshot_from_inventory()` | 先建立 visual-context IDs；逐 observation 执行 requirement、primary disposition、composite/group/parser | layout decision 的最小 consumer seam 已存在 |
| `backend/app/candidates/disposition.py::classify_primary_disposition()` | `has_visual_context=true` 时 standalone number 交回 parser | revision triangle 关联的 `1/2/3` 会绕过 number noise gate |
| `backend/app/candidates/disposition.py::repeated_page_overlay_observation_ids()` | 只确认跨不同页面、相同位置的 repeated overlay | 同一页规则网格中的 `伟立机器人` 不会被确认成水印 |
| `backend/app/candidates/coverage.py::Disposition` | 已支持 `candidate/reference_context/non_inspection/ambiguous` | 不需新增 disposition enum |
| `backend/app/candidates/disposition.py::PrimaryDispositionDecision` | 当前只允许 `non_inspection/ambiguous` | implementation 若提交 `reference_context`，需最小扩展该内部 decision type |
| `backend/app/candidates/coverage.py::CoverageEntry` | 已保存 observation ID、source、coordinates、reason 和 rule version | 可以审计规则结果，不得静默删除 observation |
| `docs/contracts/MAIN_CONTRACT_MATRIX.md::PDF-002/PDF-006` | Native/OCR 使用 canonical PDF bbox，互不覆盖 | layout 只能消费 bbox，不能改写 bbox |
| `docs/contracts/MAIN_CONTRACT_MATRIX.md::CAND-002/CAND-005` | 每个工程相关 group 恰有一个 disposition，所有疑似 source 必须被 Coverage 覆盖 | layout filter 必须是 disposition，不是删除 |
| `docs/contracts/MAIN_CONTRACT_MATRIX.md::PROV-002` | OCR 是 Signal Provider，VLM 是 Advisor | VLM 不得拥有表格 disposition 或正式业务语义 |

### Real Corpus Inventory

用户提供的 corpus 共 `15` 个 PDF、`17` 页：

| Profile | Pages | Current support |
| --- | ---: | --- |
| A3 landscape | 12 | 11 parseable，1 scanned/unsupported |
| A4 portrait | 4 | 3 parseable，1 scanned/unsupported |
| A3 portrait | 1 | 1 parseable |
| Total | 17 | 15 parseable，2 scanned/unsupported |

15 个 parseable 页面中：

- `14` 页为 vector/native；
- `1` 页为 hybrid/hybrid；
- 所有页面都命中 title anchor group：
  `物料编码/图样代号/比例/重量`；
- 所有页面都命中 revision anchor group：
  `标记/更改描述`；
- 所有页面都命中 archive anchor：
  `旧底图总号`。

当前对全部 17 页执行 `build_inventory()` 和
`candidate_snapshot_from_inventory()` 的 diagnostic baseline：

| Metric | Current count |
| --- | ---: |
| Coverage entries | 3646 |
| Candidates | 1312 |
| Ambiguous | 2193 |
| Non-inspection | 141 |

这些数字是同一开发 corpus 的当前代码诊断，不是 Quality Owner ground truth，
不能直接称为 candidate precision/recall。

### Confirmed Candidate Leakage

在 parseable pages 中，当前有 `57` 个 candidate 的 source center 落入已确认模板
区域：

| Region | Current candidates | Safe P0-A2 action |
| --- | ---: | --- |
| Revision table | 47 | 45 个 marker number 为 `reference_context`；1 个普通变更描述为 `reference_context`；1 个工程例外必须保留 |
| Title block | 7 | 已知 metadata value cell 为 `reference_context` |
| Page frame | 3 | page/frame zone number 为 `non_inspection` |
| Archive strip | 0 | 当前无 candidate；仍需路由 observation-level 噪声 |

因此当前 corpus 上可安全移出 candidate path 的精确上界是 `56`，不是 `57`。

必须保留的例外位于一张上插臂图纸的 revision description row：空白更改栏单元格被
复用于工程标注 `其余 3.2`。这证明“revision rectangle 全部
reference_context/non_inspection”会删除真实工程语义。P0-A2 必须按 cell role 和
engineering-preservation evidence 决策。

### Confirmed Ambiguous Load

当前至少有以下 observation-level 模板内容留在 generic `ambiguous`：

| Class | Current ambiguous observations |
| --- | ---: |
| Title block | 415 |
| Archive strip | 88 |
| Same-page `伟立机器人` watermarks | 184 |
| Revision fixed headers | at least 30 |
| Total deterministic opportunity | at least 717 |

这组计数包含 Native line/span 层级，表示人工 review load，不等于独立 inspection
item 数。

### Technical Requirement Residual

corpus 中有 `13` 个 `技术要求` heading 和 `64` 个编号 requirement lines。
现有 classifier 只把同时含 inspection verb 和 verifiable criterion 的单行转成
`global_requirement`，因此：

- `62` 条仍为 `ambiguous`；
- `2` 条只形成 coarse weld candidate；
- heading 位置跨页面变化明显，不能用固定矩形过滤。

技术要求是工程内容，不能被 P0-A2 标为 `non_inspection`。完整 block grouping
属于独立 P0-A2b/P0-B design，不在本文实现范围。

## Root Cause Analysis

### Detection

Native inventory 正确地高召回保留 line/span text，但 observation 只表达文字事实，
没有表格 cell role。问题不是“Native 检测太多”，而是下游缺少 layout evidence。

### Layout And Grouping

当前只存在粗粒度 normalized-position rule，没有 versioned drawing profile、vector
grid match 或 anchor quorum。revision marker 的 triangle 还会产生 visual context，
使裸数字优先交给 parser。

### Disposition

P0-A1-R1 的 exact-text rules 能过滤 label，却无法根据同一 cell 的语义解释 field
value。`260508` 在 drawing body 可能是工程数字，在 confirmed date/material cell
则只是 reference context。

### Watermark

当前 repeated-overlay rule 要求至少两个不同 page index。同页 9～14 次的斜向网格
水印不满足条件，即使文字、角度和布局高度稳定。

### Item And Balloon

candidate 进入 working copy 后会获得 provisional marker；该 marker 不是 formal
balloon，但会让噪声在 UI 中显得像已识别检验项。P0-A2 的目标是从 candidate source
上游减少错误，不修改 numbering、freeze 或 formal balloon Owner。

## Goals

1. 只在高置信 WELLI profile match 后解释固定表格 cell role。
2. 把确定性 metadata/reference、revision control、archive、page-frame 和 watermark
   observation 从 candidate path 移到明确 disposition。
3. 保留每个 observation 的 identity、bbox、source relation 和 Coverage entry。
4. 对模板边界、未知 cell、证据冲突和工程语义保持 conservative fallback。
5. 保证 `其余 3.2`、普通尺寸、公差、半径、螺纹、GD&T 和技术要求不因表格规则被
   删除。
6. 相同 code/input 得到 byte-identical profile match、disposition 和 candidate
   snapshot。
7. 模板不匹配时保持 P0-A1-R1 行为不变。

## Non-Goals

- 不实现 scanned/unsupported 页面的 OCR 主链或 raster table detection。
- 不完成 technical-requirement block grouping 或 semantic normalization。
- 不完成复合孔、上下公差、GD&T 等通用 grouping hardening。
- 不新增或调用 VLM/LLM Provider。
- 不修改 Observation identity、canonical PDF bbox 或 OCR projection。
- 不原地覆盖 Native/OCR observation。
- 不创建正式 InspectionItem、ReviewedResult、formal number 或 balloon geometry。
- 不修改 frontend marker、review command、freeze、balloon、PDF/Excel/manifest export。
- 不把 WELLI 三个 variant 泛化为任意供应商的通用表格识别器。
- 不把当前 15-PDF development corpus 声称为 blind/holdout 或正式质量基线。
- 不新增运行时 feature flag、配置中心、规则管理后台或数据库 schema。

## Target Architecture

```text
PDF bytes
  |
  v
Native PageInventory Owner
  |  build_inventory() still owns raw drawings
  +-> WELLI Layout Profile Matcher
  |     TextObservation + vector drawings + page size
  |     -> reduced immutable LayoutProfileMatch
  v
PageInventory
  |  TextObservation + optional versioned layout sidecar
  v
Observation Region/Cell Assignment
  |  observation_id -> region_id/cell_role/cell_id/evidence
  v
Technical Requirement Existing Classifier
  |  matched requirement -> existing global requirement candidate
  |  otherwise
  v
Existing Exact Metadata/Scale/Section Rules
  |  matched exact noise -> existing non_inspection decision
  |  otherwise
  v
Template-Aware Disposition Policy
  |  safe exact cell -> reference_context/non_inspection
  |  engineering evidence / conflict / edge -> no decision
  v
Same-Page Watermark Policy
  |  exact text + angle + grid evidence -> non_inspection
  v
Remaining P0-A1-R1 Number/Roman/Repeated-Text Rules
  v
Existing composite/grouping/parser/coarse fallback
  v
CandidateSnapshot + complete Coverage Ledger
  |  text dispositions + layout-resolved visual dispositions
  |  required_visual_observation_ids = unresolved visual sources only
  v
Visual batch planner / CandidateAdvisor
  |  schedules and projects required visual IDs only
  v
Existing confidence/review/balloon/export path
```

### Owner Boundaries

| Component | Owns | Must not own |
| --- | --- | --- |
| Native Inventory Owner | 调用 matcher并把 reduced optional sidecar写入 `PageInventory` | 在 Candidate Snapshot 中重新打开 PDF、保存无界 raw drawings |
| Layout Profile Matcher | page/profile match 和 cell-assignment evidence | disposition、candidate、Coverage、review、balloon |
| Region/Cell Assigner | observation-to-cell relation and evidence | source observation mutation、semantic exclusion |
| Primary Disposition Owner | final per-observation rule decision | formal item/review/number/export |
| Candidate Snapshot Owner | orchestration and one Coverage write per selected source | profile geometry definitions duplicated inline |
| Coverage Owner | source identity, disposition, reason/version, confirmation state | silently dropping observations |
| Visual Batch Planner | 只调度 `required_visual_observation_ids` | 把 layout-resolved visual source 重新升级为 VLM request |
| CandidateAdvisor | 只投影已调度的 unresolved visual sources | 覆盖 layout-resolved visual Coverage disposition |
| VLM Advisor | future local suggestion only | profile match、formal coordinates、final disposition or business write |

## Layout Profile Contract

### Canonical Units

Profile geometry Owner 使用 physical PDF millimetres；运行时从 canonical PDF points
转换。normalized bbox 只用于诊断和 UI，不作为 profile geometry 的唯一 truth。

页面尺寸容差：`±0.5 mm`。vector grid line/boundary 容差：`±1.0 mm`。

### Supported Variants

三个 variant 共享同一 WELLI 物理表格结构：

| Profile ID | Page size/orientation | Title block | Revision table | Archive strip | Body frame |
| --- | --- | --- | --- | --- | --- |
| `welli-a3-landscape/1` | `420×297 mm` landscape | `[W-185,H-61,W-5,H-5]` | `[W-95,5,W-5,40]` | `[0,H-107,25,H-5]` | `[25,5,W-5,H-5]` |
| `welli-a4-portrait/1` | `210×297 mm` portrait | same physical rule | same physical rule | same physical rule | same physical rule |
| `welli-a3-portrait/1` | `297×420 mm` portrait | same physical rule | same physical rule | same physical rule | same physical rule |

矩形格式为 `[x0,y0,x1,y1]`，原点和方向遵守 `PDF-002`。

对应当前 corpus 的 normalized diagnostic boxes：

| Profile | Title | Revision | Archive | Body |
| --- | --- | --- | --- | --- |
| A3 landscape | `[0.5595,0.7946,0.9880,0.9833]` | `[0.7743,0.0169,0.9880,0.1347]` | `[0,0.6397,0.0595,0.9833]` | `[0.0595,0.0169,0.9880,0.9833]` |
| A4 portrait | `[0.1189,0.7946,0.9762,0.9833]` | `[0.5487,0.0169,0.9762,0.1347]` | `[0,0.6397,0.1189,0.9833]` | `[0.1189,0.0169,0.9762,0.9833]` |
| A3 portrait | `[0.3770,0.8548,0.9831,0.9882]` | `[0.6810,0.0120,0.9831,0.0953]` | `[0,0.7452,0.0841,0.9882]` | `[0.0841,0.0120,0.9831,0.9882]` |

normalized values 是 regression evidence，不是第二套 profile Owner。

### Stable Grid And Cell-Role Map

以下坐标均相对各 region 左上角，以 mm 表示。它们在 15/15 parseable pages 上命中。

#### Title Block

mandatory grid：

```text
x = 0,12,24,40,52,64,80,106,118,130,144,180
y = 0,7,14,18,21,28,35,38,42,47,49,56
```

`x=93` 只在 14/15 页出现，不得作为 match gate 或 mandatory cell boundary。

P0-A2 的最小安全 role map：

| Local area | Role | Policy |
| --- | --- | --- |
| `0 <= x < 80` | `title_approval_context` | exact metadata labels 保持既有规则；其余 line 为 `reference_context` |
| `80 <= x <= 180` 且为 exact fixed label | existing exact label role | 保持 existing metadata/scale rule |
| `80 <= x <= 180` 的其余唯一 cell/merged-cell line | `title_metadata_value` | `reference_context` |

title fixed-label allowlist 在统一空白和兼容字符后精确匹配：

```text
更改文件号
版本号
设计
签名
年月日标准化
年月日
校对
工艺
批准
审核
重量
重量/kg
比例
图样代号
物料编码
第一角法
表面积
共张
第张
```

这些 label 为 `non_inspection`。不做 substring match；`重量/kg` 与 `重量` 是两个
明确 variant。

这里的 x 指 observation center 的 local x，但仍必须通过下文完整 assignment gate。
title role 不依赖 filename、drawing number 或 value text allowlist。

#### Revision Table

mandatory grid：

```text
x = 0,10,90
y = 0,5,15,25,35
```

精确 role map：

| Local rectangle | Role |
| --- | --- |
| `[0,0,90,5]` | `revision_header` |
| `[0,5,10,15]` | `revision_marker` |
| `[0,15,10,25]` | `revision_marker` |
| `[0,25,10,35]` | `revision_marker` |
| `[10,5,90,15]` | `revision_description` |
| `[10,15,90,25]` | `revision_description` |
| `[10,25,90,35]` | `revision_description` |

marker rule 只接受三行各自对应的 exact `1/2/3`。description role 在
engineering-preservation gate 命中时不得提交 layout disposition。

#### Archive Strip

mandatory grid：

```text
x = 0,25
y = 0,7,17,24,34,41,51,58,68,75,85,92,102
```

y 方向为交替 `7 mm` label row 和 `10 mm` record row：

| Local y rows | Role | Policy |
| --- | --- | --- |
| `[0,7] [17,24] [34,41] [51,58] [68,75] [85,92]` | archive fixed labels | exact label 为 `non_inspection` |
| `[7,17] [24,34] [41,51] [58,68] [75,85] [92,102]` | `archive_record` | unique assigned line 为 `reference_context` |

fixed labels 依次为 `借通用件登记/描图/校描/旧底图总号/签字/日期`。其中
`借通用件登记` 在一个 A4 page 缺失，因此不是 mandatory text anchor；grid 仍必须
命中。任何跨 row line、rotation conflict 或越过 outer boundary 的 source 不赋
role。当前 record cells 基本为空，P0-A2 只路由已有文本，不做字段解析。

#### Page Frame Numbers

对 15 个 parseable pages 的 `60/60` frame-zone labels，稳定 pattern 为：

```text
top band:    0 <= center_y <= 5 mm
bottom band: H-5 mm <= center_y <= H
text "1":    abs(center_x - W/4) <= 1 mm
text "2":    abs(center_x - 3W/4) <= 1 mm
```

只有 exact standalone `1/2` 同时命中 y band 和 x target 才赋
`page_frame_number`；其他 page-edge 工程标注继续 P0-A1-R1 conservative path。
page-frame band 和 x target 使用已通过 profile size tolerance 的实际 page `W/H`，
不把 nominal profile size 与解析器返回值之间的浮点差异解释为越界。精确
cell/text/target 已同时命中时，line 接触 actual physical page outer edge 是允许的；
这项例外不适用于内部 cell boundary 或其他 role。

### Observation-To-Cell Assignment

P0-A2 assignment grain 固定为 Native `observation_level=="line"`，与
`automatic_result._selected_observations()` 当前正式 text grain 一致。Native span
只保留 parent/source lineage，不参与 cell count；后追加 OCR 不在 P0-A2 profile
assignment 范围。

每个 line 必须同时满足：

1. bbox center 位于一个 unexpanded base cell 或一个明确的 same-role merged-cell
   union 内；
2. 完整 bbox 位于该 unexpanded role union 内；
3. line 接触的所有 base cells 具有相同 role；
4. 不存在第二个 role 同时满足；
5. title/revision/archive/page-frame line 的 direction angle 为 `0° ±2°`；
6. line/parent relation、bbox 和 profile page_index 无冲突。

若 line 越过 role union、跨越不同 role、只靠 bbox overlap 命中、merged cell role
不唯一或 title optional `x=93` 造成两种解释，则不创建 assignment。
`boundary_distance_mm` 为相对 unexpanded role union 的 signed inward distance；
assignment 中只允许非负值。`0..1 mm` 表示位于 grid tolerance band 内侧，
assignment 可保留用于诊断，且除精确 `page_frame_number` 接触 actual physical
page outer edge 外，disposition 必须 veto；负值一律不创建 assignment。不得用
“center 落进整块 title/revision rectangle”替代 cell assignment。

### Match Gate

只有同时满足以下条件才返回 `match_state=high_confidence`：

1. page size/orientation 命中一个且仅一个 supported variant；
2. body frame 命中；
3. title/revision/archive 三组 region geometry 至少命中两组；
4. text anchor groups 至少命中两组：
   - title group：`物料编码/图样代号/比例/重量` 至少 `3/4`；
   - revision group：`标记/更改描述` 必须 `2/2`；
   - archive group：`旧底图总号` 必须 `1/1`；
5. 不存在另一个 profile 同分、关键 grid 缺失或 boundary conflict。

matcher 结果只有：

```text
LayoutProfileMatch(high_confidence)
None (no_match)
```

P0-A2 不引入可直接过滤的 medium state。证据不足一律 `no_match`，回到现有路径。
只有 page size 相同不能触发 profile。

### Additive PageInventory Sidecar

P0-A2 使用 optional immutable sidecar，不修改 `TextObservation`。data shapes 由
`backend/app/pdf/schemas.py` 定义，算法和 profile constants 由
`backend/app/pdf/layout_profiles.py` 唯一拥有：

```python
@dataclass(frozen=True)
class LayoutProfileMatch:
    page_index: int
    profile_id: str
    match_state: Literal["high_confidence"]
    geometry_evidence_codes: tuple[str, ...]
    text_anchor_evidence_codes: tuple[str, ...]
    assignments: tuple[ObservationRegionAssignment, ...]
    rule_version: str


@dataclass(frozen=True)
class ObservationRegionAssignment:
    observation_id: str
    page_index: int
    profile_id: str
    region_id: Literal[
        "title_block",
        "revision_table",
        "archive_strip",
        "page_frame",
    ]
    cell_role: str
    cell_id: str
    assignment_evidence_codes: tuple[str, ...]
    boundary_distance_mm: float
    rule_version: str


@dataclass(frozen=True)
class PageInventory:
    # existing fields unchanged
    layout_profile_match: LayoutProfileMatch | None = None
```

`build_inventory()` 在构建每页 inventory 时恰调用 matcher 一次；matcher 只接收
当前 page 的 observations、raw drawings、page size 和 transform，不读取 filename、
source basename、page index allowlist 或 source hash special case。它只保存最小
profile/geometry/anchor/assignment evidence，不保存 raw drawings。

matcher 返回 `None` 时，`PageInventory.layout_profile_match` 同样为 `None`。
`PageInventory.to_dict()` 在 sidecar 为 `None` 时省略该字段，保证 no-match/未启用
路径的旧序列化不变；high-confidence match 时输出 versioned additive evidence。
`append_ocr_observations()` 必须保留已有 sidecar，不重新匹配。P0-A2 assignments
只覆盖 matcher 当时存在的 Native observations；后追加 OCR 继续现有 conservative
path。

这些 sidecar 只提供 evidence。最终 business trace 继续写入现有
`CoverageEntry.disposition_reason/disposition_rule_version`。不得把
`TextObservation.parent_region_id` 改成 layout region。

`cell_id` 是同一 profile 内稳定的 cell identity，例如：

```text
revision-marker-1
revision-description-1
revision-marker-2
revision-description-2
revision-marker-3
revision-description-3
```

row-level engineering veto 必须按 `cell_id` 聚合，不能在 Candidate Snapshot 重新
硬编码 revision geometry，也不能从 diagnostic evidence code 反解析业务 identity。

该 optional additive field 实现 `PDF-007` 已定义的 region identity/evidence，不新增
业务 Owner、数据库 column 或 public API。successor plan 必须同步现有 page-inventory
serialization/contract tests；若 implementation 还要求数据库持久化字段或公开 API，
必须另行 amend contract matrix 和 schema，不得静默扩展。

## Cell-Aware Disposition Policy

### Decision Precedence

Primary Disposition Owner 内部的顺序固定为：

1. existing technical requirement classifier；
2. existing exact metadata、drawing scale 和 section-view rules；
3. high-confidence template cell policy；
4. same-page WELLI watermark policy；
5. remaining P0-A1-R1 standalone number、Roman label 和 cross-page repeated-text
   rules；
6. existing composite/grouping/parser/coarse fallback。

这样 `1:10`、`A-A`、`设计` 等已稳定规则不改变；revision marker `1/2/3` 和
page-frame number 则能在 generic number/visual-context yield 之前由 confirmed
cell role 处理。

### Engineering-Preservation Gate

现有 executable technical requirement 对所有 role 保持最高优先级。bbox 跨 cell、
方向异常、cell role 不唯一或同一 source 的 line/span assignment 冲突时不创建
layout decision；除下述精确 page-frame outer-edge 例外外，距离内部 role boundary
小于 `1 mm` 同样返回 no decision。

parser/grouping/visual engineering preservation 只适用于 `revision_description` row：

- 现有 parser/grouping 能识别为工程标注；
- 关联的 VisualObservation 表达非 revision-control 的工程符号上下文。

title metadata/approval、archive record 等 role 不因 generic parser 把日期、编号或
重量值解释为 engineering shape 而失去已确认的 cell policy。coarse keyword/type
fallback 本身也不是 revision engineering evidence；例如 plain change prose
不能只因包含 `焊接` 等词而被保留为 candidate。

此时 policy 返回 no decision，继续现有 classifier/parser；若现有路径仍不能解释，
Coverage 保持 `ambiguous/requires_confirmation=true`。

revision description 的 veto 按整行 cell 执行：同一 description row 内只要一个
Native line 命中 parser/technical/visual engineering evidence，该 row 的其他
Native lines 也全部返回 no decision。这样不会把复合标注中未单独可解析的文字片段
降为 context。

当前 `其余 3.2` 的真实 inventory evidence 是两个独立 Native line，而不是 parser
直接收到一条完整字符串：

| Text | Revision-local bbox mm | Existing evidence |
| --- | --- | --- |
| `3.2` | approximately `[78.6,25.4,83.2,29.8]` | standalone number 可被 existing parser 识别，并关联 VisualObservation |
| `其余` | approximately `[71.5,29.0,77.8,33.5]` | 与 `3.2` 同属第三个 description row，并关联 overlapping VisualObservation context |

因此通用 preservation rule 是“description-row engineering evidence veto”，不是
filename、source hash、page index、observation ID 或 exact sample text 特判。marker
cell 对应的 exact `1/2/3` 是唯一允许覆盖 visual-context yield 的 revision-control
例外。另一个 control-role 例外是精确 page-frame cell/text/target：它可以接触
actual physical page outer edge，并优先于 visual-context yield；内部边界仍不得
放宽。

### Decision Table

| High-confidence cell/evidence | Disposition | Reason | Notes |
| --- | --- | --- | --- |
| Existing exact metadata labels | `non_inspection` | existing `exact_metadata_label` | 保持 P0-A1-R1，不改变 |
| Title metadata value cell | `reference_context` | `welli_title_metadata_value` | 物料/图号/重量/材料/日期等，不创建 candidate；精确比例继续使用 existing `drawing_scale` |
| Title signature/name/date value cell | `reference_context` | `welli_title_approval_context` | 不作为 inspection item |
| Revision fixed header cell | `non_inspection` | `welli_revision_header` | exact `标记/更改描述` |
| Revision marker column exact row integer | `reference_context` | `welli_revision_marker` | row 1/2/3 对应 exact 1/2/3；即使 triangle 产生 visual context，也由 confirmed marker-cell role 覆盖 |
| Revision description plain change prose | `reference_context` | `welli_revision_description` | 只有 engineering-preservation gate 未命中才适用 |
| Revision row engineering annotation | no decision | none | `其余 3.2` 必须继续现有工程识别链 |
| Archive fixed label cell | `non_inspection` | `welli_archive_label` | exact allowlist + exact label row |
| Archive record cell | `reference_context` | `welli_archive_record` | 仅在 exact record-row assignment 时适用 |
| Page-frame zone/page number | `non_inspection` | `welli_page_frame_number` | confirmed profile 优先于 visual-context yield |
| Same-page WELLI watermark | `non_inspection` | `welli_same_page_watermark` | 需满足独立 watermark contract |
| Unknown/merged/edge/conflict cell | no decision | none | 回到 P0-A1-R1 或 `ambiguous` |
| Drawing body | no decision | none | 现有 technical/grouping/parser path 完全不变 |

统一 rule version 建议：

```text
p0-a2-welli-layout/1
```

`reference_context` 不是 candidate，也不是不可恢复删除；它必须保留 source location
和 Coverage relation，未来可以被 item/group 引用。

## Layout-Resolved Visual Observation Contract

固定表格文字附近的 triangle、cell border 或其他 vector context 可能已经形成
`VisualObservation`。只改变 text disposition 不足以阻止这些 visual sources 进入
Advisor。

Candidate Snapshot 必须为每个 visual source执行以下确定性关系判定：

1. `associated_text_observation_ids` 非空；
2. 先把合法 Native span relation canonicalize 到已选中的 Native line：
   - span 与 parent line 同页；
   - `span.parent_region_id` 指向该 parent line；
   - visual 同时显式关联 span 和 parent line；
   - parent line 是 Candidate Snapshot 当前 selected observation；
3. orphan、跨页、parent 未被同一 visual 关联或 parent identity 冲突的 span 不能折叠，
   整个 visual relation 保持 unresolved；
4. 去重后的 canonical Native line IDs 都在同一 high-confidence layout match 中；
5. 每个 canonical line 都已有非候选的 layout-safe decision；
6. 任一 canonical line 不在 engineering-preservation set；
7. 不存在 candidate/ambiguous/missing/conflicting text relation。

canonical relation projection 只解决现有 visual proposal 的 line/span source lineage；
它不为 span 新建 Coverage entry，不修改 `associated_text_observation_ids`，也不改变
Candidate Snapshot 仍以 Native line 为正式 text grain 的合同。

全部满足时：

- 若所有关联 text 都是 `non_inspection`，visual source 也为
  `non_inspection/welli_layout_visual_context`；
- 否则 visual source 为
  `reference_context/welli_layout_visual_context`；
- visual source 仍保留自己的 identity、bbox、Coverage entry 和 relation；
- visual ID 不进入 `required_visual_observation_ids`。

任一条件不满足时，visual source 保持现有
`ambiguous/requires_confirmation=true`，并继续进入
`required_visual_observation_ids`。

下游必须机械遵守该集合：

```text
plan_visual_batches()
  -> only required_visual_observation_ids

CandidateAdvisor visual projection
  -> only scheduled/required visual observations

layout-resolved visual observations
  -> preserve existing Coverage decision
```

不得仅在 batch planner 过滤后，又让 `project_visual_page()` 以
`visual_no_detection` 覆盖这些 source。

## Same-Page Watermark Contract

只有同一 page 上的 Native observations 同时满足以下条件，才判为
`welli_same_page_watermark`：

1. normalized text 精确等于 `伟立机器人`；
2. direction angle 为 `-30° ±2°`；
3. 同页 unique Native line count `>=9`；
4. centers 中存在至少 `9` 个 unique inliers，形成至少 `2×3` 的规则网格；
5. spacing variance 在 versioned deterministic tolerance 内；
6. observation 不在技术要求或其他工程文本 group 中。

watermark observation grain 固定为 unique Native line observations；不得把同一
line 的 span 再计一次。按 profile 的预期相邻 center spacing 为：

| Profile | X spacing | Y spacing | Tolerance |
| --- | ---: | ---: | ---: |
| A3 landscape | `100 mm` | `80 mm` | `±2 mm` |
| A4 portrait | `65 mm` | `80 mm` | `±2 mm` |
| A3 portrait | `100 mm` | `90 mm` | `±2 mm` |

只有某个 deterministic origin 下至少 `9` 个 unique centers 占据至少两列、三行，
且相邻 spacing 同时满足对应 profile，才通过 page-level lattice quorum。页面边缘
允许缺少被裁切的外侧点，也允许存在不完整 outer row；它们不得降低 count 或 spacing
gate，也不得因为不能共同确定全页最小 origin 而否决已经成立的 quorum。page-level
quorum 成立后，同页全部满足 exact text、angle 和非工程 group 条件的 unique Native
lines 都按本 rule 路由。当前 corpus 的 14 个含水印 parseable pages 上共有 `184`
条满足文字、角度和网格模式的 Native line observations，每页为 `9～14` 次。不得
使用 substring match，因为工程文本中可能出现相近词；水平 logo 也不得被本规则捕获。

P0-A2 不把任意倾斜重复文字泛化为水印。其他文字继续走现有跨页 repeated-overlay
规则或 `ambiguous`。

## Technical Requirement Boundary

P0-A2 只保证不破坏技术要求，不在本 spec 中完成 block grouping。

后续独立 design 应采用：

```text
exact 技术要求 heading
  -> same direction and indentation
  -> consecutive numbered lines 1,2,3...
  -> bounded continuation lines
  -> stop at profile region boundary / abnormal gap / numbering break
```

该后续结果应形成 source-linked global requirement group，通常
`balloon_required=false`，但不得由 P0-A2 table filter 预先删除。

## VLM Boundary

### P0-A2

固定表格 layout、cell role、page-frame number 和 watermark 均由 deterministic
rule 处理：

```text
layout-resolved source eligible Provider batches = 0
layout-resolved source attributable Provider calls = 0
unresolved source Provider calls = existing path, reported separately
```

### Future Advisor Seam

未来局部 VLM 的正确插入点仍是：

```text
Native/OCR observations
  -> deterministic layout noise routing
  -> deterministic technical/grouping/parser
  -> unresolved ambiguous/complex local group
  -> bounded crop + observation IDs
  -> VisionLlmProvider suggestion
  -> deterministic validator
  -> CandidateAdvisor single write
  -> human review
```

VLM 不得：

- 匹配正式 WELLI profile 或直接提交 disposition；
- 覆盖 Native/OCR observation；
- 生成正式 identity、InspectionItem、ReviewedResult 或 formal balloon number；
- 返回正式 PDF coordinate 作为唯一依据；
- 决定 `balloon_center_pdf`；
- 绕过 human review、freeze 或 export gate。

未来 local crop 还必须排除无关标题栏、签字、物料和档案信息；P0-A2 先用规则移除
这些区域，亦能减少 Provider privacy surface。

## Proposed Code Surface

下列只是 design-level ownership mapping，不是 implementation authorization：

| File | Intended responsibility |
| --- | --- |
| `backend/app/pdf/layout_profiles.py` | 新增 WELLI profile、geometry/anchor match、region/cell assignment 的唯一 Owner |
| `backend/app/pdf/schemas.py` | 新增 optional additive `LayoutProfileMatch` / `ObservationRegionAssignment` shapes 和 `PageInventory` sidecar |
| `backend/app/pdf/inventory.py` | 在 raw drawings 尚可用时调用 matcher；只保存 reduced evidence |
| `backend/app/candidates/disposition.py` | 消费 assignment，提交 template-aware primary disposition；内部 decision 支持 `reference_context` |
| `backend/app/processing/automatic_result.py` | 只消费 inventory 已保存的 match/assignments，并在现有 path 中编排；不得重读 PDF |
| `backend/app/candidates/symbol_review.py` | visual batch planner 只调度 snapshot 明确 required 的 visual IDs |
| `backend/app/candidates/advisor.py` | 只 project required visual IDs，保留 layout-resolved Coverage |
| `backend/tests/unit/pdf/test_inventory.py` | sidecar producer/serialization/no-match compatibility |
| `backend/tests/unit/pdf/test_layout_profiles.py` | profile、tolerance、anchor quorum、cell assignment、no-match tests |
| `backend/tests/unit/candidates/test_disposition.py` | decision table、engineering exception、watermark and precedence tests |
| `backend/tests/unit/candidates/test_symbol_advisor.py` | required-visual scheduling 和 resolved-visual non-projection |
| `backend/tests/e2e/test_offline_automatic_result.py` | candidate/Coverage integration、fallback determinism |

P0-A2 不应修改：

- review、confidence、balloon、export、frontend modules；
- Provider ports/adapters/schema；
- database migration；
- historical Harness receipt 或 sealed run evidence；
- current implementation plan，直到 design 获批并进入 replan gate。

## Acceptance Criteria

### Deterministic Unit Contract

1. 三个 supported page-size variants 在 `±0.5 mm` 内可匹配，超出即 no-match。
2. grid/region boundary 在 `±1 mm` 内可匹配，超出或 conflict 即 no-match。
3. 只有 page size、只有 text anchor 或只有 geometry 均不能触发 high-confidence。
4. profile/cell assignment 不修改任何 `TextObservation` 字段。
5. `parent_region_id` 继续只表达现有 source lineage。
6. no-match/sidecar-absent page inventory serialization 与 P0-A1-R1
   byte-identical；Candidate Snapshot 不重新打开 source PDF。
7. matcher/assigner 不读取 filename、basename、source hash、page allowlist 或
   sample-specific special case。
8. bbox 只命中整块 region、跨不同 roles 或只有 overlap 时不产生 assignment。
9. table/page-frame line angle 超出 `0° ±2°` 时不产生 assignment。
10. Native line/span 对同一水印只能计数一次；spacing 超出 `±2 mm` 时不判水印。
11. marker cell 的对应 `1/2/3` 即使有 visual context 也进入
    `reference_context/welli_revision_marker`。
12. revision description 的真实 split-line `其余` + `3.2` bundle 触发整行 veto，
    两个 observation 均不进入 table noise disposition。
13. unmatched page 的 snapshot 与 P0-A1-R1 baseline byte-identical。
14. layout-resolved visual source 保留 Coverage identity/disposition，不进入
    `required_visual_observation_ids`、VLM batch 或 Advisor projection。
15. unresolved/mixed-relation visual source 仍为 `ambiguous` 且必须进入 required set。
16. 真实 `line + child spans` visual relation 可稳定折叠到 selected Native line；
    orphan、跨页、parent 未显式关联或 identity 冲突的 span 必须 fail closed。

### Current Corpus Diagnostic Gate

在固定 code/input 下，15 个 parseable pages 必须全部 high-confidence match；2 个
scanned/unsupported pages 必须保持明确 residual，不得伪装成功。

对 parseable pages：

1. 当前 `45` 个 revision marker candidates 不再进入 candidate/balloon-required path。
2. 当前 `1` 个普通 revision description candidate 进入 `reference_context`。
3. 当前 `7` 个 title metadata value candidates 进入 `reference_context`。
4. 当前 `3` 个 page-frame candidates 进入 `non_inspection`。
5. 当前 `184` 个 WELLI watermark observations 进入
   `non_inspection/welli_same_page_watermark`。
6. `其余 3.2` 保持 source-covered，并继续形成工程 candidate 或可审核
   `ambiguous`；不得成为 table noise。
7. 所有原有 selected observations 仍恰有 Coverage entry；blocking coverage 不增加。
8. 相同 code/input 连续两次 canonical snapshot byte-identical。
9. 与已路由 title/revision/archive/page-frame noise 关联的 visual sources 不进入
   Provider batch；其他 unresolved visual sources 的 required coverage 不减少。

上述 gate 证明 deterministic prefilter 行为，不证明正式 candidate precision、
post-Advisor precision、reviewed result 或交付文件正确性。

### No Regression

以下输入在 drawing body 继续现有路径：

```text
25
Φ20
M6
R5
25±0.02
普通上下公差
GD&T / roughness visual context
executable technical requirement
```

existing exact metadata/scale/section rules、P0-A1-R1 page-frame/title fallback、
Coverage Veto、confidence/review、formal numbering 和 export contract 均必须保持。

## Test And Evaluation Plan

### Testing Pyramid

| Layer | What | Minimum evidence |
| --- | --- | --- |
| Unit | page size、geometry、anchor quorum、cell roles、boundary conflict | exact/just-inside/just-outside parameterized tests |
| Unit | disposition precedence、marker visual context、`其余 3.2`、watermark grid | positive and negative examples |
| Integration | PageInventory -> CandidateSnapshot -> Coverage | matched and no-match pages |
| Fixed corpus | 15 parseable + 2 unsupported pages | immutable source manifest and canonical report |
| Review | independent read-only architecture/diff review | `accept/accept with concerns/reject` |

### Three Separate Reports

#### Automatic Capability

只使用 raw automatic snapshot，报告：

- profile match/no-match；
- candidate count 和 deterministic disposition counts；
- candidate leakage by confirmed table cell；
- non-inspection false-negative audit；
- Coverage completeness；
- repeat determinism；
- layout-resolved source 的 eligible Provider batches 预期为 `0`；Advisor focused
  test 证明没有 call 可归因于这些 source；
- 其他 unresolved sources 的 Provider call 数单独报告，不得混入上述零调用结论。

不得混入人工修改后的 working copy 或 ReviewedResult。

#### Human Correction Cost

在 Quality Owner 标注后单独报告：

- automatic candidate 到 reviewed item 的 add/delete/merge/split/edit counts；
- template noise 的人工恢复数；
- `reference_context/ambiguous` promote/ignore counts；
- 每页 review time 或 commands per page。

ReviewedResult 只能用于 correction burden，不得回填 automatic accuracy。

#### Final Delivery Correctness

P0-A2 不修改正式交付，因此只有后续运行完整 review/freeze/balloon/export 回归后才能
报告：

- formal balloon count 与 reviewed `balloon_required=true` items 一致；
- PDF/Excel/manifest 引用同一 reviewed result；
- table noise 不出现在正式 balloons 或 SIP rows；
- 工程例外未丢失。

没有该执行证据时，结论必须写为“未验证”，不能由 deterministic snapshot 推断。

### Dataset Governance

当前 15-PDF corpus 是 development/regression candidate，且本 spec 的阈值和计数来自
同一 cohort，因此属于 in-sample evidence。推广到其他 WELLI revision 或供应商模板
前必须新增：

1. Quality Owner 批准的 immutable source manifest；
2. observation/cell/item ground truth；
3. 不参与阈值选择的 holdout WELLI cohort；
4. 非 WELLI negative pages，证明 no-match fallback；
5. threshold/rule version freeze。

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| 整块 revision table 过滤导致真实标注丢失 | cell role + engineering-preservation gate；锁定 `其余 3.2` regression |
| 只按页面尺寸误匹配其他模板 | geometry + anchor quorum；歧义直接 no-match |
| line/span 重复造成重复 disposition | assignment 按 observation identity；Coverage 仍逐 observation，评测另按 group 去重 |
| visual context 让 revision marker 回到 parser 或 VLM | confirmed marker cell 对 text 使用明确 precedence，并让 layout-resolved visual ID 同步退出 required/batch/projection |
| watermark rule误删正常文字 | exact text + angle + count + 2×3 grid；不做 substring/generalized watermark |
| 模板 revision 漂移 | versioned profile；边界 conflict no-match；不得自动放宽 tolerance |
| 当前 corpus 过拟合 | in-sample 标签；必须用 holdout/negative pages 才能推广 |
| scanned pages被错误宣称覆盖 | 继续 `unsupported`；扫描 OCR/raster routing 单独立项 |
| `reference_context` 被前端当删除 | Coverage/source relation 保留；本任务不改 frontend，后续 integration test 锁定 API behavior |

## Rollback

后续 implementation 必须使用独立提交。回滚方式是常规 `git revert` 该实现提交：

```text
remove layout evidence producer + PageInventory optional sidecar + consumer
  -> no LayoutProfileMatch decisions
  -> all pages return to existing P0-A1-R1 path
```

回滚不得删除 observation、Coverage 或 historical result，也不得回滚 P0-A1/R1 已完成
的 exact metadata、scale、section 和 region-aware standalone number 规则。

由于 P0-A2 不需要 database migration、runtime config 或 external Provider，回滚不涉及
数据迁移或 secret。回滚后的第一项验证应是 matched/no-match snapshot regression，
确认 no-match 与 pre-P0-A2 baseline 一致。

## What's Working Well — Do Not Touch

- canonical PDF coordinate and Native/OCR separation；
- immutable observation IDs 和 line/span source lineage；
- Coverage Ledger 及 reason/version 字段；
- technical requirement 优先于 generic primary disposition 的现有语义；
- drawing-body parser/grouping path；
- P0-A1-R1 的 conservative fallback；
- Provider Advisor trust boundary；
- raw AutomaticResult、working copy、ReviewedResult 分层；
- provisional marker 与 formal balloon numbering 分离；
- freeze、placement、reviewed-result 和 export Veto Gates。

## Open Questions

只有以下外部决定会影响实施/验收范围：

1. Quality Owner 是否批准把当前 15-PDF corpus 登记为固定 development regression，
   并为 `56` 个 table-noise candidates、`其余 3.2` 和 technical-requirement sources
   提供可评分标注。
2. 首个 holdout cohort 由哪些未参与本 spec 阈值选择的 WELLI PDF 组成；在该 cohort
   到位前，能力只能声明为当前模板样本内有效。

以下已在本文决定，不再作为 implementation 期开放项：

- P0-A2 先用规则，不调用 VLM；
- 不做整块 revision rectangle 删除；
- scanned OCR 和 technical-requirement block grouping 分开立项；
- profile miss 保持 P0-A1-R1；
- 本任务不修改 balloon/review/export。

## Approval And Next Gate

本文当前为 `proposed`。批准后下一步只允许：

1. 把 P0-A2 作为唯一 current plan 的有界 amendment/replan；
2. 明确 single writer、old-path preservation、allowed paths、RED/GREEN commands；
3. 先建立 fixed corpus annotation/evaluation contract；
4. 实现完成后由独立只读 reviewer 检查误删、fallback、Coverage 和 evidence boundary；
5. Quality Owner 只依据 raw automatic、human correction 和 final delivery 三份分离报告
   决定是否接受。

在 design approval 和 successor plan approval 之前，不得开始 production
implementation。
