# P0-A1 Candidate Noise Prefilter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 observation、parser 和正式编号契约的前提下，阻止明显元数据噪声进入 candidate，并将证据不足的独立数字保留为可审核的 `ambiguous`。

**Architecture:** 由 `app.candidates.disposition` 作为确定性 primary disposition 的单一 Owner；`candidate_snapshot_from_inventory()` 在 technical requirement 判定之后、composite/parser 之前调用该 Owner。所有 observation 仍写入 Coverage Ledger，规则判定附带 reason/version；未命中的 observation 继续沿用现有 grouping/parser/confidence 路径。

**Tech Stack:** Python 3.12、Pydantic/dataclass、pytest、现有 `qi-p0` Micromamba 环境

---

## Execution Record

- Lane: `Heavy`
- Selected task: `P0-A1`
- Selection evidence: 用户明确选择“P0-A1 规则降噪”；当前 `HEAD=b8a49e528c512a0caabf8288a160bc8706e8fa35`
- Baseline evidence: focused backend suite `271 passed in 0.93s`
- Single writer: 主线程
- Old path being replaced: 每个 Native/OCR 文本 observation 无 primary disposition 闸门即进入 composite/group/parser
- Unchanged contracts:
  - `parse_annotation("25")` 仍然是合法 parser 输入，避免破坏其他 caller。
  - 所有 observation 必须进入 Coverage Ledger。
  - technical requirement、复合标注和明确工程符号继续走现有识别路径。
  - 本任务不创建 VLM provider，不创建 formal balloon number，不改变 reviewed-result freeze gate。
- Rollback: revert 本任务实现 commit；运行本计划中的 focused regression command，确认旧 candidate 路径恢复且基线测试通过。

## Scope

本任务只处理：

- 精确匹配的标题栏/签字栏字段名：`设计`、`校对`、`审核`、`批准`、`签名`、`日期`、`重量`、`比例`、`图样代号`、`物料编码`
- 精确比例文本，如 `1:10`、`1:15`、`2:15`
- 精确剖视标签，如 `A-A`、`B-B`、`C-C`
- 同一规范化文本在至少两个页面、近似相同规范化位置重复出现的非工程语义水印/页眉文本
- 无工程符号和上下文的独立数字：不创建 candidate，Coverage disposition 为 `ambiguous`，必须人工确认

本任务明确不处理：

- 完整标题栏区域分割、更改栏、图框区域模型
- `I`、`II`、`IV`、`V` 的强制删除；这些仍为 `ambiguous`
- 技术要求 block 聚合、复合孔/GD&T grouping
- VLM、UI marker 语义、formal balloon number 或 export gate

## Task 1: Freeze Primary-Disposition Rules

**Files:**

- Modify: `backend/tests/unit/candidates/test_disposition.py`
- Modify: `backend/app/candidates/disposition.py`

- [x] **Step 1: Write failing unit tests for exact deterministic rules**

新增参数化测试，要求：

```python
@pytest.mark.parametrize(
    ("raw_text", "expected_disposition", "expected_reason"),
    [
        ("设计", "non_inspection", "exact_metadata_label"),
        ("1:10", "non_inspection", "drawing_scale"),
        ("A-A", "non_inspection", "section_view_label"),
        ("25", "ambiguous", "standalone_number"),
        ("II", "ambiguous", "standalone_roman_label"),
    ],
)
def test_classify_primary_disposition_is_conservative(...):
    ...
```

同时增加反例，确认 `Φ20`、`M6`、`R5`、`25±0.02`、`检查焊缝不得有裂纹` 不被规则误判。

- [x] **Step 2: Run the unit test and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q tests/unit/candidates/test_disposition.py
```

Expected: 新测试因 primary-disposition API 尚不存在而失败。

- [x] **Step 3: Implement the minimum classifier**

在 `backend/app/candidates/disposition.py` 增加：

```python
PRIMARY_DISPOSITION_RULE_VERSION = "p0-a1-v1"

@dataclass(frozen=True)
class PrimaryDispositionDecision:
    disposition: Literal["non_inspection", "ambiguous"]
    reason: str
    rule_version: str = PRIMARY_DISPOSITION_RULE_VERSION
    requires_confirmation: bool = False

def classify_primary_disposition(
    observation: Observation,
    *,
    repeated_overlay_observation_ids: AbstractSet[str] = frozenset(),
) -> PrimaryDispositionDecision | None:
    ...
```

规则顺序固定为：精确 metadata → scale → section label → standalone number → standalone Roman label → confirmed repeated overlay。仅做完全匹配，不做包含匹配。

- [x] **Step 4: Implement conservative repeated-overlay evidence**

增加纯函数：

```python
def repeated_page_overlay_observation_ids(
    observations: Sequence[Observation],
) -> frozenset[str]:
    ...
```

判定必须同时满足：

- 相同 `normalized_text`
- 出现在至少两个不同 `page_index`
- `bbox_normalized` 中心点落在同一个保守网格桶
- 文本不是空值、不是独立数字、不是明确工程标注、不是 technical requirement

- [x] **Step 5: Run the unit test and verify GREEN**

Run the same command.

Expected: `tests/unit/candidates/test_disposition.py` 全部通过。

- [x] **Step 6: Commit rule Owner**

```bash
git add backend/app/candidates/disposition.py \
  backend/tests/unit/candidates/test_disposition.py
git commit -m "feat: add conservative candidate noise disposition"
```

## Task 2: Integrate the Gate into Candidate Snapshot

**Files:**

- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/app/candidates/coverage.py`
- Modify: `backend/tests/e2e/test_offline_automatic_result.py`
- Modify: `backend/tests/unit/candidates/test_coverage.py`

- [x] **Step 1: Write failing end-to-end snapshot tests**

覆盖以下行为：

```text
设计 / 1:10 / A-A
  -> candidates=[]
  -> coverage.disposition=non_inspection
  -> disposition reason/version present

25 / II
  -> candidates=[]
  -> coverage.disposition=ambiguous
  -> requires_confirmation=true

same watermark on page 0 and page 1 at the same normalized position
  -> both coverage entries are non_inspection

Φ20 / M6 / R5 / 25±0.02 / executable technical requirement
  -> still create their existing candidate type
```

- [x] **Step 2: Run the focused tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q \
  tests/e2e/test_offline_automatic_result.py \
  tests/unit/candidates/test_coverage.py
```

Expected: 噪声仍进入 parser/candidate，且 CoverageEntry 尚无 rule evidence。

- [x] **Step 3: Extend CoverageEntry without breaking legacy serialization**

增加可选字段：

```python
disposition_reason: str | None = None
disposition_rule_version: str | None = None
```

仅在字段非空时写入 `to_dict()`，因此旧 fixture 和非规则路径输出保持不变。

- [x] **Step 4: Insert primary disposition after technical-requirement classification**

在 `candidate_snapshot_from_inventory()` 中：

1. 对本次 `_selected_observations()` 预计算 repeated-overlay IDs。
2. 每个 observation 先保留现有 technical requirement 判定。
3. technical requirement 未命中时调用 `classify_primary_disposition()`。
4. 命中时直接写 CoverageEntry 并跳过 composite/group/parser。
5. 未命中时继续原路径。

- [x] **Step 5: Run focused tests and verify GREEN**

Run the command from Step 2.

- [x] **Step 6: Commit candidate snapshot integration**

```bash
git add backend/app/processing/automatic_result.py \
  backend/app/candidates/coverage.py \
  backend/tests/e2e/test_offline_automatic_result.py \
  backend/tests/unit/candidates/test_coverage.py
git commit -m "feat: gate obvious noise before candidate parsing"
```

## Task 3: Regression, Failure-Path, and Independent Review

**Files:**

- Verify only; no production edits unless a verified defect requires a new TDD cycle

- [x] **Step 1: Re-run the candidate/PDF/contract baseline**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q \
  tests/unit/candidates/test_parser.py \
  tests/unit/candidates/test_grouping.py \
  tests/unit/candidates/test_disposition.py \
  tests/unit/candidates/test_coverage.py \
  tests/unit/candidates/test_confidence.py \
  tests/unit/pdf/test_coordinates.py \
  tests/unit/pdf/test_runtime_ocr.py \
  tests/contract/test_automatic_result.py \
  tests/contract/test_qwen_vl_provider.py \
  tests/e2e/test_offline_automatic_result.py
```

Expected: 全部通过，且先前 `271 passed` 基线没有回归。

- [x] **Step 2: Verify failure and rollback behavior**

确认：

- 不存在 feature flag、shadow writer 或第二个 disposition Owner。
- VLM/provider 不可用与本任务输出无关。
- 未命中的 observation 沿原路径处理。
- rule classifier 抛出异常时不会被静默转换为 formal success；测试应暴露失败。

- [x] **Step 3: Inspect the exact diff**

```bash
git diff HEAD~2 -- \
  backend/app/candidates/disposition.py \
  backend/app/candidates/coverage.py \
  backend/app/processing/automatic_result.py \
  backend/tests/unit/candidates/test_disposition.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/e2e/test_offline_automatic_result.py
```

确认每一行都追溯到 `P0-A1`，且没有 parser、VLM、frontend、numbering 或 export 变更。

- [x] **Step 4: Run independent read-only review**

Reviewer 必须给出 `accept / accept with concerns / reject`，重点检查：

- 规则是否会把真实工程标注误判为 `non_inspection`
- standalone number 是否保留 review/coverage
- technical requirement 是否优先于 repeated overlay
- Coverage Ledger 是否完整
- 是否出现隐藏 fallback 或第二个业务 Owner

- [x] **Step 5: Apply only verified review fixes through a new RED/GREEN loop**

若 reviewer 报告 blocker，先由主线程复核文件/测试证据，再以最小补丁修复并重新运行 Step 1；非阻断建议留给后续 `P0-B`。

## Acceptance Evidence

自动能力、人工成本和最终交付必须分开报告：

- Automatic:
  - 明确 metadata/scale/section/repeated-overlay 噪声不再创建 candidate。
  - 独立数字/Roman label 不再自动创建 candidate，但保留为 `ambiguous`。
  - 明确工程标注和 technical requirement 不回归。
- Human correction cost:
  - `non_inspection` 项不进入确认队列。
  - `ambiguous` 独立数字仍需人工确认，不能计为自动识别正确。
- Final delivery:
  - 本任务不声明 reviewed result、formal balloon、PDF/Excel/manifest 正确性提升。
  - 交付正确性仍由后续审核 freeze 与统一 reviewed-result gate 保证。

## Execution Results

- RED/GREEN:
  - primary-disposition API 缺失时 unit collection 明确失败。
  - snapshot 旧路径证明独立数字仍会直接创建 `linear_dimension`。
  - reviewer 发现 repeated-overlay 提前覆盖工程语义后，新增跨页焊接、粗糙度、GD&T、未注公差和技术要求回归，再完成 GREEN。
  - full-suite 发现 visual-context standalone number 回归后，新增 visual context 让行规则并完成 GREEN。
- Verification:
  - focused candidate/PDF/contract suite: `295 passed`
  - offline automatic-result DB e2e: `32 passed`
  - fresh PostgreSQL full backend suite: `986 passed, 1 warning`
- Independent review:
  - first verdict: `reject`
  - final verdict: `accept with concerns`
  - remaining concerns are fixed-sample evaluation and 5% normalized-position bucket stability；均不扩大本任务生产范围。
- Commits:
  - `662d21f` — deterministic disposition Owner
  - `f91a826` — candidate snapshot gate and Coverage evidence
  - `104e5b1` — repeated engineering observation preservation
  - `6267ce1` — visually contextualized standalone number preservation
