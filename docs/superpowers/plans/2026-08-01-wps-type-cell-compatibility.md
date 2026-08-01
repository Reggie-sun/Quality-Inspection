# WPS Type Cell Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让正式尺寸质量检测表在 WPS 中可靠显示已识别类型和类型颜色，同时保持历史 artifact immutable。

**Architecture:** 把 type label/color 表收敛到 `sip_workbook_contract.py`，template builder 与 runtime Excel renderer 共同消费；renderer 为已填充 C cell 写静态 base style，同时保留 conditional formatting。升级单一 formal renderer identity，让 existing `3/3` reviewed result 获得新的 logical export key。

**Tech Stack:** Python 3.11、openpyxl、pytest、LibreOffice headless、Micromamba `qi-p0`

## Global Constraints

- Selected lane: `Heavy`。
- Current plan: 本文件是 WPS 类型列兼容修复的唯一 current plan；parent design 为
  `docs/superpowers/specs/2026-08-01-wps-type-cell-compatibility-design.md`。
- Selection evidence: 用户明确选择“正式兼容修复”。
- Validation action: `replan`。
- Problem boundary: `rendered type_label -> visible static cell style -> new immutable export identity`。
- Single Owner: existing label projection 为 `ExportService._type_label()`；color palette 为
  `sip_workbook_contract.py`；cell style execution 为 `excel.py`；export rematerialization
  identity 为 existing `ExportService`/manifest seam。
- Old path action: retire “已填充类型 cell 只依赖 conditional differential style 可见”的
  output；保留 conditional formatting 作为用户编辑后的增强行为。
- Unchanged contracts: template/mapping `3/3`、asset bytes/hash、recognition、review、schema、
  九列 mapping、formula、measurement、PDF 和 atomic publish 均不变。
- Artifact history: 不修改、删除或覆盖旧 export；新 renderer identity 只创建新 immutable
  result。
- Writer ownership: 父 agent 是唯一 writer；现有子任务均已结束。
- Allowed paths:
  - `backend/app/exports/sip_workbook_contract.py`
  - `backend/app/exports/excel.py`
  - `backend/app/exports/service.py`
  - `backend/scripts/build_sip_template_v3.py`
  - `backend/tests/unit/exports/test_sip_workbook_contract.py`
  - `backend/tests/integration/test_excel_export.py`
  - `backend/tests/integration/test_export_atomicity.py`
  - `.agent/bug-memory.md`
  - 本 spec/plan
- Git: 只 stage 上述实际修改文件，不 stage 既有 frontend、`.pyc`、Harness runs 或设计产物。
- Rollback: revert 本 amendment commit；不删除已发布 artifact。rollback 后先运行 spec 中的
  focused rollback command。

---

### Task 1: Materialize WPS-Compatible Type Styles And New Export Identity

**Files:**

- Modify: `backend/app/exports/sip_workbook_contract.py`
- Modify: `backend/app/exports/excel.py`
- Modify: `backend/app/exports/service.py`
- Modify: `backend/scripts/build_sip_template_v3.py`
- Test: `backend/tests/unit/exports/test_sip_workbook_contract.py`
- Test: `backend/tests/integration/test_excel_export.py`
- Test: `backend/tests/integration/test_export_atomicity.py`
- Modify: `.agent/bug-memory.md`

**Interfaces:**

- Consumes: existing `type_label` values and `render_sip_workbook(...)` detail loop.
- Produces: read-only `TYPE_FILL_COLORS`, static type-cell styles, and renderer identity
  `balloon-pdf/1+xlsx-type-style/1`.

- [x] **Step 1: Write workbook and rematerialization RED tests**

Add a workbook regression that renders representative rows, removes all conditional formatting
from the loaded result, and still requires:

```python
assert sheet["C6"].value == "线性"
assert sheet["C6"].fill.fill_type == "solid"
assert sheet["C6"].fill.fgColor.rgb[-6:] == "E5334E"
assert sheet["C6"].font.bold is True
assert sheet["C6"].font.color.rgb[-6:] == "FFFFFF"
assert sheet["C8"].value == "技术要求"
assert sheet["C8"].fill.fgColor.rgb[-6:] == "6B7280"
```

Add an isolated-DB regression that creates the historical literal logical key
`export:{reviewed.id}:3:3:balloon-pdf/1`, then claims the current key and requires two distinct jobs
for the same project/reviewed result.

- [x] **Step 2: Run RED and verify exact failures**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_atomicity.py -q
```

Expected: static-style assertions fail because current output relies on conditional formatting；
rematerialization assertion fails because current key仍为 historical `balloon-pdf/1`。

- [x] **Step 3: Implement the minimum shared color/style contract**

Add an immutable exact mapping to `sip_workbook_contract.py`:

```python
TYPE_FILL_COLORS = MappingProxyType({
    "线性": "E5334E",
    "直径": "178BFF",
    "半径": "22B14C",
    "粗糙度": "C23ACF",
    "角度": "F39C3D",
    "螺纹": "009688",
    "技术要求": "6B7280",
    "复合": "B7791F",
})
```

Replace the builder-local color dict with this Owner。In `excel.py`, after writing `type_label`,
apply `PatternFill("solid", fgColor=TYPE_FILL_COLORS[label])` and the existing white bold CJK font
directly to that cell；do not change H/I handling or template asset bytes。

- [x] **Step 4: Upgrade only the formal renderer identity**

Set:

```python
RENDERER_VERSION = "balloon-pdf/1+xlsx-type-style/1"
```

Keep template/mapping at `3/3`; the existing logical key, ExportJob and manifest propagation consume
the new value without schema or API shape changes。

- [x] **Step 5: Run GREEN and broader export gates**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/unit/exports/test_manifest.py -q

PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 ruff check \
  backend/app/exports/sip_workbook_contract.py \
  backend/app/exports/excel.py \
  backend/app/exports/service.py \
  backend/scripts/build_sip_template_v3.py \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_atomicity.py
```

Expected: all checks pass；LibreOffice test 继续证明 formula recalculation，atomicity tests 继续
证明失败不发布。

- [x] **Step 5a: Add the reviewer-found historical-export concurrency RED**

Create a historical success `ExportJob` for template/mapping `3/3` and renderer
`balloon-pdf/1`，put the current logical job into `processing` without creating a current
`ExportJob`，then assert a contender receives `ExportInProgress` rather than that historical
success result。Run the exact test and confirm old `_claim_execution()` returns the wrong export。

- [x] **Step 5b: Filter fallback exports by complete current identity**

In both `_existing_export()` failed lookup and `_claim_execution()` processing lookup，require
`APPROVED_TEMPLATE_VERSION`、`APPROVED_MAPPING_VERSION` and `RENDERER_VERSION` in addition to
reviewed result/status。Rerun the concurrency RED、full atomicity file and broader export gate。

- [x] **Step 6: Verify the same live project and close the bug record**

通过当前 frontend 对同一 project 再次执行“生成正式文件”，断言 response 的
`renderer_version` 为新 identity、export ID 与历史 ID 不同；下载 actual workbook，检查 C
列值和 base style，并用 WPS 打开确认视觉。更新同一 bug-memory entry，不创建重复记录。

- [x] **Step 7: Review, commit and preserve unrelated dirt**

运行 focused independent review，检查 stable contract、artifact immutability、测试真实 failure
surface 和 allowed-path diff。然后只 stage 本 Task 文件并提交：

```bash
git add \
  backend/app/exports/sip_workbook_contract.py \
  backend/app/exports/excel.py \
  backend/app/exports/service.py \
  backend/scripts/build_sip_template_v3.py \
  backend/tests/unit/exports/test_sip_workbook_contract.py \
  backend/tests/integration/test_excel_export.py \
  backend/tests/integration/test_export_atomicity.py \
  docs/superpowers/specs/2026-08-01-wps-type-cell-compatibility-design.md \
  docs/superpowers/plans/2026-08-01-wps-type-cell-compatibility.md
git commit -m "fix(exports): materialize WPS type styles"
```

`.agent/bug-memory.md` 已含其他未提交记录时不得整文件 stage；只在能够隔离本 entry 时单独
提交，否则保留并在 handoff 报告 overlap。

## Completion

- Implementation commit: `5e5096d fix(exports): materialize WPS type styles`，已进入 `main`。
- Independent review: `accept with concerns`；唯一 concern 为 live WPS/frontend proof，现已关闭。
- Live export: `2cb55361-4768-4bec-aaaf-51c873b6521b`，template/mapping `3/3`，renderer
  `balloon-pdf/1+xlsx-type-style/1`。
- Workbook proof: C 列 label 非空且具有 solid base fill、白色粗体；conditional formatting 保留。
- WPS proof: 新文件中 `线性`、`直径`、`螺纹` 等类型和值对应颜色均可见。
- Immutability proof: 历史 export `57a46870-5c5e-4e30-8603-d72a6a3a8bb1` 仍返回 HTTP `200`。
