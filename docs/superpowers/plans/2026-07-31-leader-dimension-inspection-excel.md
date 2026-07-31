# Leader Dimension Inspection Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将唯一正式 `sip-v1` 原位升级为领导批准的“机械图纸尺寸质量检测表”，让质检人员填写检测值并由受控 Excel 公式自动判定 `OK/NG`。

**Architecture:** `ReviewService` 与 `sip_mapping.py` 保持现有 reviewed-item 和
inspection-guidance Owner；`ExportService._excel_rows()` 原位替换为新的尺寸质量表
row projection。新增纯合同模块 `sip_workbook_contract.py`，由 builder、renderer、
workbook validator 和 staged validator 共同消费 numeric/text 分类与 trusted formula，
避免循环依赖和第二状态源。`template_registry.py` 继续唯一登记 `sip-v1` v3 资产、
mapping、hash、capacity 和受控范围。

**Tech Stack:** Python 3.11、openpyxl、Pillow、PyMuPDF、pytest、LibreOffice headless、
Micromamba `qi-p0`

## Global Constraints

- Selected lane: `Heavy`。
- Current plan: 本文件是“机械图纸尺寸质量检测表正式实现”的唯一 current plan。
- Design source:
  `docs/superpowers/specs/2026-07-31-leader-dimension-inspection-excel-design.md`。
- Selection evidence: 用户查看非生产对比稿后明确要求“写 specs 和 plan”。
- Validation action: `replan`；只 supersede
  `2026-07-31-sip-auto-mapping-and-exception-review-design.md` 中“不修改固定 Excel
  模板、列 mapping”的 non-goal。
- Problem boundary:
  `frozen reviewed item -> formal SIP Excel visible row and trusted workbook formula`。
- Single Owner:
  - template identity/layout: `backend/app/exports/template_registry.py`；
  - v3 value/formula contract: `backend/app/exports/sip_workbook_contract.py`；
  - formal Excel row projection: `ExportService._excel_rows()`；
  - item membership: existing `ReviewService` lifecycle。
- Old path action: v2 template、mapping、sheet name、七列 visible mapping 和 pinned
  hashes 全部原位 `replace`；不得保留 v2 flag、fallback、shadow、legacy renderer 或
  第二 template ID。
- Unchanged contracts: item review/confirm、frozen `sip_metadata` 五字段形状、
  `generate_sip_table`、SIP exception-only UI、
  review commands/OpenAPI、database schema、formal numbering、`气泡图`、PDF/Excel/
  manifest identity、staging/atomic publish 和 historical artifact immutability。
- Formula trust: PDF/OCR/LLM/user text 始终写为 plain string；只有登记 template 的
  result formulas 可执行。
- Measurement boundary: server 不写、不保存检测值或结果；每次正式导出 H 列为空。
- No recognition rewrite: 不修改 candidate parser、Provider、OCR、symbol routing 或
  technical-requirement classifier。
- Single writer: production tasks 按 Task 1 → Task 5 串行执行；explorer/reviewer
  始终只读。
- TDD: 每项 runtime behavior 必须先跑对应 RED，再做最小实现。
- Git: 每个 task 只 stage 明列文件；禁止 stage `.pyc`、Harness runs、`.local` 对比稿
  或其他既有 dirty files。
- Environment: 所有 Python checks 使用
  `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0`。
- Rollback: 按 Task 5 → Task 1 commit 逆序 revert；rollback 后第一项验证为：

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_template_registry.py::test_p0_exp_001_loads_the_approved_single_template_registration \
  backend/tests/integration/test_export_preflight.py -q
```

---

## Status

- Date: `2026-07-31`
- Status: `ready-for-execution`
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-07-31-leader-dimension-inspection-excel.md`
- Selection evidence: 用户明确要求在批准的非生产对比稿之后建立正式 spec/plan。
- Validation action: `replan`
- Writer ownership and order: parent/main thread；Task 1 → Task 5；不允许并发 writer。
- Next verification: Task 1 Step 2 的 focused RED。

## Allowed Paths

- `backend/assets/templates/sip-v1.xlsx`
- `backend/assets/templates/sip-v1.mapping.json`
- `backend/scripts/build_sip_template_v3.py`
- `backend/app/exports/sip_workbook_contract.py`
- `backend/app/exports/template_registry.py`
- `backend/app/exports/excel.py`
- `backend/app/exports/service.py`
- `backend/app/exports/validators.py`
- `backend/tests/unit/exports/test_sip_workbook_contract.py`
- `backend/tests/unit/exports/test_template_registry.py`
- `backend/tests/unit/exports/test_excel_mapping.py`
- `backend/tests/integration/test_excel_export.py`
- `backend/tests/integration/test_export_consistency.py`
- `backend/tests/integration/test_export_atomicity.py`
- `backend/tests/integration/test_export_preflight.py`
- `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- `docs/superpowers/specs/2026-07-31-leader-dimension-inspection-excel-design.md`
- `docs/superpowers/plans/2026-07-31-leader-dimension-inspection-excel.md`

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `sip-v1.xlsx` | 唯一受控 workbook bytes；保存视觉、formula、conditional formatting、print layout 和 `气泡图` |
| `sip-v1.mapping.json` | v3 sheet/header/detail/input/formula/capacity/range registration |
| `build_sip_template_v3.py` | 离线构建 v3 asset；不在 runtime 导出路径，不拥有业务语义 |
| `sip_workbook_contract.py` | 唯一 header/detail numeric-field 分类及 row-specific trusted formula Owner |
| `template_registry.py` | 唯一 template/mapping identity、schema 和 pinned hashes Owner |
| `service.py` | frozen reviewed item → dimension row/header projection、staged value validation、cross-artifact identity |
| `excel.py` | registered cells 的 plain-text/numeric 写入和 page-image embedding Executor |
| `validators.py` | workbook fixed ranges、formula、editable input、cell type 和 page-image Veto Gate |
| export tests | registration、row values、formula、recalc、atomicity 和 rollback regression proof |
| `MAIN_CONTRACT_MATRIX.md` | accepted `EXP-001/002/003/007` durable contract |

---

### Task 1: Lock The V3 Registration And Row Contract With RED Tests

**Files:**

- Create: `backend/tests/unit/exports/test_sip_workbook_contract.py`
- Modify: `backend/tests/unit/exports/test_template_registry.py`
- Modify: `backend/tests/unit/exports/test_excel_mapping.py`
- Modify: `backend/tests/integration/test_export_consistency.py`

**Interfaces:**

- Consumes: existing `load_template_registration()` and `ExportService._excel_rows()`.
- Produces: exact v3 registration expectations and representative row-projection contract for
  Tasks 2–3.

- [ ] **Step 1: Lock the shared value/formula Owner with an exact RED**

Create a focused unit test that imports `NUMERIC_METADATA_FIELDS`,
`NUMERIC_DETAIL_FIELDS`, `TEXT_METADATA_FIELDS`, `TEXT_DETAIL_FIELDS` and
`expected_result_formula` from `sip_workbook_contract.py`. Assert the exact field partitions are
disjoint and complete, and:

```python
assert expected_result_formula(6) == (
    '=IF(H6="","",IF(OR(F6="",G6=""),"",'
    'IF(AND(ISNUMBER(H6),H6<=F6,H6>=G6),"OK","NG")))'
)
with pytest.raises(ValueError):
    expected_result_formula(0)
```

- [ ] **Step 2: Replace the registration expectations with exact v3 literals**

Update the approved-registration test to require:

```python
assert registration.template_id == "sip-v1"
assert registration.template_version == "3"
assert registration.mapping_version == "3"
assert registration.sheet == "尺寸质量检测表"
assert registration.capacity == 512
assert registration.first_row == 6
assert registration.last_row == 517
assert registration.measurement_column == "H"
assert registration.result_column == "I"
assert registration.image_sheet == "气泡图"
assert registration.image_anchor == "B2"
```

Update `_complete_mapping()` to use these exact key sets:

```python
metadata_cells = {
    "source_filename": "B2",
    "inspection_date": "F2",
    "toleranced_count": "I2",
    "page_count": "B3",
    "detail_count": "F3",
    "unit": "I3",
    "general_tolerance_note": "A4",
}
detail_columns = {
    "number": "A",
    "source_page": "B",
    "type_label": "C",
    "basic_size": "D",
    "tolerance": "E",
    "upper_limit": "F",
    "lower_limit": "G",
}
```

Add negative cases proving:

```python
mapping.pop("measurement_column")  # InvalidTemplateRegistration
mapping["result_column"] = "H"     # overlaps measurement_column
mapping["detail_columns"]["upper_limit"] = "I"  # overlaps result formula column
```

- [ ] **Step 3: Run the registration/formula RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/unit/exports/test_template_registry.py \
  backend/tests/unit/exports/test_excel_mapping.py -q
```

Expected: FAIL because production registration is still v2 and
`sip_workbook_contract.py` does not exist and `TemplateRegistration` has no
measurement/result columns.

- [ ] **Step 4: Add exact row-projection RED cases**

In `test_export_consistency.py`, construct reviewed items with the existing confirmed SIP
readiness fields plus structured dimension fields:

```python
linear = {
    "item_id": "linear-500",
    "item_type": "linear_dimension",
    "normalized_text": "500 ±0.2",
    "nominal": "500",
    "upper_tolerance": "0.2",
    "lower_tolerance": "-0.2",
    "source_page": 1,
    "active": True,
    "balloon_required": True,
    "sip_detail_fields_confirmed": True,
    "inspection_item": "线性尺寸：500 ±0.2",
    "inspection_standard": "图纸要求",
    "inspection_method": "游标卡尺",
    "key_dimension": "否",
    "inspection_role": "IPQC",
}
rows = ExportService._excel_rows(
    [linear],
    [{"inspection_item_id": "linear-500", "formal_number": 7}],
)
assert rows == [{
    "number": 7,
    "source_page": 1,
    "type_label": "线性",
    "basic_size": "500",
    "tolerance": "±0.2",
    "upper_limit": Decimal("500.2"),
    "lower_limit": Decimal("499.8"),
    "scope": None,
    "balloon_required": True,
}]
```

Add table-driven cases for:

```python
("diameter_dimension", {"nominal": "20"}, "直径", "Φ20")
("radius", {"radius_value": "35"}, "半径", "R35")
(None, {"coarse_type": "roughness", "raw_text": "Ra3.2"}, "粗糙度", "Ra3.2")
("angle", {"angle_value": "45"}, "角度", "45°")
("thread", {"thread_spec": "M10×1.5"}, "螺纹", "M10×1.5")
("general_requirement", {"normalized_text": "去毛刺"}, "技术要求", "去毛刺")
("composite", {"normalized_text": "Φ10 深20"}, "复合", "Φ10 深20")
```

Add failure/blank cases:

```python
assert no_tolerance_row["tolerance"] == ""
assert no_tolerance_row["upper_limit"] == ""
assert no_tolerance_row["lower_limit"] == ""
with pytest.raises(ValueError, match="one-sided structured tolerance"):
    ExportService._excel_rows([upper_only_item], balloons)
```

- [ ] **Step 5: Run the projection RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_export_consistency.py -q
```

Expected: FAIL because `_excel_rows()` still produces the old seven SIP fields.

- [ ] **Step 6: Commit the RED contract**

```bash
git add \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/unit/exports/test_template_registry.py \
  backend/tests/unit/exports/test_excel_mapping.py \
  backend/tests/integration/test_export_consistency.py
git commit -m "test(exports): define dimension inspection workbook v3"
```

---

### Task 2: Build And Register The Single V3 Workbook

**Files:**

- Create: `backend/scripts/build_sip_template_v3.py`
- Create: `backend/app/exports/sip_workbook_contract.py`
- Modify: `backend/assets/templates/sip-v1.xlsx`
- Modify: `backend/assets/templates/sip-v1.mapping.json`
- Modify: `backend/app/exports/template_registry.py`
- Modify: `backend/tests/unit/exports/test_template_registry.py`
- Modify: `backend/tests/unit/exports/test_excel_mapping.py`
- Modify: `backend/tests/integration/test_export_preflight.py`

**Interfaces:**

- Consumes: exact v3 registration literals from Task 1 and the visual reference in
  `.local/design-qa/leader-dimension-inspection-template/`.
- Produces:
  `TemplateRegistration(..., measurement_column="H", result_column="I")`,
  v3 template/mapping bytes and exact pinned hashes.

- [ ] **Step 1: Establish the acyclic workbook value/formula contract**

Create `sip_workbook_contract.py` with no imports from renderer, validator, service or registry:

```python
NUMERIC_METADATA_FIELDS = frozenset(
    {"toleranced_count", "page_count", "detail_count"}
)
NUMERIC_DETAIL_FIELDS = frozenset(
    {"number", "source_page", "upper_limit", "lower_limit"}
)
TEXT_METADATA_FIELDS = frozenset(
    {"source_filename", "inspection_date", "unit", "general_tolerance_note"}
)
TEXT_DETAIL_FIELDS = frozenset(
    {"type_label", "basic_size", "tolerance"}
)


def expected_result_formula(row: int) -> str:
    if isinstance(row, bool) or not isinstance(row, int) or row < 1:
        raise ValueError("result formula row must be a positive integer")
    return (
        f'=IF(H{row}="","",IF(OR(F{row}="",G{row}=""),"",'
        f'IF(AND(ISNUMBER(H{row}),H{row}<=F{row},H{row}>=G{row}),"OK","NG")))'
    )
```

`template_registry.py` must import these four field sets and require the mapping keys to equal
their unions. `build_sip_template_v3.py`, `excel.py`, `validators.py` and
`ExportService._validate_excel()` must import the same symbols; none may redeclare numeric-field
sets or the formula literal.

- [ ] **Step 2: Implement the offline workbook builder**

Create a builder with no network dependency. It may import only the pure workbook contract from
application code:

```python
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from app.exports.sip_workbook_contract import expected_result_formula
from openpyxl import load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side

FIRST_ROW = 6
LAST_ROW = 517


def _normalize_archive(path: Path) -> None:
    members: dict[str, bytes] = {}
    with ZipFile(path, "r") as source:
        for name in source.namelist():
            members[name] = source.read(name)
    normalized = path.with_suffix(".normalized.xlsx")
    with ZipFile(normalized, "w", compression=ZIP_DEFLATED) as target:
        for name in sorted(members):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            target.writestr(info, members[name])
    normalized.replace(path)


def build_template(source_path: Path, target: Path) -> None:
    workbook = load_workbook(source_path, data_only=False)
    old_sheet = (
        workbook["SIP检验记录"]
        if "SIP检验记录" in workbook.sheetnames
        else workbook["尺寸质量检测表"]
    )
    workbook.remove(old_sheet)
    sheet = workbook.create_sheet("尺寸质量检测表", 0)
    image_sheet = workbook["气泡图"]
    assert image_sheet.title == "气泡图"
    workbook.properties.created = datetime(2026, 7, 31, tzinfo=timezone.utc)
    workbook.properties.modified = datetime(2026, 7, 31, tzinfo=timezone.utc)
    for row in range(FIRST_ROW, LAST_ROW + 1):
        for column in "ABCDEFGH":
            sheet[f"{column}{row}"].protection = Protection(locked=False)
        sheet[f"H{row}"].value = None
        sheet[f"I{row}"] = expected_result_formula(row)
        sheet[f"I{row}"].protection = Protection(locked=True)
    workbook.save(target)
    workbook.close()
    _normalize_archive(target)
```

The completed builder must additionally set these exact values:

- title `A1:I1 = 机械图纸尺寸质量检测表`；
- metadata labels/merges from the design spec；
- red note `A4:I4`；
- blue headers `A5:I5`；
- type conditional formatting colors from the design spec；
- `OK` green / `NG` red conditional formatting；
- A4 landscape, print area `A1:I522`, print titles `1:5`；
- fixed footer at row `518` and signoff body `519:522`；
- `气泡图 / BALLOONED DRAWING` title and existing `B2` image anchor layout；
- all 512 H cells blank/unlocked and all 512 I formulas exact.
- all 512 A:H detail cells unlocked；
- the existing `气泡图` worksheet structure remains present because the builder starts from the
  currently registered workbook and replaces only the first worksheet。

- [ ] **Step 3: Generate the workbook and mapping deterministically using Micromamba**

Run:

```bash
build_dir="$(mktemp -d /tmp/qi-sip-template-v3.XXXXXX)"
second_build_dir="$(mktemp -d /tmp/qi-sip-template-v3-repeat.XXXXXX)"
cd backend
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python \
  scripts/build_sip_template_v3.py \
  --source assets/templates/sip-v1.xlsx \
  --target "$build_dir/sip-v1.xlsx" \
  --mapping "$build_dir/sip-v1.mapping.json"
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python \
  scripts/build_sip_template_v3.py \
  --source assets/templates/sip-v1.xlsx \
  --target "$second_build_dir/sip-v1.xlsx" \
  --mapping "$second_build_dir/sip-v1.mapping.json"
sha256sum "$build_dir/sip-v1.xlsx" "$second_build_dir/sip-v1.xlsx"
cmp "$build_dir/sip-v1.xlsx" "$second_build_dir/sip-v1.xlsx"
cmp "$build_dir/sip-v1.mapping.json" "$second_build_dir/sip-v1.mapping.json"
cp "$build_dir/sip-v1.xlsx" assets/templates/sip-v1.xlsx
cp "$build_dir/sip-v1.mapping.json" assets/templates/sip-v1.mapping.json
cd ..
```

The script's `argparse` entrypoint must pass the three exact paths to `build_template()` and the
mapping writer from Step 4. Expected: exit `0`; generated workbook has exactly two sheets and
reopens with openpyxl.

Expected: both `cmp` commands exit `0`; the committed template/mapping bytes are reproducible.

- [ ] **Step 4: Replace the mapping with v3 registration**

Generate the mapping with the actual workbook digest in the same builder:

```python
import hashlib
import json

template_bytes = target.read_bytes()
mapping = {
    "template_id": "sip-v1",
    "template_version": "3",
    "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
    "mapping_version": "3",
    "sheet": "尺寸质量检测表",
    "capacity": {"first_row": 6, "last_row": 517},
    "metadata_cells": {
        "source_filename": "B2",
        "inspection_date": "F2",
        "toleranced_count": "I2",
        "page_count": "B3",
        "detail_count": "F3",
        "unit": "I3",
        "general_tolerance_note": "A4",
    },
    "detail_columns": {
        "number": "A",
        "source_page": "B",
        "type_label": "C",
        "basic_size": "D",
        "tolerance": "E",
        "upper_limit": "F",
        "lower_limit": "G",
    },
    "measurement_column": "H",
    "result_column": "I",
    "image_sheet": "气泡图",
    "image_anchor": "B2",
    "protected_ranges": [
        "A1:I1", "A2", "E2", "H2", "A3", "E3", "H3",
        "A5:I5", "I6:I517", "A518:I518",
    ],
    "signoff_ranges": ["A519:B522", "C519:D522", "E519:F522", "G519:I522"],
}
mapping_path.write_text(
    json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
```

After generation, independently print the digest from `backend/`:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python -c \
  "from pathlib import Path; from app.exports.template_registry import file_sha256; print(file_sha256(Path('assets/templates/sip-v1.xlsx')))"
```

The printed digest must equal `template_sha256` in the generated mapping.

- [ ] **Step 5: Extend registration schema and pin both hashes**

Update `TemplateRegistration`:

```python
@dataclass(frozen=True)
class TemplateRegistration:
    template_id: str
    template_version: str
    template_sha256: str
    mapping_version: str
    sheet: str
    first_row: int
    last_row: int
    metadata_cells: dict[str, str]
    detail_columns: dict[str, str]
    measurement_column: str
    result_column: str
    image_sheet: str
    image_anchor: str
    protected_ranges: tuple[str, ...]
    signoff_ranges: tuple[str, ...]
```

Set:

```python
APPROVED_TEMPLATE_VERSION = "3"
APPROVED_MAPPING_VERSION = "3"
```

Compute the final mapping digest after its `template_sha256` is concrete:

```bash
sha256sum backend/assets/templates/sip-v1.xlsx \
  backend/assets/templates/sip-v1.mapping.json
```

Copy those exact lowercase digests into `APPROVED_TEMPLATE_SHA256` and
`APPROVED_MAPPING_SHA256`. Validate measurement/result columns are single Excel columns,
distinct from each other and disjoint from `detail_columns.values()`. Validate metadata/detail
key sets against the shared workbook contract imported from `sip_workbook_contract.py`.

- [ ] **Step 6: Run v3 registration GREEN and preflight**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/unit/exports/test_template_registry.py \
  backend/tests/unit/exports/test_excel_mapping.py \
  backend/tests/integration/test_export_preflight.py -q
```

Expected: PASS; missing asset, hash drift, mapping drift, missing sheet and overlapping column
cases continue to fail closed. The mapping/template tests must open the registered workbook and
assert every row `6:517` has blank unlocked H and
`I<row> == expected_result_formula(row)`.

- [ ] **Step 7: Commit the v3 asset and registration**

```bash
git add \
  backend/scripts/build_sip_template_v3.py \
  backend/app/exports/sip_workbook_contract.py \
  backend/assets/templates/sip-v1.xlsx \
  backend/assets/templates/sip-v1.mapping.json \
  backend/app/exports/template_registry.py \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/unit/exports/test_template_registry.py \
  backend/tests/unit/exports/test_excel_mapping.py \
  backend/tests/integration/test_export_preflight.py
git commit -m "feat(exports): register dimension inspection workbook v3"
```

---

### Task 3: Replace The Formal Excel Row And Header Projection

**Files:**

- Modify: `backend/app/exports/service.py`
- Modify: `backend/tests/integration/test_export_consistency.py`
- Modify: `backend/tests/integration/test_export_atomicity.py`

**Interfaces:**

- Consumes: frozen `ReviewedResult.items`, active formal balloons, source filename,
  `ExportJob.created_at` and validated page count.
- Produces:
  `list[dict[str, object]]` with exactly the seven server-written detail fields plus
  `scope/balloon_required`, and a seven-field header mapping.

- [ ] **Step 1: Add Decimal-safe display helpers**

Add private helpers in `service.py`:

```python
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

_EXCEL_DETAIL_FIELDS = {
    "number",
    "source_page",
    "type_label",
    "basic_size",
    "tolerance",
    "upper_limit",
    "lower_limit",
}


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return "0" if rendered in {"-0", ""} else rendered
```

Use fixed type labels from the design spec. Determine roughness from
`coarse_type == "roughness"` before the generic composite fallback.

- [ ] **Step 2: Implement the exact tolerance contract**

Add:

```python
def _tolerance_values(item: dict[str, Any]) -> tuple[str, Decimal | str, Decimal | str]:
    upper = _decimal(item.get("upper_tolerance"))
    lower = _decimal(item.get("lower_tolerance"))
    if upper is None and lower is None:
        return "", "", ""
    if upper is None or lower is None:
        raise ValueError("reviewed item has one-sided structured tolerance")
    base = _numeric_base(item)
    if base is None:
        return _tolerance_text(upper, lower), "", ""
    return _tolerance_text(upper, lower), base + upper, base + lower
```

`_numeric_base()` may use only:

- `nominal` for linear/diameter；
- `radius_value` for radius；
- `angle_value` for angle。

It must not parse `normalized_text` or apply general tolerance standards.

- [ ] **Step 3: Replace `_excel_rows()` in place**

Each active item produces:

```python
row = {
    "number": balloon_numbers.get(item_id, ""),
    "source_page": item["source_page"],
    "type_label": _type_label(item),
    "basic_size": _basic_size(item),
    "tolerance": tolerance,
    "upper_limit": upper_limit,
    "lower_limit": lower_limit,
    "scope": item.get("scope"),
    "balloon_required": required,
}
```

Preserve these gates before projection:

- `sip_detail_fields_confirmed is True`；
- all existing `SIP_DETAIL_FIELDS` remain complete；
- balloon-required item has exactly one formal number；
- source page is positive integer。

Update `assert_export_counts()` to compare nonblank `row["number"]` against formal PDF numbers.

- [ ] **Step 4: Project the general-tolerance note from frozen reviewed items**

Add a pure export helper that reads only immutable `ReviewedResult.items`:

```python
def _general_tolerance_note(
    reviewed_items: list[dict[str, Any]],
) -> str:
    standards = {"GB/T 1804": set(), "GB/T 1184": set()}
    allowed_classes = {
        "GB/T 1804": {"f", "m", "c", "v"},
        "GB/T 1184": {"h", "k", "l"},
    }
    for item in reviewed_items:
        refs = item.get("technical_requirement_refs")
        if item.get("active", True) is not True or not isinstance(refs, list) or not refs:
            continue
        value = item.get("inspection_standard")
        if not isinstance(value, str):
            continue
        for code in standards:
            prefix = f"{code}-"
            tolerance_class = value[len(prefix):].lower() if value.startswith(prefix) else ""
            if tolerance_class in allowed_classes[code]:
                standards[code].add(f"{code}-{tolerance_class}")
    if any(len(values) > 1 for values in standards.values()):
        raise ValueError("frozen reviewed items contain conflicting general tolerance standards")
    dimensional = next(iter(standards["GB/T 1804"]), None)
    geometric = next(iter(standards["GB/T 1184"]), None)
    parts = []
    if dimensional is not None:
        parts.append(f"未注线性尺寸公差按 {dimensional} 级执行")
    if geometric is not None:
        parts.append(f"未注形位公差按 {geometric} 级执行")
    return "【未注公差标准】" + ("；".join(parts) if parts else "未确认")
```

Do not read `raw_text/normalized_text`, do not call the technical-requirement classifier, and do
not modify `ReviewService.confirm()` or `ReviewedResult.sip_metadata`. Tests must prove one
1804 value, combined 1804/1184 values, absent controlled values, ignored arbitrary standards, and
conflicting classes.

- [ ] **Step 5: Validate legacy review metadata and build the new header after PDF validation**

Remove `service.py`'s import of the workbook v2 `excel.REQUIRED_METADATA_FIELDS`. Import
`SIP_METADATA_FIELDS` from `app.review.schemas`, convert it to a local set, and keep
`_sip_metadata()` five-field exact validation behavior unchanged:

```python
required_review_metadata = set(SIP_METADATA_FIELDS)
missing = required_review_metadata - set(metadata)
extra = set(metadata) - required_review_metadata
```

Call it before export claim. Do not pass those five legacy values to the new visible sheet and do
not extend their stored/API-visible shape. Add a regression asserting v3 still accepts exactly the
same frozen five-field payload and rejects missing/extra keys; this is the rollback data-compatibility
proof.

After `source_page_count` and `export.created_at` are available, produce:

```python
workbook_metadata = {
    "source_filename": source.filename,
    "inspection_date": export.created_at.astimezone(
        ZoneInfo("Asia/Hong_Kong")
    ).strftime("%Y-%m-%d %H:%M"),
    "toleranced_count": sum(
        row["upper_limit"] != "" and row["lower_limit"] != ""
        for row in excel_rows
    ),
    "page_count": source_page_count,
    "detail_count": len(excel_rows),
    "unit": "mm / 按项目",
    "general_tolerance_note": _general_tolerance_note(reviewed.items),
}
```

Pass this dict to renderer and staged Excel validation. Keep `RENDERER_VERSION` unchanged because
formal ballooned PDF rendering did not change; v3 template/mapping already changes export identity.

- [ ] **Step 6: Run projection and atomicity GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py -q
```

Expected: PASS; row/balloon/reviewed-result mismatches and tolerance conflicts fail before publish.

- [ ] **Step 7: Commit the projection replacement**

```bash
git add \
  backend/app/exports/service.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py
git commit -m "feat(exports): project reviewed dimensions into SIP workbook"
```

---

### Task 4: Render And Validate Trusted Formula Cells

**Files:**

- Modify: `backend/app/exports/excel.py`
- Modify: `backend/app/exports/service.py`
- Modify: `backend/app/exports/validators.py`
- Modify: `backend/tests/integration/test_excel_export.py`
- Modify: `backend/tests/integration/test_export_atomicity.py`

**Interfaces:**

- Consumes: v3 `TemplateRegistration`, header dict, seven-field row dicts and formal PDF page images.
- Produces: reopenable workbook bytes with A:G server data, blank editable H, trusted I formula,
  and unchanged page images/fixed ranges.

- [ ] **Step 1: Write renderer/validator RED cases**

Update `_reviewed_items()` and `_render()` fixtures for v3 rows. Add assertions:

```python
assert sheet["A6"].value == 1
assert sheet["B6"].value == 1
assert sheet["C6"].value == "线性"
assert sheet["D6"].value == "500"
assert sheet["E6"].value == "±0.2"
assert sheet["F6"].value == 500.2
assert sheet["G6"].value == 499.8
assert sheet["H6"].value is None
assert sheet["H6"].protection.locked is False
assert sheet["I6"].value == (
    '=IF(H6="","",IF(OR(F6="",G6=""),"",'
    'IF(AND(ISNUMBER(H6),H6<=F6,H6>=G6),"OK","NG")))'
)
assert sheet["A1"].value == "机械图纸尺寸质量检测表"
assert sheet["A4"].font.color.rgb[-6:] == "D9272E"
assert sheet["A5"].fill.fgColor.rgb[-6:] == "4472C4"
assert str(sheet.print_area) == "'尺寸质量检测表'!$A$1:$I$522"
assert sheet.print_title_rows == "$1:$5"
assert sheet.page_setup.orientation == "landscape"
```

Inspect conditional formatting without assuming openpyxl evaluates it:

```python
conditional_fills: dict[str, str] = {}
for conditional in sheet.conditional_formatting:
    for rule in sheet.conditional_formatting[conditional]:
        if rule.formula and rule.dxf is not None and rule.dxf.fill is not None:
            conditional_fills[rule.formula[0]] = rule.dxf.fill.fgColor.rgb[-6:]
assert conditional_fills['$C6="线性"'] == "E5334E"
assert conditional_fills['$C6="直径"'] == "178BFF"
assert conditional_fills['$C6="半径"'] == "22B14C"
assert conditional_fills['$C6="粗糙度"'] == "C23ACF"
```

Add a formula-injection case:

```python
row["basic_size"] = "=HYPERLINK(\"https://invalid\")"
content = render(...)
assert load_workbook(BytesIO(content))["尺寸质量检测表"]["D6"].data_type == "s"
```

Add a failure case that mutates `I6` in a copied template and expects
`validate_sip_workbook()` to raise `registered fixed or sign-off range changed` or the more
specific `trusted result formula changed`.

- [ ] **Step 2: Run renderer RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_excel_export.py -q
```

Expected: FAIL because the old renderer writes every detail cell as string and has no H/I contract.

- [ ] **Step 3: Add explicit numeric allowlist writing**

In `excel.py`, import `NUMERIC_DETAIL_FIELDS` and `NUMERIC_METADATA_FIELDS` from
`sip_workbook_contract.py`:

```python
def set_registered_value(cell: Cell, field: str, value: object) -> None:
    if value in (None, ""):
        cell.value = None
        return
    if field in NUMERIC_DETAIL_FIELDS:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError(f"{field} must be numeric")
        cell.value = int(value) if Decimal(str(value)) % 1 == 0 else float(value)
        cell.data_type = "n"
        return
    set_untrusted_text(cell, value)


def set_metadata_value(cell: Cell, field: str, value: object) -> None:
    if field in NUMERIC_METADATA_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")
        cell.value = value
        cell.data_type = "n"
        return
    set_untrusted_text(cell, value)
```

Never accept a string starting with `=` as numeric or formula.

- [ ] **Step 4: Preserve measurement/result columns instead of writing them**

Before writing rows, snapshot all registered protected/signoff ranges, including `I6:I517`.
For each exported row:

- write only `detail_columns` A:G；
- require `H<row>` is blank and unlocked；
- require `I<row>` equals the literal row-specific template formula；
- do not write measurement or result cells。

The renderer must continue embedding each `page_images` entry on `气泡图` at the registered
anchor/order.

- [ ] **Step 5: Extend validator cell-type and formula checks**

Update `validate_sip_workbook()`. Check A:G cell types only for `detail_count` written rows, then
check H/I for every registered capacity row `first_row:last_row`:

```python
for field, column in registration.detail_columns.items():
    cell = sheet[f"{column}{row}"]
    if field in NUMERIC_DETAIL_FIELDS:
        if cell.value not in (None, "") and cell.data_type != "n":
            raise ValueError("generated numeric detail cell is not numeric")
    elif cell.value is not None and cell.data_type != "s":
        raise ValueError("generated text detail cell is not plain text")

for row in range(registration.first_row, registration.last_row + 1):
    measurement = sheet[f"{registration.measurement_column}{row}"]
    if measurement.value not in (None, "") or measurement.protection.locked:
        raise ValueError("measurement cell is not blank and editable")

    result = sheet[f"{registration.result_column}{row}"]
    if result.value != expected_result_formula(row):
        raise ValueError("trusted result formula changed")
```

Import `NUMERIC_DETAIL_FIELDS` and `expected_result_formula` from
`sip_workbook_contract.py`; do not import `excel.py` from `validators.py`. Keep the existing
page-image parity, fixed-range snapshot and resave/reopen checks.

- [ ] **Step 6: Replace staged validation with the same numeric/text contract**

Update `ExportService._validate_excel()` to import the shared metadata/detail field sets and
`expected_result_formula`. Compare numeric registered fields by first requiring
`cell.data_type == "n"` and then
`Decimal(str(actual)) == Decimal(str(expected))` (reject bool and string); compare text fields as
exact strings/blank `None`; require H blank/unlocked; require exact I formula. Remove all v2
`str(expected)` assumptions and old `balloon_number` special case.

Add an integration case that calls the complete `ExportService.create()` flow with numeric header
counts, numeric number/page/upper/lower cells and one global-requirement blank number. Assert the
three artifacts publish atomically and the staged workbook contains the expected numeric cells.
Mutating one numeric cell to text or one formula must make `create()` fail before any artifact is
visible.

- [ ] **Step 7: Run renderer/validator/staged-validation GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_atomicity.py -q
```

Expected: PASS with the new visible fields, formula, input cells, type colors, fixed ranges,
page images, formula-injection case and full staged publish using numeric cells.

- [ ] **Step 8: Commit the trusted formula renderer**

```bash
git add \
  backend/app/exports/excel.py \
  backend/app/exports/service.py \
  backend/app/exports/validators.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_atomicity.py
git commit -m "feat(exports): render trusted inspection result formulas"
```

---

### Task 5: Close Contract, LibreOffice, Atomicity And Independent Review

**Files:**

- Modify: `backend/tests/integration/test_excel_export.py`
- Modify: `backend/tests/integration/test_export_consistency.py`
- Modify: `backend/tests/integration/test_export_atomicity.py`
- Modify: `backend/tests/integration/test_export_preflight.py`
- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Modify: `docs/superpowers/specs/2026-07-31-leader-dimension-inspection-excel-design.md`
- Modify: `docs/superpowers/plans/2026-07-31-leader-dimension-inspection-excel.md`

**Interfaces:**

- Consumes: completed v3 asset, renderer, row projection and validators.
- Produces: executable acceptance evidence, durable `EXP` contract update and independent verdict.

- [ ] **Step 1: Add the representative LibreOffice recalculation test**

In `test_excel_export.py`, add a test that requires the local `libreoffice` binary:

```python
def test_dimension_result_formula_recalculates_with_libreoffice(
    tmp_path: Path,
) -> None:
    libreoffice = shutil.which("libreoffice")
    assert libreoffice is not None, "LibreOffice is required for formal Excel verification"
    content, registration, _ = _render(tmp_path)
    source = tmp_path / "leader-dimension-inspection.xlsx"
    source.write_bytes(content)
    profile = tmp_path / "lo-profile"
    output = tmp_path / "recalculated"
    profile.mkdir()
    output.mkdir()

    input_book = load_workbook(source, data_only=False)
    input_book[registration.sheet]["H6"] = 500.3
    input_book.save(source)
    input_book.close()

    subprocess.run(
        [
            libreoffice,
            f"-env:UserInstallation=file://{profile}",
            "--headless",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(output),
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    recalculated_path = output / source.name
    recalculated = load_workbook(recalculated_path, data_only=True)
    values = recalculated[registration.sheet]
    try:
        assert values["F6"].value == 500.2
        assert values["G6"].value == 499.8
        assert values["I6"].value == "NG"
        assert values["I7"].value is None  # no measurement
        assert values["F8"].value is None
        assert values["G8"].value is None
        assert values["I8"].value is None  # no explicit tolerance
    finally:
        recalculated.close()
```

Use a unique `UserInstallation` directory so an existing desktop LibreOffice session cannot
capture the command. Do not modify production code to satisfy the smoke.

- [ ] **Step 2: Run the complete focused export suite**

Run:

```bash
command -v libreoffice
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/unit/exports/test_template_registry.py \
  backend/tests/unit/exports/test_excel_mapping.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py -q
```

Expected: command prints a real binary path; pytest has zero failures and the LibreOffice test is
not skipped.

- [ ] **Step 3: Run the nearest broader backend verification**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py \
  backend/tests/integration/test_schema.py -q
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 ruff check \
  backend/app/exports \
  backend/scripts/build_sip_template_v3.py \
  backend/app/exports/sip_workbook_contract.py \
  backend/tests/unit/exports \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py
```

Expected: zero test failures and zero Ruff errors.

- [ ] **Step 4: Update the durable contract matrix**

Amend only these rows:

- `EXP-001`: `sip-v1` v3 registration now includes measurement/result columns and trusted formula
  ranges；
- `EXP-002`: fixed visible row is number/page/type/basic size/tolerance/upper/lower, with blank
  global-requirement number；
- `EXP-003`: user text remains plain string; only registered result formulas are executable；
- `EXP-007`: add blank editable measurement, exact formula, LibreOffice representative recalc and
  no-tolerance blank-result checks。

Do not change `EXP-004/005/006/008/009`.

- [ ] **Step 5: Perform an independent read-only review**

Dispatch the local `reviewer` profile with:

- exact diff scope from all five tasks；
- authority `read-only`；
- no nested delegation；
- required verdict `accept / accept with concerns / reject`；
- explicit checks for second Owner, v2 fallback, formula injection, missing active rows,
  `气泡图`, atomic publish, rollback and test realism。

The parent must verify every blocking claim against code/tests before acting.

- [ ] **Step 6: Run final diff and scope verification**

Run:

```bash
git diff --check
git status --short
git diff -- \
  backend/assets/templates/sip-v1.xlsx \
  backend/assets/templates/sip-v1.mapping.json \
  backend/scripts/build_sip_template_v3.py \
  backend/app/exports/template_registry.py \
  backend/app/exports/sip_workbook_contract.py \
  backend/app/exports/excel.py \
  backend/app/exports/service.py \
  backend/app/exports/validators.py \
  backend/tests/unit/exports/test_template_registry.py \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/unit/exports/test_excel_mapping.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py \
  docs/contracts/MAIN_CONTRACT_MATRIX.md \
  docs/superpowers/specs/2026-07-31-leader-dimension-inspection-excel-design.md \
  docs/superpowers/plans/2026-07-31-leader-dimension-inspection-excel.md
```

Confirm no `.local`, `.pyc`, Harness run, recognition, frontend, database, OpenAPI or unrelated file
is staged.

- [ ] **Step 7: Commit the closure**

```bash
git add \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py \
  docs/contracts/MAIN_CONTRACT_MATRIX.md \
  docs/superpowers/specs/2026-07-31-leader-dimension-inspection-excel-design.md \
  docs/superpowers/plans/2026-07-31-leader-dimension-inspection-excel.md
git commit -m "docs(exports): close dimension inspection workbook contract"
```

- [ ] **Step 8: Record completion only after fresh evidence**

Set this plan status to `completed` only when:

- focused and broader suites passed in the same implementation run；
- LibreOffice representative recalculation passed without skip；
- template/mapping final hashes match registry and manifest；
- independent reviewer verdict is `accept` or all blocking concerns were fixed and reverified；
- final staged file list contains only allowed paths；
- production implementation commits exist。

Do not create `.agent/EXECUTION_STATUS.md` in this checkout; it is currently absent.
