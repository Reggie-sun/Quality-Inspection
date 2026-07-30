# P0-A2 WELLI Template-Aware Layout Noise Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对已确认的 WELLI 固定工程图模板做高置信 layout/cell 匹配，把标题栏、更改栏、档案栏、页框编号和同页网格水印从 candidate path 路由到可追溯的 `reference_context/non_inspection`，同时保留真实工程标注、Coverage identity 和 unresolved visual Advisor 路径。

**Architecture:** `backend/app/pdf/layout_profiles.py` 只负责从 Native line、page size 和 raw drawings 产生 versioned layout evidence；`backend/app/candidates/disposition.py` 继续是 primary disposition 唯一 Owner；`candidate_snapshot_from_inventory()` 编排 row-level preservation、text/visual Coverage 和 required visual set；`plan_visual_batches()` 与 `CandidateAdvisor` 机械遵守 required set。模板未命中、证据冲突、OCR 后追加、工程语义或 mixed visual relation 均回到现有路径。

**Tech Stack:** Python 3.12、PyMuPDF、frozen dataclasses、pytest、现有 `qi-p0` Micromamba 环境

---

## Status And Authority

- Date: `2026-07-30`
- Status: `accepted / complete`
- Lane: `Heavy`
- Parent plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- Approved design:
  `docs/superpowers/specs/2026-07-30-p0-a2-welli-template-aware-layout-noise-routing-design.md`
- Design checkpoint: `4b13193`
- Verified base: `main@f9c8c2d`
- Planning worktree:
  `.worktrees/welli-template-layout-filtering-spec`（merge 后已删除）
- Planning branch:
  `codex/welli-template-layout-filtering-spec`（merge 后已删除）
- Execution authorization: 用户已批准本 subordinate implementation sequence；
  Tasks 1–9 已按顺序执行，implementation 经 integration checkpoint `3d00d15`
  合入本地 `main`。本计划不替换 parent plan，也未授权或执行 live Provider call、
  runtime config、database schema/migration 修改、Harness receipt、review freeze 或
  export。

本计划作为 parent plan 下的有界 successor work package 已完成。各 Task 的执行证据、
验证结果、review 结论和剩余边界记录在 `Execution Results`；checkbox 表示对应步骤
已有执行证据，不扩大原计划范围。

## Planning Amendments From Real-Code Mapping

在把 design 映射到真实调用链时确认了三个必须写入 implementation contract 的细节：

1. `ObservationRegionAssignment` 必须携带稳定 `cell_id`。revision description
   的 row-level engineering veto 需要按同一 row identity 聚合，不能在
   Candidate Snapshot 中重新硬编码 geometry，也不能从 evidence code 反解析 row。
2. 只修改 text disposition 不能实现固定表格噪声的 VLM 零调用。当前
   `candidate_snapshot_from_inventory()` 把所有 visual source 标为 required，
   `plan_visual_batches()` 调度所有 visual observations，而
   `CandidateAdvisor` 又对整页 visual source 做 projection。实现必须让
   layout-resolved visual source 同步退出 required set、batch 和 projection，
   否则会被 `visual_no_detection` 重新覆盖为 `ambiguous`。
3. 真实 `VisualObservation.associated_text_observation_ids` 同时包含 Native line 和
   child spans，而 Candidate Snapshot 正式 text grain 只选择 Native line。实现必须
   用 `parent_region_id` 做 fail-closed canonical projection；不能把合法 child span
   当成 missing relation，也不能为 span 另造 Coverage。

这些修订只闭合既有 design 的 identity、lineage 和 Provider boundary，不改变 Provider
port、response schema、review、balloon 或 export 语义。

## Selection Record

- Problem boundary:
  - P0-A1-R1 已处理 exact metadata label、比例、剖视标签和粗粒度裸数字区域；
  - 它没有稳定模板 profile、cell identity、same-page watermark 或
    layout-resolved visual routing；
  - 当前真实 corpus 中有 `57` 个 candidate 落入已确认模板区域，其中 `56` 个可安全
    路由，`1` 个 `其余` + `3.2` 工程例外必须保留。
- Single disposition Owner:
  `backend/app/candidates/disposition.py`
- Geometry evidence producer:
  `backend/app/pdf/inventory.py::build_inventory()`
- Layout algorithm Owner:
  `backend/app/pdf/layout_profiles.py`
- Candidate/Coverage orchestration Owner:
  `backend/app/processing/automatic_result.py::candidate_snapshot_from_inventory()`
- Visual scheduling Owner:
  `backend/app/candidates/symbol_review.py::plan_visual_batches()`
- Advisor write Owner:
  `backend/app/candidates/advisor.py::CandidateAdvisor.review()`
- Old path action:
  `preserve` technical requirement、P0-A1-R1 generic disposition、
  composite/grouping/parser/coarse fallback 和 unmatched visual routing。
- First focused verification:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/pdf/test_layout_profiles.py \
  tests/unit/pdf/test_inventory.py
```

## Allowed And Forbidden Paths

### Allowed production paths

- `backend/app/pdf/layout_profiles.py`
- `backend/app/pdf/schemas.py`
- `backend/app/pdf/inventory.py`
- `backend/app/candidates/disposition.py`
- `backend/app/processing/automatic_result.py`
- `backend/app/candidates/symbol_review.py`
- `backend/app/candidates/advisor.py`

### Allowed test/helper paths

- `backend/tests/helpers/welli_layout_fixture.py`
- `backend/tests/helpers/welli_layout_regression.py`
- `backend/tests/unit/helpers/test_welli_layout_regression.py`
- `backend/tests/unit/pdf/test_layout_profiles.py`
- `backend/tests/unit/pdf/test_inventory.py`
- `backend/tests/unit/pdf/test_runtime_ocr.py`
- `backend/tests/integration/test_pdf_inventory.py`
- `backend/tests/unit/candidates/test_disposition.py`
- `backend/tests/unit/candidates/test_symbol_advisor.py`
- `backend/tests/unit/candidates/test_advisor.py`
- `backend/tests/e2e/test_offline_automatic_result.py`

### Allowed documentation path

- 本计划文件的 `Execution Results`

### Forbidden paths and changes

- frontend modules
- review、confidence、numbering、balloon、placement、Excel、PDF export 或 manifest
- Provider port、SDK、adapter、prompt 或 response schema
- database model、migration 或 persisted public API schema
- `.agent/harness/runs/` 中的 historical/sealed evidence
- runtime config、secret、model selection 或 network policy
- user-provided PDF 内容、WeChat absolute path 或 PDF binary 入库
- technical requirement block grouping、扫描件 OCR enablement 或局部 VLM 新能力

若 RED 证明必须修改 forbidden path，停止当前 Task，记录证据并请求 replan；不得以
“小改动”为由扩展 scope。

## Unchanged Contracts

- `TextObservation` identity、source type、raw/normalized text、`bbox_pdf`、
  `bbox_normalized`、direction、confidence 和 `parent_region_id` 均不变。
- Native/OCR observation 互不覆盖；P0-A2 只给 matcher 当时存在的 Native line
  建立 assignment。
- `PageInventory.layout_profile_match` 是 optional additive sidecar；no-match 时旧
  serialization byte shape 不变。
- `CoverageEntry` 继续是每个 selected source 恰好一次 disposition 的审计面。
- `reference_context` 仍保留 source identity/bbox/relation，不等于删除。
- technical requirement classifier 先于 template policy。
- drawing body、unmatched page、boundary conflict、unknown cell 和 OCR append 均走
  现有路径。
- VLM 仍是 Advisor；layout rule 不能创建正式 identity、InspectionItem、
  ReviewedResult 或 formal balloon number。
- 未 freeze 的 working copy 不参与正式编号或导出。
- PDF、Excel 和 manifest 的 reviewed-result 一致性合同不变。

## Fixed Deterministic Contract

实现不得在编码过程中重新调参：

```text
MM_PER_PDF_POINT = 25.4 / 72
page-size tolerance = 0.5 mm
grid tolerance = 1.0 mm
horizontal assignment angle = 0° ±2°
watermark angle = -30° ±2°
watermark spacing tolerance = 2.0 mm
minimum unique Native line watermark count = 9
rule version = p0-a2-welli-layout/1
```

Supported physical page variants：

```text
A3 landscape = 420 x 297 mm
A4 portrait = 210 x 297 mm
A3 portrait  = 297 x 420 mm
```

Outer regions：

```text
title block   = [W-185, H-61, W-5, H-5]
revision      = [W-95, 5, W-5, 40]
archive strip = [0, H-107, 25, H-5]
body frame    = [25, 5, W-5, H-5]
```

Title local grid：

```text
x = 0,12,24,40,52,64,80,106,118,130,144,180
y = 0,7,14,18,21,28,35,38,42,47,49,56
optional x=93 is evidence-neutral
```

Revision local grid：

```text
x = 0,10,90
y = 0,5,15,25,35
```

Archive local grid：

```text
x = 0,25
y = 0,7,17,24,34,41,51,58,68,75,85,92,102
```

Profile match 必须同时满足：唯一 page variant、body frame、三组 region geometry 中
至少两组、三组 text anchors 中至少两组，且无同分/conflict。只有 page size、只有
text 或只有 geometry 均返回 `None`。

## Plan Review Record

- Initial read-only verdict: `reject`
- Blocking findings:
  - 真实 visual relation 同时含 line/span，而 selected text grain 只有 line；
  - negative boundary assignment 与 design 冲突；
  - real-PDF diagnostic 缺少可执行 helper/CLI/schema；
  - plan checkpoint 未指向包含 material amendments 的 committed design。
- Corrections:
  - 增加 canonical parent-line projection 及 orphan/mismatch fail-closed tests；
  - negative `boundary_distance_mm` 改为 no assignment；
  - 增加 test-only diagnostic helper、unit test、sidecar-stripped control、双运行命令；
  - 先提交 design 为 `4b13193`，再更新本计划 checkpoint。
- Final read-only verdict: `accept`
- Reviewer verification:
  `git status`、`git show`、`git rev-parse`、`git diff --check`、`rg`、`nl`
- Tests not run: 本轮只复核 docs；implementation 尚未授权，RED/GREEN tests 属于
  Task 1～9。

## Rollback

每个 Task 独立 commit。若某 Task 的 GREEN、focused regression 或 review gate
失败，只 revert 该 Task commit，再复跑前一 Task 的 focused command。不得 reset、
revert 或覆盖用户/其他 Task 的未提交改动。若 layout match 已发布但 candidate
routing 未发布，可通过 revert inventory integration commit 回到 sidecar-absent 的
旧路径；no-match compatibility 必须保证该回滚可行。

## Task 1: Freeze The Additive Layout Sidecar

**Files:**

- Modify: `backend/app/pdf/schemas.py`
- Modify: `backend/tests/unit/pdf/test_inventory.py`

- [x] **Step 1: Write serialization and immutability tests**

增加精确测试：

```python
def test_page_inventory_omits_absent_layout_profile_match() -> None:
    page = _page_inventory(layout_profile_match=None)
    assert "layout_profile_match" not in page.to_dict()


def test_page_inventory_serializes_versioned_layout_assignment() -> None:
    assignment = ObservationRegionAssignment(
        observation_id="native:p0:b1:l2:line",
        page_index=0,
        profile_id="welli-a3-landscape",
        region_id="revision_table",
        cell_role="revision_description",
        cell_id="revision-description-3",
        assignment_evidence_codes=("bbox_inside_role", "center_in_role"),
        boundary_distance_mm=2.1,
        rule_version="p0-a2-welli-layout/1",
    )
    page = _page_inventory(
        layout_profile_match=LayoutProfileMatch(
            page_index=0,
            profile_id="welli-a3-landscape",
            match_state="high_confidence",
            geometry_evidence_codes=("archive_grid", "body_frame", "revision_grid"),
            text_anchor_evidence_codes=("archive_anchor", "revision_anchor_quorum"),
            assignments=(assignment,),
            rule_version="p0-a2-welli-layout/1",
        )
    )
    assert page.to_dict()["layout_profile_match"]["assignments"][0][
        "cell_id"
    ] == "revision-description-3"
```

同时锁定：

- frozen dataclass 不能原地修改；
- tuple/evidence 输出顺序稳定；
- `layout_profile_match=None` 时现有 `visual_observations` 省略逻辑不变；
- `append_ocr_observations()` 保留同一个 sidecar value；
- 追加 OCR 后 assignments 只包含原有 Native line IDs。

- [x] **Step 2: Run the focused test and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/pdf/test_inventory.py
```

Expected RED: `LayoutProfileMatch` / `ObservationRegionAssignment` import 不存在，
或 `PageInventory` 不接受 `layout_profile_match`。

- [x] **Step 3: Add the minimum schema**

在 `backend/app/pdf/schemas.py` 增加：

```python
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
class LayoutProfileMatch:
    page_index: int
    profile_id: str
    match_state: Literal["high_confidence"]
    geometry_evidence_codes: tuple[str, ...]
    text_anchor_evidence_codes: tuple[str, ...]
    assignments: tuple[ObservationRegionAssignment, ...]
    rule_version: str
```

把以下 optional field 加在 `PageInventory` default fields 中：

```python
layout_profile_match: LayoutProfileMatch | None = None
```

并在 `to_dict()` 中只对 `None` 省略：

```python
if self.layout_profile_match is None:
    payload.pop("layout_profile_match")
```

不得改变 `TextObservation` 或 `VisualObservation` shape。

- [x] **Step 4: Run the focused test and verify GREEN**

Run Step 2 command. Expected: all pass.

- [x] **Step 5: Commit Task 1**

```bash
git add backend/app/pdf/schemas.py \
  backend/tests/unit/pdf/test_inventory.py
git commit -m "feat: add immutable PDF layout evidence sidecar"
```

## Task 2: Build The WELLI Profile Signature Matcher

**Files:**

- Create: `backend/app/pdf/layout_profiles.py`
- Create: `backend/tests/helpers/welli_layout_fixture.py`
- Create: `backend/tests/unit/pdf/test_layout_profiles.py`

- [x] **Step 1: Add a deterministic synthetic WELLI fixture**

用 PyMuPDF `page.new_shape()`、`draw_line()`、`draw_rect()`、`finish()` 和
`commit()` 构建最小 test-only page。fixture 必须能分别开关：

- supported page variant；
- body/title/revision/archive geometry；
- title/revision/archive text anchors；
- optional title `x=93`；
- unknown drawing opcode；
- page rotation。

fixture 只创建测试输入，不复制真实 PDF 或 host absolute path。

- [x] **Step 2: Write matcher gate tests**

锁定以下矩阵：

```text
page size exact                                  -> eligible
page size +0.49 mm                               -> eligible
page size +0.51 mm                               -> no match
page rotation != 0                               -> no match
only page size                                   -> no match
only text anchors                                -> no match
only geometry                                    -> no match
body + 2 region geometries + 2 anchor groups     -> high confidence
optional x=93 missing                            -> still high confidence
critical grid missing/conflicting                -> no match
unknown/cubic drawing opcode only                -> ignored evidence, not blocker
same input in different list order               -> identical result
```

调用目标 API：

```python
match = match_welli_layout_profile(
    page_index=0,
    page_width_pt=page_width_pt,
    page_height_pt=page_height_pt,
    page_rotation=0,
    observations=observations,
    drawings=drawings,
)
```

Expected result 只允许 `LayoutProfileMatch(high_confidence)` 或 `None`，不增加
medium/low state。

- [x] **Step 3: Run tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/pdf/test_layout_profiles.py
```

Expected RED: `app.pdf.layout_profiles` 不存在。

- [x] **Step 4: Implement the physical profile and geometry reader**

新模块公开面固定为：

```python
def match_welli_layout_profile(
    *,
    page_index: int,
    page_width_pt: float,
    page_height_pt: float,
    page_rotation: int,
    observations: Sequence[TextObservation],
    drawings: Sequence[Mapping[str, Any]],
) -> LayoutProfileMatch | None:
    ...


def welli_same_page_watermark_observation_ids(
    *,
    profile_match: LayoutProfileMatch | None,
    observations: Sequence[TextObservation],
) -> frozenset[str]:
    ...
```

内部可使用 frozen `_Profile`、`_SegmentMm`、`_RoleRectMm`。drawing reader 只消费
PyMuPDF `"l"` 与 `"re"`；`"c"`、`"qu"` 和未知 opcode 不贡献 evidence，也不让
matcher 崩溃。所有 PDF points 在函数入口转换为 mm；profile 常量不得改用 normalized
ratio。

geometry codes 按稳定字典序输出：

```text
archive_grid
body_frame
revision_grid
title_grid
```

anchor codes 按稳定字典序输出：

```text
archive_anchor
revision_anchor_quorum
title_anchor_quorum
```

matcher 不读取 filename、basename、source hash、page allowlist 或 corpus identity。

- [x] **Step 5: Run matcher tests and verify GREEN**

Run Step 3 command. Expected: all pass.

- [x] **Step 6: Commit Task 2**

```bash
git add backend/app/pdf/layout_profiles.py \
  backend/tests/helpers/welli_layout_fixture.py \
  backend/tests/unit/pdf/test_layout_profiles.py
git commit -m "feat: match versioned WELLI drawing layouts"
```

## Task 3: Add Cell Assignment And Same-Page Watermark Evidence

**Files:**

- Modify: `backend/app/pdf/layout_profiles.py`
- Modify: `backend/tests/helpers/welli_layout_fixture.py`
- Modify: `backend/tests/unit/pdf/test_layout_profiles.py`

- [x] **Step 1: Write cell assignment tests**

每个 assignment 必须满足：

```text
Native line only
center in one role union
full bbox within the unexpanded role union
all touched base cells share the same role
only one role matches
direction angle = 0° ±2°
page/profile/lineage has no conflict
```

增加以下边界测试：

- title metadata、approval、revision header、revision marker/description、
  archive label/record 和 page-frame cell 得到预期 `region_id/cell_role/cell_id`；
- `revision-marker-1` 与 `revision-description-1` 是稳定不同 identity；
- bbox 跨两种 role 不 assignment；
- center 在 cell 内但完整 bbox 越过 role union 边界，即使不足 `1 mm` 也不
  assignment；
- `boundary_distance_mm` 在 `0..1` 可创建 assignment，但后续 disposition 不可直接
  过滤；
- `boundary_distance_mm < 0` 不创建 assignment；
- Native span、OCR observation 不 assignment；
- input order 改变时 assignments 的 canonical serialization 不变。

- [x] **Step 2: Write watermark tests**

正例必须同时满足 exact text、angle、minimum count 和 2D spacing grid：

```python
ids = welli_same_page_watermark_observation_ids(
    profile_match=match,
    observations=observations,
)
assert ids == frozenset(expected_native_line_ids)
```

负例覆盖：

- 8 个点；
- 水平 `伟立机器人`；
- `伟立机器人有限公司` substring；
- angle 超出 `-30° ±2°`；
- 只有一列或两行；
- x/y spacing 超出对应 profile `±2 mm`；
- line/span 同源不能重复计数；
- `profile_match=None`。

- [x] **Step 3: Run tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/pdf/test_layout_profiles.py
```

Expected RED: matcher 尚未返回 cell assignments，watermark helper 尚未实现完整
grid contract。

- [x] **Step 4: Implement assignments and watermark evidence**

使用 profile 内 role rectangles 和 stable cell IDs。assignment evidence 至少能区分：

```text
center_in_role
bbox_inside_role
single_role
horizontal_direction
```

`boundary_distance_mm` 使用相对 role union 的 signed inward distance：

- positive: bbox 在 role 内；
- zero: bbox 接触边界；
- negative: bbox 越界，因此不创建 assignment。

watermark 只迭代 `source_type=="native"` 且
`observation_level=="line"` 的 observations；按 profile spacing 聚类 unique centers，
不得使用 span 数量凑 `>=9`。

- [x] **Step 5: Run tests and verify GREEN**

Run Step 3 command. Expected: all pass.

- [x] **Step 6: Commit Task 3**

```bash
git add backend/app/pdf/layout_profiles.py \
  backend/tests/helpers/welli_layout_fixture.py \
  backend/tests/unit/pdf/test_layout_profiles.py
git commit -m "feat: assign WELLI cells and watermark evidence"
```

## Task 4: Integrate The Matcher Into Page Inventory

**Files:**

- Modify: `backend/app/pdf/inventory.py`
- Modify: `backend/tests/unit/pdf/test_inventory.py`
- Modify: `backend/tests/unit/pdf/test_runtime_ocr.py`
- Modify only if required by RED: `backend/tests/integration/test_pdf_inventory.py`

- [x] **Step 1: Write producer and persistence tests**

用 monkeypatch/spy 锁定：

- `build_inventory()` 每页恰调用 matcher 一次；
- matcher 收到 page size、rotation、Native observations 和原始 drawings；
- matched page 保存 reduced sidecar，不保存 raw drawings；
- no-match page `to_dict()` 与旧 shape byte-equivalent；
- `InventoryPipeline._store_inventory()` 在现有
  `schema_version="page-inventory/1"` payload 中自然保存 additive field；
- `append_ocr_observations()` 保留 sidecar，不调用 matcher；
- OCR observations 不被追加进已有 assignments。

- [x] **Step 2: Run tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/pdf/test_inventory.py \
  tests/unit/pdf/test_runtime_ocr.py \
  tests/integration/test_pdf_inventory.py
```

Expected RED: `build_inventory()` 未调用 matcher，matched sidecar 为空。

- [x] **Step 3: Add the single producer call**

在 `page.get_drawings()` 和 Native observations 均可用、`PageInventory` 构造前调用：

```python
layout_profile_match = match_welli_layout_profile(
    page_index=page_index,
    page_width_pt=transform.width,
    page_height_pt=transform.height,
    page_rotation=transform.rotation,
    observations=tuple(observations),
    drawings=drawings,
)
```

构造 `PageInventory` 时只附加：

```python
layout_profile_match=layout_profile_match
```

不修改 `append_ocr_observations()` 的 `replace(...)` 实现，除非 RED 证明 sidecar 被
丢失；预期只补回归测试。

- [x] **Step 4: Run tests and verify GREEN**

Run Step 2 command. Expected: all pass.

- [x] **Step 5: Commit Task 4**

```bash
git add backend/app/pdf/inventory.py \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/integration/test_pdf_inventory.py
git commit -m "feat: attach WELLI layout evidence to page inventory"
```

提交前用 `git diff --name-only --cached` 确认不存在未实际修改的 path；未修改文件不得
stage。

## Task 5: Implement Cell-Aware Primary Disposition

**Files:**

- Modify: `backend/app/candidates/disposition.py`
- Modify: `backend/tests/unit/candidates/test_disposition.py`

- [x] **Step 1: Write the decision table tests**

扩展 internal decision literal：

```python
Literal["reference_context", "non_inspection", "ambiguous"]
```

测试固定 precedence：

```text
technical requirement
existing exact metadata / scale / section label
high-confidence layout cell
same-page WELLI watermark
remaining P0-A1-R1 number / Roman / repeated overlay
parser fallback
```

测试行为：

| Evidence | Expected |
| --- | --- |
| title metadata value | `reference_context/welli_title_metadata_value` |
| title approval value | `reference_context/welli_title_approval_context` |
| revision fixed header | `non_inspection/welli_revision_header` |
| revision marker exact row integer | `reference_context/welli_revision_marker` |
| revision plain description | `reference_context/welli_revision_description` |
| archive exact label | `non_inspection/welli_archive_label` |
| archive record | `reference_context/welli_archive_record` |
| page-frame number | `non_inspection/welli_page_frame_number` |
| confirmed watermark ID | `non_inspection/welli_same_page_watermark` |
| unknown/edge/conflict/body | no layout decision |

revision marker `1/2/3` 即使 `has_visual_context=True` 也必须由 confirmed marker cell
处理。其他工程 visual context 保留现有 yield。

- [x] **Step 2: Write engineering-preservation tests**

单 observation preservation evidence：

- `parse_annotation()` 可识别；
- executable technical requirement；
- non-revision engineering visual context；
- `boundary_distance_mm < 1`；
- source line/span assignment 冲突；
- role 不唯一。

row-level test 使用稳定 `cell_id`：

```text
revision-description-3:
  其余
  3.2

3.2 is parser-recognizable
=> both lines receive no layout disposition
```

不得用 filename、hash、page index、observation ID 或 exact combined text 作例外。

- [x] **Step 3: Run tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/candidates/test_disposition.py
```

Expected RED: internal decision 不支持 `reference_context`，classifier 不接收 layout
evidence，revision marker 仍因 visual context 返回 `None`。

- [x] **Step 4: Implement the minimum layout decision API**

保持现有 `PRIMARY_DISPOSITION_RULE_VERSION="p0-a1-r1"` 供旧规则使用；layout decisions
显式使用：

```python
WELLI_LAYOUT_RULE_VERSION = "p0-a2-welli-layout/1"
```

建议给现有 classifier 增加 keyword-only evidence，而不是新增第二个 business Owner：

```python
def classify_primary_disposition(
    observation: TextObservation,
    *,
    has_visual_context: bool = False,
    repeated_overlay_observation_ids: AbstractSet[str] = frozenset(),
    layout_assignment: ObservationRegionAssignment | None = None,
    welli_watermark_observation_ids: AbstractSet[str] = frozenset(),
    engineering_preservation_observation_ids: AbstractSet[str] = frozenset(),
) -> PrimaryDispositionDecision | None:
    ...
```

layout helper 只返回 decision，不写 Coverage、candidate 或 inventory。若 assignment
不是 high-confidence sidecar 的成员、boundary 不安全或 observation 在 preservation
set 中，返回 `None`。

- [x] **Step 5: Run tests and verify GREEN**

Run Step 3 command. Expected: all pass.

- [x] **Step 6: Commit Task 5**

```bash
git add backend/app/candidates/disposition.py \
  backend/tests/unit/candidates/test_disposition.py
git commit -m "feat: route WELLI cells through primary disposition"
```

## Task 6: Integrate Text And Visual Coverage In Candidate Snapshot

**Files:**

- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/tests/e2e/test_offline_automatic_result.py`

- [x] **Step 1: Add matched-page snapshot fixtures**

扩展现有 `_page_with_observations()` / `_text_observation()` test helpers，使测试可以附加：

- `LayoutProfileMatch`；
- assignments with stable `cell_id`；
- associated `VisualObservation`；
- unmatched/no-sidecar control page。

不要改变现有 unmatched fixtures 的默认 shape。

- [x] **Step 2: Write failing text routing tests**

至少锁定：

```text
revision marker 1 + revision triangle visual
  -> no text candidate
  -> text reference_context/welli_revision_marker

title metadata value
  -> text reference_context

page-frame 1
  -> text non_inspection

same-page watermark
  -> text non_inspection

revision-description-3: 其余 + 3.2
  -> neither gets layout noise disposition
  -> existing candidate or ambiguous path remains

technical requirement inside overlapping template region
  -> existing global requirement candidate

OCR observation appended after match
  -> no layout decision

unmatched page
  -> snapshot canonical bytes unchanged
```

- [x] **Step 3: Write failing visual routing tests**

构造三个 cases：

1. visual 关联 selected Native line 及其真实 child spans；canonical relation
   投影后只剩同一 high-confidence match 中的 layout-safe `non_inspection` line：
   - visual Coverage = `non_inspection/welli_layout_visual_context`
   - `requires_confirmation=False`
   - visual ID 不在 `required_visual_observation_ids`
2. visual 关联 layout-safe `reference_context` text：
   - visual Coverage = `reference_context/welli_layout_visual_context`
   - ID 不 required
3. visual 关联 candidate/ambiguous/missing/different-match/preserved text：
   - visual Coverage = `ambiguous`
   - `requires_confirmation=True`
   - ID 必须 required

所有 cases 都保留 visual identity 和 `bbox_pdf`。

另加 fail-closed cases：

- associated span 的 `parent_region_id` 为空；
- parent line 跨页；
- visual 关联 span 但没有同时关联其 parent line；
- parent ID 存在但不是 selected Native line；
- 同一 span relation 映射到冲突 parent identity。

- [x] **Step 4: Run snapshot tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/e2e/test_offline_automatic_result.py
```

Expected RED: current snapshot 未消费 layout sidecar，所有 visual IDs 仍为
`ambiguous` 且 required。

- [x] **Step 5: Precompute immutable page layout context**

在 `candidate_snapshot_from_inventory()` 开始处按 page 建立：

```text
observation_id -> assignment
cell_id -> assigned observation IDs
page -> same-page watermark IDs
page -> engineering-preservation IDs
```

row preservation 先完整计算，再进入 sequential candidate loop，避免处理顺序影响同
row 较早 observation 的结果。Candidate Snapshot 不重开 PDF、不读取 raw drawings。

调用 primary classifier 时传递当前 observation 的 evidence。Coverage 继续逐 source
写一次，并保存 layout reason/version。

- [x] **Step 6: Derive visual dispositions from final text decisions**

text loop 完成后先建立：

```python
text_coverage_by_id = {
    entry.observation_id: entry
    for entry in coverage_entries
}
```

visual source 只有在所有 associated text relations 都满足 design gate 时才可 resolve。
实现必须逐项检查：

```text
associated text IDs non-empty
selected Native line ID -> canonical self
Native span ID -> canonical parent only when:
  same page
  span.parent_region_id points to that selected Native line
  visual explicitly associates both span and parent
orphan/cross-page/unpaired/conflicting span -> unresolved
deduplicated canonical lines all have a high-confidence assignment
all assignments share page_index/profile_id with the visual page
no canonical line is in the engineering-preservation set
every canonical line Coverage reason/version is a P0-A2 layout-safe decision
no canonical line Coverage is candidate/ambiguous/missing/conflicting
```

不能仅凭任意既有 `non_inspection`（例如不在模板内的 generic rule）推断 visual 已被
layout resolve。projection 不为 span 新建 Coverage、不改写 visual relation，也不把
span 提升为 Candidate Snapshot text grain。

规则：

```text
all text dispositions == non_inspection
  -> visual non_inspection

all text dispositions in {non_inspection, reference_context}
and at least one reference_context
  -> visual reference_context

otherwise
  -> visual ambiguous + required
```

resolved visual Coverage 使用 reason/version：

```text
welli_layout_visual_context
p0-a2-welli-layout/1
```

`required_visual_observation_ids` 只按 page/input stable order 收集 unresolved IDs。

- [x] **Step 7: Run snapshot tests and verify GREEN**

Run Step 4 command. Expected: all pass.

- [x] **Step 8: Verify Coverage exactly once**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/candidates/test_coverage.py \
  tests/e2e/test_offline_automatic_result.py
```

Expected:

- selected text + visual IDs 每个恰有一条 Coverage；
- `blocking_count == 0` for valid fixtures；
- resolved visual IDs 不需要 `advisor_review`；
- unmatched fixture 输出不变。

- [x] **Step 9: Commit Task 6**

```bash
git add backend/app/processing/automatic_result.py \
  backend/tests/e2e/test_offline_automatic_result.py
git commit -m "feat: preserve layout dispositions in candidate coverage"
```

## Task 7: Enforce Required Visual IDs In Planner And Advisor

**Files:**

- Modify: `backend/app/candidates/symbol_review.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`

- [x] **Step 1: Write planner filtering tests**

修改 test helper 允许传入 explicit required IDs，然后锁定：

```text
page visual IDs = resolved-a, unresolved-b, resolved-c
snapshot required IDs = unresolved-b
plan_visual_batches() schedules exactly unresolved-b
```

同时测试：

- empty required set 返回 per-page empty batches；
- required IDs 的 input order 不改变 stable schedule；
- required ID 不存在于 supplied pages 时 fail closed；
- budget 只计算 required observations；
- 现有 all-required fixture 的排序和 overflow 行为不变。

- [x] **Step 2: Run planner tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/candidates/test_symbol_advisor.py
```

Expected RED: `plan_visual_batches()` 仍调度 `page.visual_observations` 全集。

- [x] **Step 3: Filter scheduling by required IDs**

在 `plan_visual_batches()` 开始冻结 required set：

```python
required_ids = frozenset(snapshot.required_visual_observation_ids)
available_ids = {
    item.observation_id
    for page in pages
    for item in page.visual_observations
}
missing = required_ids - available_ids
if missing:
    raise ValueError("required visual observation is absent from pages")
```

每页 `ordered` 只包含 ID 在 required set 的 observations，再复用现有 priority、
packing 和 budget logic。不要把 disposition logic 下沉到 planner。

- [x] **Step 4: Run planner tests and verify GREEN**

Run Step 2 command. Expected: all pass.

- [x] **Step 5: Write Advisor non-projection tests**

构造 snapshot：

```text
resolved visual Coverage = reference_context
required visual IDs = empty
text routes = empty
```

验证：

- Provider factory 不构造；
- `CandidateAdvisor.review()` 返回与 input snapshot 相等；
- resolved visual Coverage 不增加 `advisor_review`；
- 不产生 `visual_no_detection`；
- candidates、source signals、provider call IDs 不变。

再构造 mixed page：

```text
resolved-a not required
unresolved-b required
```

验证只有 `unresolved-b` 进入 batch/projection，`resolved-a` Coverage byte-equivalent。

- [x] **Step 6: Run Advisor tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/candidates/test_advisor.py
```

Expected RED: current Advisor 的 `project_visual_page()` 仍收到整页 visual observations，
把 resolved source 覆盖为 `visual_no_detection`。

- [x] **Step 7: Limit Advisor projection to required/scheduled observations**

在 `CandidateAdvisor.review()` 中从 required set 构建 filtered visual mapping，并让：

```text
batch lookup
geometry reconstruction consumption
project_visual_page(visual_observations=...)
visual coverage replacement
visual signal append
```

只处理 required visual IDs。layout-resolved entries 不经过 visual decision loop。

保留现有 early return：

```python
if not routes and not any(visual_batches):
    return snapshot
```

不得修改 Provider adapter、schema validation、cache key 或 retry budget。

- [x] **Step 8: Run combined visual tests and verify GREEN**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/candidates/test_symbol_advisor.py \
  tests/unit/candidates/test_advisor.py
```

Expected: all pass；existing all-required visual behavior unchanged。

- [x] **Step 9: Commit Task 7**

```bash
git add backend/app/candidates/symbol_review.py \
  backend/app/candidates/advisor.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_advisor.py
git commit -m "fix: restrict visual Advisor to unresolved sources"
```

## Task 8: Run The Fixed Real-PDF Diagnostic Gate

**Files:**

- Create: `backend/tests/helpers/welli_layout_regression.py`
- Create: `backend/tests/unit/helpers/test_welli_layout_regression.py`
- Modify: 本计划文件的 `Execution Results`
- Verify only: production/test files

- [x] **Step 1: Write failing diagnostic helper tests**

新增 test-only、read-only diagnostic helper，并先锁定：

- 从两个 roots 递归发现 `.pdf`；
- 以 source SHA-256 去重，同一 PDF 在两个 roots 只处理一次；
- stable order 只按 SHA-256，不依赖 private filename/path；
- output 不包含 root、basename、raw text 或 PDF bytes；
- 对 current pages 运行正常 snapshot；
- 对 `replace(page, layout_profile_match=None)` 运行同 code 的 P0-A1-R1 control
  snapshot；
- current/control candidate source IDs、Coverage reasons 和 required visual IDs 可比较；
- canonical JSON 使用 `sort_keys=True` 和固定 separators；
- 同一 synthetic inputs 两次输出 byte-identical。

固定 output schema：

```json
{
  "schema_version": "welli-layout-regression/1",
  "report": {
    "input_summary": {
      "unique_document_count": 0,
      "duplicate_document_count": 0,
      "page_count": 0
    },
    "documents": [
      {
        "source_sha256": "...",
        "page_count": 0,
        "parseable_page_count": 0,
        "unsupported_page_count": 0,
        "matched_page_count": 0
      }
    ],
    "aggregate": {
      "control_candidate_source_count": 0,
      "current_candidate_source_count": 0,
      "candidate_source_ids_rerouted": 0,
      "revision_marker_reroutes": 0,
      "revision_description_reroutes": 0,
      "title_metadata_reroutes": 0,
      "page_frame_reroutes": 0,
      "watermark_native_line_count": 0,
      "revision_engineering_preserved_line_count": 0,
      "resolved_visual_observation_count": 0,
      "required_visual_observation_count": 0,
      "resolved_visual_ids_in_planned_batches": 0,
      "coverage_blocking_count": 0
    }
  },
  "report_sha256": "..."
}
```

`report_sha256` 只对 canonical `report` object 计算，避免 self-hash。测试必须拒绝
空 root env、non-PDF input 和 duplicate observation identity。

- [x] **Step 2: Run helper tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/helpers/test_welli_layout_regression.py
```

Expected RED: diagnostic helper/module 尚不存在。

- [x] **Step 3: Implement the read-only helper**

最小公开函数：

```python
def discover_unique_pdfs(roots: Sequence[Path]) -> tuple[Path, ...]:
    ...


def build_welli_layout_report(pdf_paths: Sequence[Path]) -> dict[str, object]:
    ...


def canonical_report_bytes(report: Mapping[str, object]) -> bytes:
    ...
```

每个 PDF 的对照路径固定为：

```python
pages = tuple(build_inventory(pdf_path))
current = candidate_snapshot_from_inventory(pages)
control_pages = tuple(
    replace(page, layout_profile_match=None)
    for page in pages
)
control = candidate_snapshot_from_inventory(control_pages)
```

这使 baseline 与 current 使用同一 code/input，只移除 P0-A2 sidecar，不需要旧
worktree、数据库或隐藏 source-ID allowlist。helper 只能读取 PDF 和写显式 `--output`
文件；不调用 OCR Provider、CandidateAdvisor、network、review、freeze 或 export。

CLI 固定读取：

```text
QI_CURRENT_FOUR_SOURCE_ROOT
QI_WELLI_REGRESSION_SOURCE_ROOT
```

并支持：

```text
--output <json path>
```

stdout 只打印 schema version、aggregate counts 和 `report_sha256`，不打印 private
paths。

- [x] **Step 4: Run helper tests and verify GREEN**

Run Step 2 command. Expected: all pass.

- [x] **Step 5: Resolve the approved read-only corpus**

运行脚本只能从环境变量读取用户本地 roots：

```bash
export QI_CURRENT_FOUR_SOURCE_ROOT="/approved/read-only/root"
export QI_WELLI_REGRESSION_SOURCE_ROOT="/approved/read-only/root"
```

实际运行时替换为当前机器已批准路径，但不得把绝对路径、文件名清单、PDF 内容或
private metadata 写入 repo。report 只记录 source SHA-256、页数、support route 和
aggregate metrics。

- [x] **Step 6: Run the deterministic automatic path twice**

Run from `backend/`:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python tests/helpers/welli_layout_regression.py \
  --output /tmp/welli-layout-regression-run-1.json

PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python tests/helpers/welli_layout_regression.py \
  --output /tmp/welli-layout-regression-run-2.json

cmp /tmp/welli-layout-regression-run-1.json \
  /tmp/welli-layout-regression-run-2.json

sha256sum /tmp/welli-layout-regression-run-1.json
```

Expected: 两次 command exit `0`，`cmp` exit `0`。执行边界：

```text
PDF bytes
-> build_inventory()
-> current snapshot
-> sidecar-stripped control snapshot
-> plan_visual_batches() for measurement only
-> canonical aggregate report
```

- [x] **Step 7: Verify the fixed corpus gates**

必须原样记录实际结果，并检查：

```text
documents/pages                         = 15 PDFs / 17 pages
parseable high-confidence matches       = 15
scanned/unsupported residual            = 2
safe candidate reroutes                 = 56
revision marker reroutes                = 45
plain revision description reroutes     = 1
title metadata candidate reroutes       = 7
page-frame candidate reroutes           = 3
WELLI watermark Native lines            = 184
其余 + 3.2                               = preserved, not table noise
Coverage completeness                   = exact once, blocking not increased
layout-resolved visual eligible batches = 0
unresolved visual batches               = separately reported
```

若任何固定 count 不符，不更新阈值或 allowlist；停止并把 source hash、page/profile、
reason delta 记录为 blocker。

- [x] **Step 8: Record the determinism boundary**

记录两个文件的相同 SHA-256。不得把当前 baseline
`ed8b8f4eae17ae5ae84d7faec815845daac9380083c0818adc222d2d24a8dc`
误写成 post-change expected hash；它只用于识别 pre-P0-A2 baseline。

- [x] **Step 9: Report evidence in three separate layers**

**Automatic capability**

- profile match/support counts；
- candidate/Coverage dispositions；
- exact safe reroutes；
- required/resolved visual IDs；
- repeat determinism；
- 无人工修改。

**Human correction cost**

- layout-resolved noise 不再出现在 candidate/Advisor queue 的计数；
- unresolved/ambiguous 数量；
- 当前没有 Quality Owner item/group ground truth，因此 correction time 与正式
  false-exclusion rate 标为 `unknown`。

**Final delivery correctness**

- 本 Task 未运行 ReviewedResult freeze、formal numbering、balloon placement、
  PDF/Excel/manifest；
- 明确标为 `not verified`，不得用 automatic metrics 代替。

- [x] **Step 10: Record results and commit**

把 commands、actual counts、canonical hash、residuals 和 evidence boundary 写入本
计划 `Execution Results`，然后：

```bash
git add backend/tests/helpers/welli_layout_regression.py \
  backend/tests/unit/helpers/test_welli_layout_regression.py \
  docs/superpowers/plans/2026-07-30-p0-a2-welli-template-aware-layout-noise-routing.md
git diff --cached --check
git diff --name-only --cached
git commit -m "test: add deterministic WELLI layout regression"
```

Expected staged paths 必须精确为上述三个文件。`/tmp` reports 不提交。

若 Quality Owner 后续要求把 corpus 变成 formal Harness receipt，必须另行授权
Harness evaluator/artifact schema；本 Task 不静默修改 `.agent/harness/`。

## Task 9: Run Focused/Full Verification And Independent Review

**Files:**

- Modify: 本计划文件的 `Execution Results`
- Verify only: all implementation/test files

- [x] **Step 1: Run the focused P0-A2 suite**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider \
  tests/unit/pdf/test_layout_profiles.py \
  tests/unit/pdf/test_inventory.py \
  tests/unit/pdf/test_runtime_ocr.py \
  tests/integration/test_pdf_inventory.py \
  tests/unit/candidates/test_disposition.py \
  tests/unit/candidates/test_coverage.py \
  tests/unit/candidates/test_symbol_advisor.py \
  tests/unit/candidates/test_advisor.py \
  tests/unit/helpers/test_welli_layout_regression.py \
  tests/e2e/test_offline_automatic_result.py
```

Expected: exit `0`。若 DB-dependent tests 无法连接配置的 PostgreSQL，必须使用仓库现有
test DB setup 后复跑；不得把 pure-test pass 冒充完整 focused pass。

- [x] **Step 2: Run the full backend suite**

Run from `backend/` with the repository test database available:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q -p no:cacheprovider
```

Expected: exit `0`。记录实际 pass/warning count；若环境 blocker 未解决，明确标记 full
suite 未通过，不降低 gate。

- [x] **Step 3: Run the contract drift check**

Run from repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python .agent/harness/scripts/check-contracts.py
```

Expected: exit `0`，无 contract drift。P0-A2 是 additive sidecar 和内部 routing，
不应要求修改 contract matrix。

- [x] **Step 4: Inspect the final diff**

```bash
git status --short
git diff --stat main...HEAD
git diff --check main...HEAD
git diff --name-only main...HEAD
```

Expected:

- 只有 allowed paths；
- no whitespace errors；
- no database/frontend/Provider schema/runtime changes；
- no PDF binary、host path 或 generated cache；
- 每个 production change 都有对应 RED/GREEN test。

- [x] **Step 5: Run independent read-only review**

Reviewer 必须给出 `accept / accept with concerns / reject`，并检查：

- profile 不能仅凭 page size 命中；
- matcher 不读 filename/hash/page allowlist；
- assignment 使用 Native line、stable `cell_id` 和 conservative boundary；
- `其余` + `3.2` row-level veto 不依赖 sample special case；
- technical requirement、drawing body、OCR 和 unmatched page 不回归；
- every selected source has exact-one Coverage；
- resolved visual IDs 退出 required/batch/projection；
- unresolved visual path、Provider schema/retry/cache 不回归；
- plan 中 automatic、human correction、final delivery 三层证据未混淆。

任何 blocking issue 必须回到对应 Task 用新的 RED→GREEN 修正，再重跑 Task 9。

- [x] **Step 6: Record final evidence**

更新 `Execution Results`：

- commit list；
- RED/GREEN commands/results；
- focused/full/contract results；
- corpus diagnostic；
- reviewer verdict；
- remaining risks；
- rollback commit boundaries。

提交：

```bash
git add docs/superpowers/plans/2026-07-30-p0-a2-welli-template-aware-layout-noise-routing.md
git commit -m "docs: close P0-A2 layout routing verification"
```

## Acceptance Evidence

### Automatic Capability

- 15 parseable corpus pages high-confidence match；2 scanned pages保持 unsupported。
- `56` 个已确认 template candidate leakage 安全退出 candidate path。
- `184` 个 exact WELLI watermark Native line observations 为
  `non_inspection/welli_same_page_watermark`。
- `其余` + `3.2` 不进入 table-noise disposition。
- visual 的合法 line + child-span relation 折叠到 selected Native line；orphan 或
  relation conflict 保持 unresolved。
- every selected text/visual source has exact-one Coverage。
- resolved visual sources 不进入 required set、Provider batch 或 Advisor projection。
- unmatched/no-sidecar snapshot 与 P0-A1-R1 baseline byte-identical。
- two-run canonical report byte-identical。

### Human Correction Cost

- 报告自动 candidate/ambiguous/reference/non-inspection 数量和 resolved/unresolved
  visual queue 数量；
- 不把人工修改后的 working copy 混入 automatic metrics；
- 在 Quality Owner ground truth 缺失时，不声明正式 precision/recall、false exclusion
  rate 或 review time reduction。

### Final Delivery Correctness

- 本计划不修改 review/freeze/formal numbering/balloon/export；
- 只有后续运行完整 ReviewedResult→PDF/Excel/manifest 闭环后才能报告最终交付正确性；
- P0-A2 完成不等于正式气泡或交付物完成。

## Risk And Rollback Matrix

| Risk | Preventive gate | Rollback point |
| --- | --- | --- |
| 仅凭页面尺寸误命中其他模板 | geometry + anchor quorum + negative fixtures | revert Task 2/4 |
| title optional grid 导致 false no-match | `x=93` evidence-neutral test | revert Task 2 |
| 整行 revision 被误删 | stable `cell_id` + row preservation | revert Task 5/6 |
| `其余 3.2` sample-specific hardcode | no filename/hash/text special-case review | reject Task 5 |
| OCR 被模板证据误路由 | Native-line-only assignment + append test | revert Task 4/6 |
| boundary text 被过度过滤 | signed distance + `<1 mm` veto | revert Task 3/5 |
| watermark 误伤正常文字 | exact text + angle + 2D grid + count | revert Task 3 |
| visual noise 经 Advisor 回流 | required-set planner + filtered projection | revert Task 7 |
| child span 被当成 missing relation | canonical parent-line projection + orphan/mismatch negatives | revert Task 6 |
| unresolved visual 被漏调 | missing-ID fail closed + mixed relation tests | revert Task 7 |
| corpus 过拟合 | in-sample label + negative fixtures + later holdout | no generalization claim |
| scanned pages 被伪装成功 | explicit unsupported count | reject Task 8 |
| Provider zero-call 被夸大 | 只对 layout-resolved IDs 报 eligible batch 0；unresolved 分开 | correct report |

## Evidence Boundary

- 当前 15-PDF/17-page corpus 是 rule discovery 与回归使用的同一 cohort，属于
  in-sample diagnostic。
- 缺少 Quality Owner item/group ground truth，因此本计划不能证明 candidate
  precision/recall、composite grouping accuracy、balloon-required accuracy 或正式
  false exclusion rate。
- layout-resolved source 的 eligible Provider batches 为 `0`；其他 unresolved
  source 继续按现有 Advisor path 单独计数。Task 8 不运行 CandidateAdvisor，因此
  不把离线 batch 计数冒充 post-Advisor live-call proof。
- 2 个 scanned/unsupported pages 不在 P0-A2 matcher 成功范围。
- technical requirement block grouping 和 local VLM Advisor 是后续独立工作。
- A3 portrait 在当前 corpus diagnostic 中可验证，但若 formal Harness physical-page
  helper 尚未覆盖该 variant，不得把 offline diagnostic 冒充 formal Harness receipt。

## Execution Results

### Execution Selection

- Authorization: 用户于 `2026-07-30` 明确调用
  `$superpowers:executing-plans` 执行本计划。
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-07-30-p0-a2-welli-template-aware-layout-noise-routing.md`
- Selection evidence: 用户点名本计划及 approved design；worktree
  `codex/welli-template-layout-filtering-spec` clean，`HEAD=85d975a`，实现基线仍为
  `main@f9c8c2d`。
- Validation action: `continue`
- Writer ownership and order: 当前主线程是唯一 writer，严格按 Task 1→9 顺序；
  不并发修改 coupled file groups。
- Problem boundary: 只实现 versioned WELLI layout evidence、cell-aware disposition、
  same-page watermark、text/visual Coverage 和 required visual routing。
- Single owner: `backend/app/candidates/disposition.py` 继续是 primary disposition
  唯一 Owner；`build_inventory()` 只生产 layout evidence。
- Old path to preserve: technical requirement、P0-A1-R1 generic disposition、
  grouping/parser/coarse fallback、unmatched/OCR path 和 unresolved visual Advisor
  path。
- Unchanged contract: observation identity/bbox/lineage、Coverage exact-once、
  Provider schema/retry/cache、review/freeze/numbering/balloon/export 均不变。
- Next verification: Task 1 schema serialization/immutability tests先 RED，再最小
  schema GREEN。

后续只有在各 Task 的 RED/GREEN、固定 corpus diagnostic、focused/full suite、
contract check 和独立 reviewer 均有真实证据时，才继续更新本节。

### Task 8 Diagnostic Gate

- Initial status: `rejected / blocker`。Task 9 当时未获准开始；固定 count 未调整，未增加
  filename/hash/source-ID allowlist。
- Helper TDD:
  - RED:
    `tests/unit/helpers/test_welli_layout_regression.py` 因 module 不存在而 collection
    error。
  - GREEN:
    `python -m pytest -q -p no:cacheprovider
    tests/unit/helpers/test_welli_layout_regression.py` → `4 passed`。
  - 首次 live run 暴露 helper 把 Native span 错当 snapshot expected identity；安全
    计数证明 15 个文档的差集只包含 Native span，`snapshot_only_count=0`。helper
    改为复用 production `selected_observations()` /
    `selected_visual_observations()` Owner，并新增 line + child span 回归用例。
- Corpus input summary（不记录 private path、basename 或 raw text）:
  - unique documents: `15`
  - duplicate documents: `0`
  - pages: `17`
  - parseable/high-confidence matched pages: `15`
  - scanned/unsupported pages: `2`
- Determinism:
  - run 1 exit: `0`
  - run 2 exit: `0`
  - `cmp` exit: `0`
  - canonical `report_sha256`:
    `e071d6b8977f7951843f42ca54462aee04397da28ec10f9af2ebcc3b573c55eb`
  - identical report-file SHA-256:
    `a491e809179c5ce1f42891f01da803032050bc31418f96537716a4d84930f8d6`
- Actual aggregate:
  - control candidate source count: `1312`
  - current candidate source count: `1267`
  - safe candidate reroutes: `45`（expected `56`）
  - revision marker reroutes: `45`（expected `45`）
  - revision description reroutes: `0`（expected `1`）
  - title metadata candidate reroutes: `0`（expected `7`）
  - page-frame candidate reroutes: `0`（expected `3`）
  - WELLI watermark Native lines: `30`（expected `184`）
  - revision engineering-preserved lines: `5`
  - layout-resolved visual observations: `50`
  - required visual observations: `1022`
  - resolved visual IDs in planned batches: `0`
  - Coverage blocking count: `0`

#### Blocker Evidence By Source Hash / Page / Profile

- Revision-description delta:
  - `322d56b00456f495830386b8dc50a32e34086a5bc66d4735e2c3c735d5fbc57d`,
    page `0`, `welli-a4-portrait/1`: one control candidate assigned
    `revision_description` remains a candidate.
  - `8fffd93fa7f055f9fe1a7da25bc85630910bdfc2ea86b2ace6ec54979f0a515e`,
    page `0`, `welli-a3-landscape/1`: one control candidate assigned
    `revision_description` remains a candidate.
  - Result: preservation retains both rows; the fixed gate requires one safe description
    reroute and one engineering exception.
- Title candidate delta:
  - `322d56b00456f495830386b8dc50a32e34086a5bc66d4735e2c3c735d5fbc57d`,
    page `0`, A4 portrait: `title_approval_context=1`.
  - `44a51de5112ebf92319bcbaed65642643818a1b0ed5bfbcb8308b673dab38392`,
    page `0`, A3 landscape: `title_metadata_value=1`.
  - `687e7b9fb46e9a55cb52e32669b3c9577e6deccf5bb1b12175309440a5d7739e`,
    page `0`, A3 portrait: `title_approval_context=1`.
  - `a33a163a2580a46227f7840283b28399690316f06390afb52b5a70dad0cc6d06`,
    page `0`, A4 portrait:
    `title_approval_context=1,title_metadata_value=1`.
  - `ffee22f2e392f309d3d0acfc2edadc4a8d5330a9bc28009263af5d8597074a86`,
    page `0`, A4 portrait: `title_metadata_value=2`.
  - Result: all `7` control candidate sources remain candidates; current matcher role split is
    four metadata and three approval, and the broad engineering-preservation path prevents
    the expected safe reroutes.
- Page-frame delta:
  - The three parseable A4 pages above each produce two page-frame assignments, but none of
    the three expected control candidate source IDs joins those assignments.
  - Result: `page_frame_reroutes=0`; candidate/assignment lineage does not converge.
- Watermark delta:
  - exact text + `-30° ±2°` Native-line candidates total `184`, matching the design
    baseline; lattice acceptance totals only `30`.
  - Accepted pages are the A4 portrait sources
    `322d56b00456f495830386b8dc50a32e34086a5bc66d4735e2c3c735d5fbc57d`
    page `0` (`9`),
    `a33a163a2580a46227f7840283b28399690316f06390afb52b5a70dad0cc6d06`
    page `0` (`9`), and A3 portrait
    `687e7b9fb46e9a55cb52e32669b3c9577e6deccf5bb1b12175309440a5d7739e`
    page `0` (`12`).
- The remaining `154` exact text+angle sources across `11` matched pages are rejected by
    the lattice evidence, so the current watermark contract has corpus false negatives.

### Task 8A Bounded Amendment

- Authorization: 用户于 `2026-07-30` 批准先前只读诊断提出的 bounded amendment。
- Change surface:
  - production 仅修改 `backend/app/pdf/layout_profiles.py`、
    `backend/app/processing/automatic_result.py` 和
    `backend/app/candidates/disposition.py`；
  - regression helper 仅修正 title metadata/approval 聚合口径；
  - 对应 layout/disposition/offline regression tests 增加真实 failure-mode coverage；
  - 未调整 threshold，未增加 filename/hash/source-ID allowlist。
- Root-cause corrections:
  - watermark 改为 deterministic page-level lattice quorum；partial outer row 不再使
    已满足 exact text/angle/count/spacing 的整页失败；
  - parser/grouping/visual engineering preservation 限定为
    `revision_description` row，coarse keyword/type fallback 不再单独构成 veto；
  - page-frame assignment 使用 matched actual page dimensions，精确
    cell/text/target 可接触 physical page outer edge。
- TDD:
  - RED focused command: `8 failed, 2 passed`；失败分别覆盖 actual-height assignment、
    partial outer-row lattice、page-frame edge disposition、两类 title value、
    plain revision prose、page-frame visual resolution 和 helper aggregate。
  - GREEN focused command: `10 passed in 0.88s`。
  - 扩展相关文件验证: `172 passed, 10 errors in 3.30s`；10 个 error 均发生在
    database fixture setup，原因是当前环境无法解析 host `postgres`，未出现 test
    assertion failure。该环境 blocker 不转换为通过。
- Fixed corpus gate:
  - repeated live runs: both exit `0`; `cmp` exit `0`
  - canonical `report_sha256`:
    `1acaccf12d07e7cd757b1516ebae45481816f09b6fc527262c344e3e62eccad8`
  - identical report-file SHA-256:
    `813a27ba5aa4d4dceb9e136e730cd08fd456fa6d839c247e0a7f2e847e21b9c6`
  - control/current candidate source count: `1312 / 1256`
  - safe candidate reroutes: `56`
  - revision marker/description reroutes: `45 / 1`
  - title metadata candidate reroutes: `7`
  - page-frame candidate reroutes: `3`
  - WELLI watermark Native lines: `184`
  - revision engineering-preserved lines: `4`
  - layout-resolved/required visual observations: `56 / 1016`
  - resolved visual IDs in planned batches: `0`
  - Coverage blocking count: `0`
- Status: `accepted`。Task 8 fixed aggregate、Coverage 和 determinism gate 已恢复；
  仅此 gate 的通过使 Task 9 重新具备开始资格，不等于 focused/full suite、contract
  check、independent review、freeze 或 export 已完成。

#### Evidence Boundaries

**Automatic capability**

- Profile support/match counts and deterministic current/control snapshots are verified.
- The fixed candidate/watermark aggregate, Coverage exact-once, zero resolved-visual batch
  leakage, and repeat determinism are verified.
- No human modifications, OCR Provider, CandidateAdvisor, network, review, freeze, numbering,
  balloon placement, or export ran.

**Human correction cost**

- Confirmed candidate queue reduction is `56`.
- Layout-resolved visual count is `56`; unresolved required visual count is `1016`.
- Quality Owner item/group ground truth is unavailable, so correction time and formal
  false-exclusion rate remain `unknown`.

**Final delivery correctness**

- ReviewedResult freeze, formal numbering, balloon placement, PDF/Excel/manifest generation
  and final delivery validation are `not verified`.
- Automatic diagnostic metrics are not delivery proof.

### Task 9 Verification And Independent Review

- Status: `accepted / complete`。focused suite、full backend suite、contract check、
  final diff audit 和 independent read-only review 均通过。
- Test database:
  - 初次宿主机 focused run 为 `320 passed, 10 errors in 3.62s`；10 个 error
    全部发生在 DB fixture setup，原因为 Compose-only hostname `postgres` 无法解析。
  - 使用两个先后创建的独立临时 PostgreSQL 17 containers，均先迁移到 Alembic
    `head`，未复用或修改共享数据库；验证结束后两个 container 均已删除。
- Pre-review verification:
  - focused P0-A2 suite: `330 passed in 2.34s`
  - full backend suite: `1116 passed, 1 warning in 47.12s`
  - warning: 既有 Starlette/httpx deprecation warning
  - contract check:
    `global_contracts=69, p0_contracts=111, mapped=101,
    implementation_only=10, unclassified=0, duplicate=0, missing_task=0,
    missing_selector=0, mirror_drift=0, bindings_drift=0,
    unbound_p0_stage_global=0, binding_relation_conflict=0`
- Review follow-up:
  - 第一次 independent review verdict 为 `accept`、无 blocking issue。
  - parent 复核额外发现 page-frame `<1 mm` 例外只检查 `cell_role`，理论上可能把
    internal band boundary 当作 physical outer edge。
  - follow-up RED: `3 failed`，分别证明 matcher 缺少 outer-edge evidence、
    disposition 放过 internal boundary、关联 visual 被错误 resolved。
  - follow-up GREEN: 最终 `5 passed in 0.81s`。matcher 只在 actual top `y=0`
    或 actual bottom `y=page_height` 接触时写入
    `physical_page_outer_edge` evidence；disposition 和 visual preservation
    只允许该 evidence 绕过 `<1 mm` veto。
  - follow-up fixed corpus 两次仍为
    `56 / 45 / 1 / 7 / 3 / 184`，`Coverage blocking=0`、
    resolved visual planned-batch leakage=`0`；canonical/report-file SHA-256
    均与 Task 8A 相同。
- Final post-follow-up verification:
  - focused P0-A2 suite: `332 passed in 2.24s`
  - full backend suite: `1118 passed, 1 warning in 44.49s`
  - contract check: 与上方相同，所有 drift/blocking counters 为 `0`
  - `git diff --check main...HEAD`: exit `0`
  - final changed paths: `19`，仅包含 approved
    PDF/layout/disposition/Coverage/Advisor implementation、对应 tests/helpers
    和当前 plan/design；无 database/frontend/Provider schema/runtime、PDF binary、
    host path 或 generated cache。
- Final independent read-only review:
  - mechanism: `claude` skill review mode，tool-less、完整 `main...HEAD` diff。
  - verdict: `accept`
  - blocking issues: `none`
  - reviewer 明确验证 physical outer-edge evidence 只能由 actual top/bottom edge
    产生；internal boundary 回到旧路径并保持 visual required；真实 outer-edge
    page-frame 继续路由和解决 visual。
  - non-blocking concerns: `_layout_snapshot_context()` 密度、watermark quorum
    `O(n²)` 和 revision grouping 的轻微重复计算；在当前每页 `<20` watermark
    candidates 和已覆盖 fixed corpus 边界下不构成 blocker。
  - reviewer limitation: corpus/runtime commands 不能由静态 diff 独立复现；verdict
    依赖代码/测试语义审查，实际 runtime evidence 仍由上方本地命令拥有。
- Commit list:
  - `71caddd` design baseline
  - `4b13193` design gap closeout
  - `85d975a` implementation plan
  - `43a15e9` execution authorization
  - `79b6cf5` immutable layout sidecar
  - `33d5a46` profile matcher
  - `3ac6f9c` cell/watermark assignments
  - `07f7214` inventory attachment
  - `974925d` primary disposition routing
  - `7ac4472` Coverage preservation
  - `09e45fd` unresolved-only Advisor routing
  - `596d007` deterministic regression helper
  - `27ef8ab` Task 8A blocker corrections
  - `d56e609` physical outer-edge evidence follow-up
- Rollback boundaries:
  - follow-up outer-edge behavior: `d56e609`
  - Task 8A corpus blocker corrections: `27ef8ab`
  - deterministic regression gate: `596d007`
  - production behavior must otherwise roll back in reverse dependency order from
    `09e45fd` through `79b6cf5`;不得单独保留 consumer 而移除其 sidecar/evidence
    producer。
- Remaining risks:
  - Quality Owner item/group ground truth 仍不可用，formal false-exclusion rate、
    correction time 和 human correction cost 仍为 `unknown`。
  - 两个 scanned/unsupported pages 仍不在 deterministic layout matcher 成功范围。
  - fixed corpus 只执行 automatic inventory/snapshot/batch measurement；未调用 live
    CandidateAdvisor Provider。Advisor-level resolved/unresolved behavior由 focused/full
    tests 覆盖，不冒充 live Provider evidence。
  - ReviewedResult freeze、formal numbering、balloon placement、
    PDF/Excel/manifest export 和 final delivery correctness 仍为 `not verified`。

### Post-Merge Closeout

- Status: `accepted / complete`。Tasks 1–9 和批准的 Task 8A amendment 均已完成；
  implementation 通过 integration checkpoint `3d00d15` 合入本地 `main`。
- Retired state: feature/integration branches、planning/integration/baseline worktrees
  和临时 PostgreSQL container 均已删除。
- Post-merge verification:
  - focused P0-A2 suite on `main`: `362 passed`
  - fixed corpus repeated aggregate: `56 / 45 / 1 / 7 / 3 / 184`
  - `Coverage blocking=0`
  - resolved visual planned-batch leakage=`0`
  - contract check: 所有 drift/blocking counters 为 `0`
  - backend suite excluding three independently reproduced baseline receipt failures:
    `1350 passed, 3 deselected, 1 warning`
- Baseline boundary: 三个
  `tests/contract/harness/test_receipt_policy.py` selector failures 已在未包含本计划
  implementation 的 `main@2cc661b` detached baseline 独立复现，因此不属于本计划
  regression；repository-wide full suite 不冒充全绿。
- Delivery boundary: 本 closeout 不执行 push、ReviewedResult freeze、formal numbering、
  balloon placement、PDF/Excel/manifest export 或 final delivery validation。
