# Geometric Tolerance Recognition Current-State Audit

## Status

- Date: `2026-08-01`
- Audit status: `verified current-state report`
- Scope: 工程图输入到 workbench UI 的几何公差识别链路
- Change boundary: 只读代码、runtime、数据库和浏览器核验；未修改业务代码
- Runtime evidence project: `9b9911d1-e64e-47a3-b8e5-539aa466dd40`
- Runtime evidence automatic result: `0705ad84-7f75-4c1a-b0f2-e99a58b63cfa`
- Sealed evidence receipt: `docs/superpowers/audits/evidence/2026-08-01-geometric-tolerance-live-receipt.json`

本文记录当前实现事实，不授权 production code、schema、migration、runtime config、
current P0 plan、contract matrix 或 Harness 变更。后续目标合同见
`docs/superpowers/specs/2026-08-01-structured-geometric-tolerance-recognition-design.md`。

## Executive Verdict

当前系统已具备“发现文本邻近矢量上下文，并用 VLM 区分三种几何公差视觉
subtype”的能力，但**不具备端到端结构化 GD&T 识别能力**。

已确认的真实行为是：

1. `gdt_parallelism`、`gdt_perpendicularity`、`gdt_flatness` 可以在原始视觉响应中
   被区分。
2. 三种 subtype 在 `project_visual_observation()` 中被压成
   `CoarseCandidate(coarse_type="geometric_tolerance")`；符号、数值和可能存在的
   datum 只拼进 `raw_text`，没有独立字段。
3. 第 85 项的 `A` 不是 API 或前端漏渲染。真实 inventory 中存在该 `A`，且其 bbox
   位于平行度视觉 ROI 内；但 ROI 的 `associated_text_observation_ids` 只包含当前
   `0.1` line/span，没有包含相邻的独立 `A` line。Provider response schema 又不能
   返回 datum 内容，只能引用已关联 text observation ID。因此 `A` 在视觉
   observation association / Provider contract 边界已经失联。
4. 第 88 项的 flatness subtype 被 VLM 明确识别为 `gdt_flatness`，随后只保留为
   `raw_text="⏥ 0.08"` 和大类 `geometric_tolerance`。
5. 当前没有 feature-control-frame cell splitting、完整 GD&T subtype 集、材料条件
   `M/L/S`、直径修饰符、复合/多层公差框或结构化 datum graph。

所以本次两个案例不能用单一“模型没识别”概括：

- subtype：**模型识别后被业务标准化压平**；
- 案例 A 的 datum `A`：**文本已被 PDF inventory 提取，但在 ROI 文本关联阶段未进入
  可表达的 recognition input contract**；
- API/UI：只忠实传递和展示已经降级的 coarse payload，不是第一丢失点。

## Audit Method And Boundaries

本次核对了：

- repository rules、workflow lane、现有 symbol recognition Specs；
- PDF inventory、vector proposal、OCR、VLM prompt/schema、projection parser；
- Pydantic/domain model、SQLAlchemy model、Alembic、review working copy；
- workbench API、OpenAPI 生成类型、前端手写类型和列表组件；
- unit、integration、E2E、synthetic fixture、Harness artifact；
- 当前 `127.0.0.1:8000` runtime 的 API、PostgreSQL JSONB、inventory artifact、
  redacted Provider request/response artifacts；
- 当前 frontend 的只读浏览器加载和组件代码。

没有修改、重跑或覆盖用户已有 review result；没有把旧 Harness 报告当作当前成功
证据。浏览器加载会触发现有 workbench 的 review-lock 请求，因此没有把目标项目
切换进浏览器；目标第 85/88 项的 UI 结论由目标项目 live API payload 与当前 UI
renderer 共同证明。

## End-To-End Current Implementation

```text
PDF / page
  -> PyMuPDF native line/span text + page.get_drawings()
  -> hybrid image regions additionally use Tencent OCR
  -> text-line-anchored vector proposal builds one annotation_context ROI
  -> crop batching
  -> Qwen VL visual-symbol-review/2
       returns symbol_kind + bbox + associated text IDs + confidence
  -> project_visual_observation()
       extracts exactly one ASCII decimal and optional one-letter text tokens
       emits four-field CoarseCandidate
  -> AutomaticResult.candidates JSONB + Coverage JSONB
  -> ReviewWorkingCopy.items JSONB
  -> GET /api/v1/projects/{project_id}/workbench
  -> frontend ReviewItem (opaque/manual type)
  -> InspectionItemTable
       raw_text + coarse type label "几何公差"
```

主要入口和调用点：

| Stage | Owner / symbol | Evidence |
| --- | --- | --- |
| Task wiring | `tasks.inventory_project()` | `backend/app/processing/tasks.py:160`, `:216`, `:225` |
| Pipeline | `InventoryPipeline.run()` | `backend/app/processing/pipeline.py:248` |
| PDF inventory | `build_inventory()` | `backend/app/pdf/inventory.py:94`, `:111`, `:159`, `:175` |
| Raster OCR orchestration | `RuntimeRecognition.build_inventory()` | `backend/app/processing/runtime_recognition.py:50-118` |
| Raster OCR call | `OcrProvider.recognize_png()` | `backend/app/processing/runtime_recognition.py:83` |
| Vector ROI | `build_page_visual_observations()` | `backend/app/pdf/visual_observations.py:548-687` |
| VLM schema | `visual-symbol-review/2` | `backend/app/providers/visual_symbol_review.schema.json:1-73` |
| GDT projection | `project_visual_observation()` | `backend/app/candidates/symbol_review.py:2517-2530` |
| Coarse schema | `CoarseCandidate` | `backend/app/candidates/complex_fallback.py:8-33` |
| Result persistence | `AutomaticResult` | `backend/app/candidates/models.py:23-98` |
| Review projection | `ReviewService._current_item()` | `backend/app/review/service.py:513-553` |
| Workbench API | `_workbench_payload()`, `_project_items()` | `backend/app/projects/router.py:329-404`, `:471-560` |
| Frontend type | `ReviewItem` | `frontend/src/api/types.ts:81-122` |
| UI label | `inspectionItemPresentation()` | `frontend/src/components/workbench/inspectionItemPresentation.ts:48-60` |
| UI row | `InspectionItemTable` | `frontend/src/components/workbench/InspectionItemTable.tsx:258-325` |

## Detection And ROI Findings

### Confirmed Support

- 系统能生成覆盖几何公差框附近图形的整体 `VisualObservation`。
- 该 observation 是 `annotation_context`，proposal kind 是
  `text_adjacent_vector_context`。
- ROI 由一个 native text line 与距离不超过 `12pt`、尺寸不超过 `96pt` 的邻近矢量
  path union 形成；它不是独立训练的 geometric-tolerance detector。
- Provider detection bbox 是相对 crop 的 normalized bbox；最终 candidate bbox 会与
  关联文本 bbox 合并。

### Not Supported

- proposal 阶段没有 `parallelism`、`flatness` 等 subtype 分类；subtype 只在 VLM
  response 出现。
- 没有把 feature-control frame 切成符号格、公差值格、modifier 格、datum 格。
- `VisualObservation.associated_text_observation_ids` 只取触发 proposal 的当前 line 与
  它的 span（`visual_observations.py:676-685`）。同一框内另一个独立 line 不会因为
  落在 ROI 内自动加入。这正是当前案例 A 丢失 `A` 的最早确认原因。
- 纯扫描 PDF 的完整 GD&T 路径未被现有 Specs 承诺；Tencent OCR 只补文本
  observation，不解析工程符号或 frame cell。

### Bbox Answer

当前 bbox 是“文本锚点 + 邻近矢量路径”的整体上下文，既不是严格的完整公差框
detector bbox，也不是框内单个符号 cell bbox。VLM 可在 crop 中返回 component bbox，
但业务投影仍将 component 与关联文本 union 成一个 candidate 坐标。

## Recognition And Parsing Findings

### Current Technology Combination

| Input | Current mechanism | GD&T responsibility |
| --- | --- | --- |
| Native PDF text | PyMuPDF | 提取数值/字母，不能识别矢量 glyph |
| Raster text | Tencent OCR | 提取文本 token，不是 GD&T parser |
| Vector symbol | Qwen VL | 在 frozen enum 中分类视觉 symbol |
| Normalization | deterministic Python rules | 唯一 decimal + 单字母 token，拼 coarse payload |
| Template/image classifier | 未发现 | 未确认存在任何 GD&T 专用实现 |

Provider exact schema 只允许：

- `visual_observation_id`
- `symbol_kind`
- `bbox_normalized`
- `associated_text_observation_ids`
- `confidence_signal`

`symbol_kind` 只包含三种 GD&T subtype：

- `gdt_parallelism`
- `gdt_perpendicularity`
- `gdt_flatness`

未包含 straightness、circularity、cylindricity、angularity、position、profile、
concentricity、symmetry、circular runout、total runout 等类型。

### Current Raw And Normalized Content

- Raw visual response 能保存三种 `symbol_kind`、关联 text IDs 和 confidence。
- `_distinct_ascii_decimals()` 只从关联文本提取 ASCII decimal。
- `_gdt_datum_tokens()` 允许数字与单个大写英文字母；任何其他 token 会使投影失败。
- `project_visual_observation()` 映射 `parallelism -> ∥`、
  `perpendicularity -> ⊥`、`flatness -> ⏥`，然后只生成 `raw_text`、`coordinates`、
  `coarse_type`，外加后续强制确认标志。
- 没有独立的 `tolerance_type`、`tolerance_symbol`、`tolerance_value`、
  `datum_references`、`modifiers` 或 `diameter_modifier`。
- 没有 `M/L/S`、多 segment、复合/多层 frame parser。

### Symbol Answers

- `∥`：当 VLM 分类为 `gdt_parallelism` 时，投影前缀为 `∥`。
- 用户给出的 `▱`：当前没有该 literal glyph contract 或测试。当前 flatness canonical
  输出是 `⏥`。真实案例的 VLM 已识别为 `gdt_flatness` 并产生 `⏥ 0.08`。
- 不能据此断言普通 OCR 稳定识别 `∥/▱/⏥`；当前成功 subtype 来自视觉分类，不是
  OCR glyph parsing。

## Data Model And Persistence Findings

### Field Matrix

| Requested field | Current normalized candidate | Other internal surface | Verdict |
| --- | --- | --- | --- |
| `category` | 无；等价 coarse 字段为 `coarse_type` | technical requirements 有自己的 `category` | 不支持目标字段 |
| `measurement_type` | 无 | 无 | 不支持 |
| `tolerance_type` | 无 | coverage 可留 `advisor_review.symbol_kinds` | 非业务合同 |
| `tolerance_symbol` | 无 | 只混入 `raw_text` | 不支持 |
| `tolerance_value` | 无 | 只混入 `raw_text` | 不支持 |
| `datum_references` | 无 | datum 可成为 source-only context | 不支持 |
| `modifiers` | 无 | 无 | 不支持 |
| `diameter_modifier` | 无 | `diameter` 是另一 symbol kind/尺寸路径 | 不支持 GD&T modifier |
| `confidence` | 无 raw confidence | coverage 内部有 `confidence_signal`；item 有派生 `confidence_decision` | 不支持原始候选 confidence API |
| `raw_text` | 有 | working copy/UI 保留 | 支持 |
| `raw_model_output` | 无 | Provider artifact/cache 可保存 | 不进入业务结果/API |
| `bbox` | `coordinates` | workbench overlay 为 `bbox_pdf` | 支持等价坐标 |
| `source_image_id` | 无 | 有 source location IDs/crop refs | 不支持该字段 |
| `review_status` | 候选用 `status` | technical requirement 另有 `review_status` | 非同名合同 |

### Persistence Truth

- `AutomaticResult.candidates`、`coverage`、`technical_requirements` 是 JSONB；没有
  GD&T 专用列（`backend/app/candidates/models.py:56-64`，migration
  `backend/alembic/versions/0003_candidates.py:20-50`）。
- Provider 原始 response 可以在 artifact/cache 内保留完整 frozen response；
  `VisualSymbolCacheEntryRecord.response` 也是 JSONB
  （`backend/app/candidates/models.py:151-189`）。它不是业务候选 schema。
- Review working copy 和 reviewed result 的 `items` 仍是 JSONB
  （`backend/app/review/models.py:14-131`）。
- `_current_item()` 深拷贝 candidate payload，所以它不会主动删除已经存在的 payload
  字段；问题是上游 payload 从未包含结构化 GD&T 字段。
- `_review_coverage()` 会把 `advisor_review` 压成诊断字段并删除原对象，进一步说明
  coverage 不能作为稳定 GD&T 业务合同。

结论：不存在 ORM 列“有 datum 而 API schema 漏掉”的简单 mismatch；当前主要
mismatch 是 raw visual evidence 比 normalized candidate 丰富，而 normalized API 又以
opaque `dict` 暴露，缺少可验证的 typed contract。

## API And Frontend Findings

`GET /api/v1/projects/{project_id}/workbench` 的语义字段来自
`working_copy.items`。`ProjectWorkbenchCandidateResponse` 只提供 overlay 元数据：
`id/item_id/page_index/bbox_pdf/confidence_band/review_disposition/status`，不补 GD&T
语义。

前端现状：

- generated OpenAPI 把 working-copy item 表示为 opaque object
  （`frontend/src/api/generated.ts:693`）。
- 手写 `ReviewItem` 没有任何 structured GD&T 字段
  （`frontend/src/api/types.ts:81-122`）。
- `inspectionItemPresentation()` 只按 `item_type`/`coarse_type` 映射大类。
- `zhCN.review.coarseTypes.geometric_tolerance` 固定为“几何公差”
  （`frontend/src/copy/zhCN.ts:407-409`）。
- 列表第一个内容格渲染 `item.raw_text`，下面渲染大类 label；数值格对 coarse item
  回退到同一 `raw_text`，公差行只读 typed dimension 的 upper/lower tolerance
  （`InspectionItemTable.tsx:304-310`）。
- ReviewPanel 对 coarse item 只提供 raw text 编辑，没有 subtype/datum 专用控件。

所以“前端收到 datum 但没渲染”在当前真实案例中为否。目标 API 的第 85 项本身就是
`raw_text="∥ 0.1"`，没有 datum 字段或 `A`；前端没有可渲染的数据。

## Live Case Traces

### Case A: `∥ | 0.1 | A`

期望目标：

```json
{
  "category": "geometric_tolerance",
  "tolerance_type": "parallelism",
  "tolerance_value": "0.1",
  "datum_references": ["A"]
}
```

真实逐层结果：

以下 runtime 数值均固化在
`docs/superpowers/audits/evidence/2026-08-01-geometric-tolerance-live-receipt.json`；
receipt 同时记录 source PDF、inventory 与脱敏 Provider response SHA-256。

| Layer | Verified result | Classification |
| --- | --- | --- |
| PDF inventory | `0.1` 和独立 `A` 都被 native extraction 提取；`A` bbox 为 `[712.13,390.73,720.73,407.93]` | 识别成功 |
| Visual ROI | ROI bbox `[659.5,388.89,721.3,428.49]` 包含 `A`，但 associated IDs 只包含 `0.1` line/span | **关联阶段丢失 A** |
| Raw VLM response | `symbol_kind=gdt_parallelism`，`confidence_signal=0.97`，关联的仍是两个 `0.1` IDs | subtype 识别成功；datum contract 不可表达 |
| Projection | `raw_text="∥ 0.1"`, `coarse_type="geometric_tolerance"` | **subtype 结构被压平** |
| AutomaticResult JSONB | candidate `abab42bb24a679dccb84d4e1` 只保留上述 coarse payload | 无独立 datum/subtype |
| Review working copy/API | 第 85 项仍为 `∥ 0.1`、`geometric_tolerance` | 忠实传递降级结果 |
| UI | raw text + “几何公差” | 无 datum 可渲染 |

补充：unit test 证明，如果 `A` 已经进入关联文本，当前投影可拼出
`raw_text="∥ 0.1 A"`（`backend/tests/unit/candidates/test_symbol_advisor.py:1580-1602`）。
这不等于结构化保存 `datum_references`，但可排除“标准化函数必然删除所有 A”的说法。

### Case B: `▱ | 0.08`

按本 Specs 目标解释为 flatness：

```json
{
  "category": "geometric_tolerance",
  "tolerance_type": "flatness",
  "tolerance_value": "0.08",
  "datum_references": []
}
```

真实逐层结果：

以下 runtime 数值使用同一 sealed receipt，可与 Case A 的 source/inventory/provider
hash 一起复核。

| Layer | Verified result | Classification |
| --- | --- | --- |
| PDF inventory | 两个 line/span 形式的 `0.08` observation | 数值识别成功 |
| Visual ROI | `gdt_flatness` ROI 关联两个 `0.08` IDs | 关联成功 |
| Raw VLM response | `symbol_kind=gdt_flatness`, `confidence_signal=0.96` | subtype 识别成功 |
| Projection | canonical `raw_text="⏥ 0.08"`, `coarse_type="geometric_tolerance"` | subtype 结构被压平 |
| AutomaticResult/API | candidate `f11f741bd0e2d49b02856ae6` 保留上述 coarse payload | 无 `tolerance_type/value` |
| UI | raw text + “几何公差” | 只展示大类 |

`▱` 与当前 canonical `⏥` 的 glyph alias 关系在代码和测试中没有正式定义；除本真实
VLM 分类结果外，对任意 `▱` crop 的稳定识别能力仍标记为**未确认**。

## Tests And Samples

### Existing Coverage

- unit test 覆盖三种 `gdt_*` 到四字段 coarse candidate，以及
  `∥ 0.1 A -> raw_text="∥ 0.1 A"`。
- integration test 明确锁定“roughness/GDT 不扩 schema，datum 保持 source-only
  context”的当前设计（`test_symbol_recognition_pipeline.py:2096-2142`）。
- synthetic PDF fixture 覆盖 `0.1 A` parallelism、`0.2 B` perpendicularity、
  `0.05` flatness 和 boxed `A/C`。
- E2E 从 inventory 到 review 使用 frozen provider response，不是真实 VLM。
- Harness 中存在真实图纸的 GDT annotation artifact，但已有两个 symbol-recognition
  报告均为 `passed=false`，不能当作当前通过证据。

### Missing Coverage

- 没有 literal `▱ | 0.08` 测试；active backend tests 中没有 `▱`。
- 没有结构化 `tolerance_type/value/datum_references` 的 contract、persistence、API、UI
  测试。
- 没有 M/L/S、diameter modifier、多个 datum、有序 datum、复合或多层 frame 测试。
- 没有针对 GD&T 的低分辨率、线条粘连、倾斜和扫描图 corpus/gate。
- synthetic fixture 的 GDT 是单 rectangle 的简化符号上下文，不等价于真实多 cell
  feature-control frame。

## Confirmed Bugs And Capability Gaps

### Confirmed Bugs

1. **Independent-line association gap**：ROI 内的独立 datum line 不会加入
   `associated_text_observation_ids`；真实第 85 项因此丢失 `A`。
2. **Semantic projection loss**：raw VLM 已有三种 subtype，业务 candidate 仍只有
   coarse type，导致 subtype/value/datum 无法成为稳定合同。
3. **Opaque API schema**：working-copy items 以 `dict[str, Any]`/opaque object 暴露，
   无法用 OpenAPI 保证 GD&T 字段不被回归删除。

### Current Capability Gaps, Not Proven Regressions

- 完整 GD&T subtype 集；
- cell splitting 与 frame grammar；
- datum/modifier/diameter/复合 frame；
- 扫描图稳健性；
- structured editing、review、export；
- glyph alias policy（包括用户输入 `▱` 与 canonical `⏥`）。

## Confirmed Versus Unconfirmed

| Question | Answer |
| --- | --- |
| 能否发现几何公差框区域？ | 是，但只是 text-anchored vector context，不是专用 frame detector |
| 检测模型是否只给统一类别？ | proposal 是统一上下文；VLM 能区分三种 subtype；业务结果统一为 coarse type |
| 是否有 cell splitting？ | 否 |
| 是否只 OCR 整框再取数字？ | 否；实际是 native/OCR text + VLM symbol classification + deterministic projection |
| 是否保存 parallelism/flatness？ | raw response/coverage 有 symbol kind；正式 candidate/API 无独立字段 |
| datum 是否有独立字段？ | 否 |
| 第 85 项 A 在哪里丢失？ | visual observation text association / Provider input contract 边界 |
| 第 88 项 subtype 在哪里丢失？ | `project_visual_observation()` coarse projection 边界 |
| 普通 OCR 对工程 glyph 是否稳定？ | 未确认；当前没有相应 gate |
| 对任意 `▱` crop 是否稳定识别 flatness？ | 未确认；当前真实 case 被 VLM 识别，但无 literal contract/corpus gate |

## Recommended Boundary

不要在前端解析 `raw_text` 补 subtype 或 datum。唯一业务 Owner 应位于 candidate domain
的 canonical GD&T normalizer；它必须在进入 `AutomaticResult` 前提交 typed payload。
旧 `geometric_tolerance` coarse path 只能在替代合同、旧数据读取策略和退出条件明确后
退役。目标合同与验收口径在配套 Specs 中定义。
