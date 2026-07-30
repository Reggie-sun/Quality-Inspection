# Technical Requirement Recognition And Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 自动重建工程图“技术要求”编号条目，把独立检验要求生成无气泡 SIP 项，把适用范围规则安全匹配到现有检验项，并保留可审核、可回滚的来源与规则 provenance。

**Architecture:** 新增唯一 `Technical Requirement Rule Owner`，在 candidate snapshot 内先重建技术要求区块，再对非技术要求 observations 生成既有 candidates，最后以完整 candidate set 做确定性匹配。Immutable `AutomaticResult` 和 versioned `ReviewWorkingCopy` 各用独立 JSONB 字段保存 requirements；Review 只投影建议并通过现有确认门，frontend 和 export 不重新识别或匹配。

**Tech Stack:** Python 3.11、Pydantic、SQLAlchemy、Alembic、PostgreSQL JSONB、FastAPI、pytest、TypeScript、React、Vitest、Playwright、Micromamba `qi-p0`

---

## Status

- Date: `2026-07-30`
- Status: `in_progress`
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-07-30-technical-requirement-recognition-and-matching.md`
- Design source:
  `docs/superpowers/specs/2026-07-30-technical-requirement-recognition-and-matching-design.md`
- Selection evidence: 用户批准“语义拆解匹配 + SIP 填充”、“规则 Owner + 辅助识别”
  和“不自动换算 `GB/T 1804/1184` 数值”的边界
- Validation action: `amend`
- Production authorization: 用户已选择 `A 主线程串行执行`，并授权创建独立
  worktree
- Execution branch: `feature/technical-requirement-matching`
- Execution worktree:
  `/home/reggie/vscode_folder/Quality_Inspection/.worktrees/technical-requirement-matching`
- Baseline verification:
  - backend unit/contract: `72 passed`
  - backend schema: `6 passed`
  - frontend focused: `32 passed`
- Writer ownership and order: 一个 write-capable executor 严格按 Task 1 → Task 7；
  同一 file group 不并发写
- Next verification: 先以 RED tests 复现并修复 reviewer 确认的两项行为回归，
  再补 migration downgrade evidence，重跑 focused/full verification，最后重新绑定
  本地 `reviewer` profile 完成 Task 7 independent reviewer gate

### Task 7 Reviewer Residual Amendment

- Review evidence: child rollout
  `019fb12e-f516-71a1-aefd-afcaaa74a453` 已确认实际加载
  `agent_role=reviewer`、`model=gpt-5.6-sol`、`reasoning_effort=high`，结论为
  `reject`。
- Confirmed residual 1: `Exclude / Merge / Split` 会停用原 review item，但不会
  同事务更新 `technical_requirements` relation，可能留下 inactive target 并让
  requirement 在 freeze/export 前静默丢失。
- Confirmed residual 2: 新 Rule Owner 只重建带 `技术要求` 标题的编号块，没有接管
  被删除旧 classifier 的 title-block 外 standalone executable requirement 行为。
- Review item 3 disposition: `.agent/real-pdf-inputs.env` 的真实本机路径来自用户明确
  要求的 hardcoded `.agent` 输入，不含 credential；本轮不擅自删除或改写，重新 review
  时作为 intentional local-path boundary 明示，保留其 portability/privacy 风险。
- Review concerns 4 disposition: `ReviewPanel.tsx` 和 workspace ratio commits 是同分支
  上既存用户并发改动，不属于本 amendment 的 writer ownership；不 reset、revert 或
  顺手重写。
- Allowed paths:
  - `backend/app/candidates/technical_requirements.py`
  - `backend/app/candidates/disposition.py`
  - `backend/app/processing/automatic_result.py`
  - `backend/app/review/service.py`
  - `backend/tests/e2e/test_offline_automatic_result.py`
  - `backend/tests/integration/test_review_operations.py`
  - `backend/tests/integration/test_review_freeze.py`
  - `backend/tests/integration/test_schema.py`
  - `.agent/bug-memory.md`
  - 本 plan
- Unchanged contract: 单一 Technical Requirement Rule Owner、`automatic-result/2`、
  confirmed-only reviewed result、freeze/export identity、global requirement 无气泡，
  以及不自动写入 `GB/T 1804/1184` 数值公差。
- Writer ownership and order: 主线程单 writer；先 relation RED/green，再 standalone
  replacement RED/green，再 migration downgrade evidence；completed reviewer 保持只读。
- Focused verification:
  `micromamba run -n qi-p0 pytest backend/tests/integration/test_review_operations.py backend/tests/integration/test_review_freeze.py backend/tests/e2e/test_offline_automatic_result.py backend/tests/integration/test_schema.py -q`
- First re-review evidence: child rollout
  `019fb143-5f9e-7900-9453-57d7dfea9897` confirmed
  `agent_role=reviewer`、`model=gpt-5.6-sol`、`reasoning_effort=high`，结论为
  `reject`；确认原 fix 只覆盖 `matched_candidate_ids`，遗漏 `global_scope` 的
  singular `generated_candidate_id` relation。
- Second residual rule: target replacement 同时覆盖 `matched_items` 和
  `global_scope`。global target replacement 为一个 active item 时保持
  `global_scope` 并重写 `generated_candidate_id`；target 消失或 split 成多个 target
  时不猜测 singular identity，转为 `unresolved` 并重开 source coverage confirmation。
- Additional regression evidence: 四种 retirement/replacement command 的 global relation、
  matched multi-target unaffected preservation、generic standalone fallback，以及两个
  persistence table 的 nonempty migration downgrade refusal。

## Problem Boundary

| Dimension | Decision |
| --- | --- |
| Single owner | `backend/app/candidates/technical_requirements.py` |
| Owner inputs | stable-order `TextObservation` + complete local candidate envelopes |
| Owner outputs | reconstructed entries、classification、match relations、SIP suggestions |
| Old path | `disposition.py::classify_technical_requirement()` → migrate rules then remove active call |
| Pipeline insertion | `candidate_snapshot_from_inventory()` 内 local candidates 完成后、confidence policy 前 |
| Persistence | `automatic_results.technical_requirements` + `review_working_copies.technical_requirements` |
| Candidate compatibility | 保留 `automatic-result/2`；candidate envelope 仅新增 optional refs |
| Numeric standard conversion | 禁止；`upper_tolerance/lower_tolerance` 不因 GB/T 引用被写值 |
| Preserved owners | Observation、Coverage、ConfidencePolicy、Review confirmation、Numbering、ReviewedResult、Export |
| Rollback | 先停止 writer；保留 reader；仅在两个新 column 全为空数组时允许 schema downgrade |

## Structural Mapping Evidence

`codegraph` current-source mapping：

- `RuntimeRecognition.build_candidate_snapshot()` 调用
  `candidate_snapshot_from_inventory()`。
- `candidate_snapshot_from_inventory()` 当前直接调用
  `classify_technical_requirement()`，并同时拥有 grouping、coverage entry、source signal
  与 duplicate input 的组装。
- `InventoryPipeline.run()` 在 snapshot 后执行 `check_coverage()`、
  `ConfidencePolicy.evaluate_candidates()` 和 `build_automatic_result()`。
- `build_automatic_result()` 当前只持久化 candidates、coverage 和 provider call IDs。
- `ReviewService.create_from_raw()` 经 `_current_item()` 把 raw candidates 投影到
  working-copy items。
- `InspectionWorkbench` 是 item/source selection 和唯一 `submitCommand()` frontend
  seam；`SelectedSipDetailFields` 只消费 working-copy fields。

因此 matching 只能进入 snapshot Owner，不能放到 Provider、Review、frontend 或
export。

## Execution Guardrails

- 当前 worktree 有既存 `.pyc`、本地 QA artifact 和 frontend 未提交修改。
- Task 5 开始前必须重新运行 `git status --short` 和 live-agent inventory。
- 如果 `InspectionWorkbench.tsx`、`InspectionWorkbench.test.tsx`、
  `ReviewPanel.tsx` 或 `zhCN.ts` 仍由其他 writer 修改，Task 5 必须停在
  `blocked/ownership overlap`，不得覆盖或顺手合并。
- 每个 commit 只 stage 当 task 列出的文件，禁止 `git add .`。
- 每个 RED 必须确认是预期缺口；collection error、环境失败或 unrelated failure
  不能冒充 RED。
- 不修改 confidence threshold、Provider prompt/runtime config、formal numbering、
  export template 或已 sealed plan 状态。

## File Map

### New Files

- `backend/alembic/versions/0008_technical_requirements.py`
  - 两个 JSONB column 的 upgrade、data-safe downgrade。
- `backend/app/candidates/technical_requirements.py`
  - 唯一 reconstruction、classification、matching、validation Owner。
- `backend/tests/unit/candidates/test_technical_requirements.py`
  - 纯规则与六条样例表驱动测试。
- `frontend/src/components/workbench/TechnicalRequirementPanel.tsx`
  - requirement provenance 与 match 状态的只消费 UI。
- `frontend/src/components/workbench/TechnicalRequirementPanel.test.tsx`
  - panel 交互与 command contract。
- `frontend/e2e/technical-requirement-matching.spec.ts`
  - approved real PDF 的 runtime acceptance。

### Existing Files

- `docs/contracts/MAIN_CONTRACT_MATRIX.md`
  - 最小更新既有 `CAND-001`、`ITEM-005/006`、`REV-002/003/004`、`EXP-002` rows。
- `backend/app/candidates/models.py`
  - immutable result JSONB field。
- `backend/app/review/models.py`
  - working-copy JSONB field。
- `backend/app/candidates/disposition.py`
  - 退役旧 technical requirement classifier。
- `backend/app/processing/automatic_result.py`
  - snapshot orchestration、contract validation、persistence。
- `backend/app/processing/pipeline.py`
  - 把 snapshot technical requirements 传给 result writer。
- `backend/app/review/schemas.py`
  - versioned match override command。
- `backend/app/review/service.py`
  - requirement projection、suggestion provenance、transactional override。
- `backend/app/review/router.py`
  - API projection。
- `backend/tests/contract/test_automatic_result.py`
  - immutable requirement contract。
- `backend/tests/contract/test_review_schema.py`
  - command schema。
- `backend/tests/integration/test_schema.py`
  - migration shape。
- `backend/tests/e2e/test_offline_automatic_result.py`
  - snapshot integration 与旧路径 retirement。
- `backend/tests/integration/test_review_working_copy.py`
  - bootstrap。
- `backend/tests/integration/test_review_operations.py`
  - override transaction。
- `backend/tests/integration/test_excel_export.py`
  - global row、空编号、confirmed-only。
- `frontend/src/api/types.ts`
  - requirement types 和 command。
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
  - panel 集成到现有 selection/submit seam。
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
  - integrated behavior。
- `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
  - suggestion 预填但未确认。
- `frontend/src/copy/zhCN.ts`
  - 用户可见文案。
- `frontend/src/styles/workbench.css`
  - 紧凑 panel 样式。

## Task 1: Freeze Contracts And Add Persistence Migration

**Files:**

- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Create: `backend/alembic/versions/0008_technical_requirements.py`
- Modify: `backend/app/candidates/models.py`
- Modify: `backend/app/review/models.py`
- Modify: `backend/tests/integration/test_schema.py`

- [x] **Step 1: 使用 `github-oss-fusion` 做受限 prior-art 检查**

只研究：

- engineering drawing note/requirement provenance；
- rules-engine match relation 的 fail-closed validation；
- Alembic JSONB additive migration 与 data-safe downgrade tests。

不得复制标准表、外部模型 prompt、大段实现或新增依赖。handoff 必须记录：

```text
Repositories inspected:
Ideas fused:
Ideas skipped:
License/scope check:
Local validation:
```

Task 1 prior-art record (`2026-07-30`)：

```text
Repositories inspected:
- mindee/doctr: README, doctr/io/elements.py, tests/common/test_io_exporters.py, LICENSE
- zeroSteiner/rule-engine: README.rst, engine/rule.py, engine/context.py, tests/engine.py, LICENSE
- sqlalchemy/alembic: docs/build/ops.rst, tests/test_postgresql.py, LICENSE
Ideas fused:
- 把原文、confidence、geometry/source location 一起保留为可导出的 requirement provenance
- 未知字段、缺失 target 和非法 relation 明确失败，不把 resolver error 当作 no-match
- migration 使用显式 Column/JSONB；upgrade 与 downgrade 各自有数据库 shape/data gate
Ideas skipped:
- 不引入 docTR、rule-engine 或其他新依赖
- 不复制第三方 OCR/layout pipeline、表达式语法、标准数值表或 prompt
- 不把通用 Alembic autogenerate 逻辑搬入项目 migration
License/scope check:
- docTR Apache-2.0、rule-engine BSD-3-Clause、Alembic MIT
- 仅融合结构和测试思路，无源代码复制
Local validation:
- baseline backend 78 passed；frontend focused 32 passed
```

- [x] **Step 2: 写 schema RED tests**

把 expected columns 改为包含 `technical_requirements`：

```python
def test_automatic_result_schema_and_immutability_trigger() -> None:
    inspector = inspect(engine)
    assert {
        column["name"]
        for column in inspector.get_columns("automatic_results")
    } == {
        "id",
        "project_id",
        "source_file_id",
        "logical_job_id",
        "inventory_ref",
        "candidates",
        "coverage",
        "technical_requirements",
        "provider_call_ids",
        "schema_version",
        "created_at",
    }


def test_review_schema_has_exact_current_persistence_shape() -> None:
    inspector = inspect(engine)
    assert {
        column["name"]
        for column in inspector.get_columns("review_working_copies")
    } == {
        "id",
        "project_id",
        "raw_result_id",
        "version",
        "items",
        "coverage",
        "technical_requirements",
        "sip_metadata",
        "numbering_stale",
        "items_frozen_at",
        "items_frozen_by",
        "items_frozen_version",
        "created_at",
        "updated_at",
    }
```

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_schema.py -q
```

Expected: FAIL，两个 exact-column assertions 都缺
`technical_requirements`，不是数据库连接失败。

- [x] **Step 3: 实现 migration 和 model fields**

`0008_technical_requirements.py` 使用：

```python
"""Add technical requirement persistence.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _empty_requirements_column() -> sa.Column:
    return sa.Column(
        "technical_requirements",
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column("automatic_results", _empty_requirements_column())
    op.add_column("review_working_copies", _empty_requirements_column())


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.scalar(
        sa.text(
            "SELECT "
            "(SELECT count(*) FROM automatic_results "
            " WHERE technical_requirements <> '[]'::jsonb) + "
            "(SELECT count(*) FROM review_working_copies "
            " WHERE technical_requirements <> '[]'::jsonb)"
        )
    )
    if int(populated or 0) != 0:
        raise RuntimeError(
            "technical requirement evidence exists; schema downgrade refused"
        )
    op.drop_column("review_working_copies", "technical_requirements")
    op.drop_column("automatic_results", "technical_requirements")
```

两个 ORM fields 都使用：

```python
technical_requirements: Mapped[list[dict[str, Any]]] = mapped_column(
    JSONB,
    default=list,
    nullable=False,
)
```

- [x] **Step 4: 升级 schema 并验证 exact shape**

Run:

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest backend/tests/integration/test_schema.py -q
```

Expected: migration 到 `0008`，`test_schema.py` PASS。

- [x] **Step 5: 最小更新 durable contracts**

只更新既有 rows：

- `CAND-001`：technical requirement decision/ref 是 frozen automatic evidence；
- `ITEM-005`：SIP suggestion 带 source/rule/version，不能覆盖 confirmed value；
- `ITEM-006`：`Technical Requirement Rule Owner` 独占分类和匹配；
- `REV-002`：raw result 冻结 requirement decisions；
- `REV-003`：working copy 保存 editable requirement relation；
- `REV-004`：match override 是 versioned command；
- `EXP-002`：export 只读 confirmed item fields，不重算 requirement。

不得新增第二组 contract IDs，不改变 P0 status counts。

- [x] **Step 6: 验证并提交**

Run:

```bash
python .agent/harness/scripts/check-contracts.py
git diff --check
```

Expected: contract checker PASS，diff check 无输出。

Commit:

```bash
git add docs/contracts/MAIN_CONTRACT_MATRIX.md backend/alembic/versions/0008_technical_requirements.py backend/app/candidates/models.py backend/app/review/models.py backend/tests/integration/test_schema.py
git commit -m "feat: add technical requirement persistence"
```

## Task 2: Build The Pure Technical Requirement Rule Owner

**Files:**

- Create: `backend/app/candidates/technical_requirements.py`
- Create: `backend/tests/unit/candidates/test_technical_requirements.py`

- [x] **Step 1: 写 reconstruction 和 sample classification RED tests**

测试 helper 明确用当前 `TextObservation`：

```python
def observation(
    observation_id: str,
    raw_text: str,
    *,
    y0: float,
    y1: float,
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id,
        source_type="native",
        observation_level="line",
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=0,
        bbox_pdf=(10.0, y0, 160.0, y1),
        bbox_normalized=(0.05, y0 / 200.0, 0.80, y1 / 200.0),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )
```

覆盖以下 exact tests：

```python
def test_reconstructs_numbered_requirement_block_and_continuation() -> None:
    observations = (
        observation("heading", "技术要求:", y0=10, y1=20),
        observation("one", "1.未标注倒角C0.5", y0=24, y1=34),
        observation("three-a", "3.零件表面不应有划痕、擦", y0=48, y1=58),
        observation("three-b", "伤等损伤零件外观的缺陷", y0=59, y1=69),
    )
    entries = reconstruct_technical_requirement_entries(observations)
    assert [entry.ordinal for entry in entries] == [1, 3]
    assert entries[1].raw_text == "零件表面不应有划痕、擦伤等损伤零件外观的缺陷"
    assert entries[1].source_location_ids == ("three-a", "three-b")


@pytest.mark.parametrize(
    ("text", "subtype"),
    [
        ("未标注倒角C0.5", "default_chamfer"),
        ("锐边去毛刺", "deburr"),
        ("零件表面不应有划痕、擦伤等损伤零件外观的缺陷", "surface_integrity"),
        ("表面阳极氧化亮光银色处理", "surface_treatment"),
        ("未注尺寸公差按GB/T 1804-m执行", "general_dimensional_tolerance"),
        ("未注形位公差按GB/T 1184-k执行", "general_geometric_tolerance"),
    ],
)
def test_classifies_approved_sample(text: str, subtype: str) -> None:
    decision = classify_technical_requirement_entry(entry_for(text))
    assert decision.subtype == subtype
    assert decision.rule_version == "technical-requirement/1"
```

同时覆盖：

- 标题不产生 requirement；
- 标题后无编号不误收；
- 页切换、方向变化、大间距停止 continuation；
- 单个 OCR observation 内含换行时按 segment index 重建；
- 相同文本不同 source identity 得到不同 `requirement_id`；
- unknown standard 为 `unsupported/review_required`。

- [x] **Step 2: 运行 RED**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_technical_requirements.py -q
```

Expected: FAIL with
`ModuleNotFoundError: No module named 'app.candidates.technical_requirements'`。

- [x] **Step 3: 实现 exact contract types**

核心 contract：

```python
TECHNICAL_REQUIREMENT_RULE_VERSION = "technical-requirement/1"

RequirementCategory = Literal[
    "standalone_check",
    "applicability_rule",
    "unsupported",
    "ambiguous",
]
RequirementSubtype = Literal[
    "deburr",
    "surface_integrity",
    "surface_treatment",
    "default_chamfer",
    "general_dimensional_tolerance",
    "general_geometric_tolerance",
    "unsupported",
    "ambiguous",
]
MatchOutcome = Literal["matched_items", "global_scope", "unresolved"]


class SipSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspection_item: str | None = None
    inspection_standard: str | None = None
    key_dimension: str | None = None
    source_page: int = Field(ge=1)
    remarks: str


class TechnicalRequirementDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1)
    ordinal: int | None = Field(default=None, ge=1)
    raw_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    source_location_ids: list[str] = Field(min_length=1)
    page_index: int = Field(ge=0)
    coordinates: list[tuple[float, float, float, float]] = Field(min_length=1)
    category: RequirementCategory
    subtype: RequirementSubtype
    parsed_parameters: dict[str, str]
    match_outcome: MatchOutcome
    matched_candidate_ids: list[str]
    generated_candidate_id: str | None = None
    rule_id: str = Field(min_length=1)
    rule_version: Literal["technical-requirement/1"]
    review_required: bool
    sip_suggestion: SipSuggestion
```

`requirement_id` 使用 `stable_candidate_id()`，输入必须包含 source IDs 和 segment
indexes，不得只使用 raw text。

- [x] **Step 4: 实现 block reconstruction 和 classification**

规则顺序固定：

```python
CLASSIFICATION_RULES = (
    ("general_dimensional_tolerance", classify_general_dimensional_tolerance),
    ("general_geometric_tolerance", classify_general_geometric_tolerance),
    ("default_chamfer", classify_default_chamfer),
    ("deburr", classify_deburr),
    ("surface_integrity", classify_surface_integrity),
    ("surface_treatment", classify_surface_treatment),
)
```

要求：

- standards 只解析 code/class string；
- `GB/T1804-m` 规范化为 `GB/T 1804` + `m`；
- 不加载、不计算标准数值表；
- method/role 不进入 suggestion；
- standalone suggestions 只填 source 能证明的 item/standard/page/remarks。

- [x] **Step 5: 运行 unit GREEN**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_technical_requirements.py -q
```

Expected: PASS。

- [x] **Step 6: 提交**

```bash
git add backend/app/candidates/technical_requirements.py backend/tests/unit/candidates/test_technical_requirements.py
git commit -m "feat: classify technical requirements"
```

## Task 3: Match Requirements In The Candidate Snapshot And Freeze Them

**Files:**

- Modify: `backend/app/candidates/technical_requirements.py`
- Modify: `backend/app/candidates/disposition.py`
- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/tests/unit/candidates/test_technical_requirements.py`
- Modify: `backend/tests/contract/test_automatic_result.py`
- Modify: `backend/tests/e2e/test_offline_automatic_result.py`

- [x] **Step 1: 写 deterministic matching RED tests**

首版 matching contract：

```python
def test_general_dimensional_tolerance_matches_only_untoleranced_dimensions() -> None:
    candidates = (
        envelope("linear", item_type="linear_dimension", nominal="25"),
        envelope(
            "explicit",
            item_type="linear_dimension",
            nominal="30",
            upper_tolerance="0.1",
            lower_tolerance="-0.1",
        ),
        envelope("thread", item_type="thread", thread_spec="M6"),
    )
    decision = evaluate_requirement(
        requirement("未注尺寸公差按GB/T 1804-m执行"),
        candidates,
    )
    assert decision.match_outcome == "matched_items"
    assert decision.matched_candidate_ids == ["linear"]
    assert candidates[0]["payload"].get("upper_tolerance") is None
    assert candidates[0]["payload"].get("lower_tolerance") is None


def test_default_chamfer_and_general_gdt_fail_safe_to_global_scope() -> None:
    chamfer = evaluate_requirement(
        requirement("未标注倒角C0.5"),
        (),
    )
    gdt = evaluate_requirement(
        requirement("未注形位公差按GB/T 1184-k执行"),
        (),
    )
    assert chamfer.match_outcome == "global_scope"
    assert gdt.match_outcome == "global_scope"
    assert chamfer.generated_candidate_id is not None
    assert gdt.generated_candidate_id is not None
```

增加 conflict tests：

- 同页出现 `GB/T 1804-m` 与 `GB/T 1804-f`；
- explicit tolerance 不能被 ref 覆盖；
- thread 不匹配；
- matched refs 双向一致；
- unresolved 不创建 candidate。

- [x] **Step 2: 写 snapshot 和 persistence RED tests**

`CandidateSnapshot` 新增：

```python
technical_requirements: tuple[dict[str, Any], ...] = ()
```

新增 exact assertions：

```python
def test_candidate_snapshot_reconstructs_and_matches_six_technical_requirements() -> None:
    snapshot = candidate_snapshot_from_inventory((approved_requirement_page(),))
    assert len(snapshot.technical_requirements) == 6
    assert {
        requirement["subtype"]
        for requirement in snapshot.technical_requirements
    } == {
        "default_chamfer",
        "deburr",
        "surface_integrity",
        "surface_treatment",
        "general_dimensional_tolerance",
        "general_geometric_tolerance",
    }
    assert all(
        candidate["payload"]["raw_text"] != "技术要求"
        for candidate in snapshot.candidates
    )
```

`build_automatic_result()` contract test：

```python
assert result.technical_requirements == list(technical_requirements)
```

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_technical_requirements.py backend/tests/contract/test_automatic_result.py backend/tests/e2e/test_offline_automatic_result.py -q
```

Expected: FAIL because snapshot/result writer does not yet carry requirements。

- [x] **Step 3: 实现 two-phase snapshot**

`candidate_snapshot_from_inventory()` 顺序固定：

```python
observations = _selected_observations(pages)
reconstruction = reconstruct_technical_requirement_entries(observations)
technical_source_ids = reconstruction.source_location_ids
local_observations = [
    observation
    for observation in observations
    if observation.observation_id not in technical_source_ids
]
local_snapshot = _candidate_snapshot_from_observations(
    local_observations,
    visual_observations,
)
evaluation = evaluate_technical_requirements(
    reconstruction.entries,
    local_snapshot.candidates,
)
```

然后：

- standalone/global-scope requirement 生成
  `general_requirement / global_requirement / balloon_required=false` candidate；
- matched applicability rule 不生成重复 item candidate；
- target envelope 增加 ordered `technical_requirement_refs`；
- consumed requirement observations 生成 exactly one coverage disposition；
- unresolved 为 `ambiguous/requires_confirmation=true`；
- safe matched rule 为 `reference_context/requires_confirmation=false`；
- technical requirement generated candidate 进入既有 confidence policy。

- [x] **Step 4: 退役旧 active path**

删除：

```python
from app.candidates.disposition import classify_technical_requirement
```

删除 while-loop 内单行调用。`disposition.py` 不再导出
`classify_technical_requirement()`；既有 explicit verb/check cases 移入新 Owner
unit tests。

用 `rg` 验证唯一 Owner：

```bash
rg -n "classify_technical_requirement|technical_requirements" backend/app backend/tests
```

Expected: 没有旧 function 或 call site；production classification 只指向
`app.candidates.technical_requirements`。

- [x] **Step 5: 持久化并验证 cross references**

`build_automatic_result()` 增加：

```python
technical_requirements: Sequence[Mapping[str, Any]] = (),
```

在数据库访问前调用：

```python
validated_requirements = validate_technical_requirements(
    technical_requirements,
    candidate_ids={
        str(candidate["candidate_id"])
        for candidate in validated_candidates
    },
)
```

`InventoryPipeline.run()` 传：

```python
technical_requirements=snapshot.technical_requirements,
```

unknown rule version、duplicate requirement ID、missing target ID、non-canonical target order
必须 fail closed 为 contract error。

- [x] **Step 6: 运行 focused GREEN 和 owner inventory**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_technical_requirements.py backend/tests/contract/test_automatic_result.py backend/tests/e2e/test_offline_automatic_result.py -q
rg -n "classify_technical_requirement" backend/app backend/tests
```

Expected: tests PASS；`rg` 无旧 symbol。

- [x] **Step 7: 提交**

```bash
git add backend/app/candidates/technical_requirements.py backend/app/candidates/disposition.py backend/app/processing/automatic_result.py backend/app/processing/pipeline.py backend/tests/unit/candidates/test_technical_requirements.py backend/tests/contract/test_automatic_result.py backend/tests/e2e/test_offline_automatic_result.py
git commit -m "feat: match technical requirements to candidates"
```

## Task 4: Project Suggestions Into The Versioned Review Aggregate

**Files:**

- Modify: `backend/app/review/schemas.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/app/review/router.py`
- Modify: `backend/tests/contract/test_review_schema.py`
- Modify: `backend/tests/integration/test_review_working_copy.py`
- Modify: `backend/tests/integration/test_review_operations.py`
- Modify: `backend/tests/integration/test_project_workbench_api.py`

- [x] **Step 1: 写 bootstrap RED test**

```python
def test_review_bootstrap_projects_requirement_suggestions_without_confirming() -> None:
    working = ReviewService(db_session).create_from_raw(raw_result.id)
    assert len(working.technical_requirements) == 6
    deburr = next(
        item for item in working.items
        if item.get("raw_text") == "锐边去毛刺"
    )
    assert deburr["inspection_item"] == "去毛刺与锐边检查"
    assert deburr["inspection_standard"] == "锐边去毛刺"
    assert deburr["sip_detail_fields_confirmed"] is False
    assert deburr["balloon_required"] is False
```

matched dimension assertion：

```python
dimension = next(item for item in working.items if item["item_id"] == "linear")
assert dimension["inspection_standard"] == "GB/T 1804-m"
assert dimension["upper_tolerance"] is None
assert dimension["lower_tolerance"] is None
assert dimension["sip_detail_fields_confirmed"] is False
assert dimension["sip_suggestion_provenance"]["inspection_standard"] == requirement_id
```

- [x] **Step 2: 写 match override command RED tests**

Command contract：

```python
class SetTechnicalRequirementMatch(CommandBase):
    type: Literal["set_technical_requirement_match"]
    requirement_id: NonBlankText
    outcome: Literal["matched_items", "global_scope", "excluded"]
    matched_item_ids: list[NonBlankText] = Field(default_factory=list)
```

validator invariants：

```python
if outcome == "matched_items" and not matched_item_ids:
    raise ValueError("matched_items requires at least one item")
if outcome != "matched_items" and matched_item_ids:
    raise ValueError("only matched_items accepts item targets")
if len(set(matched_item_ids)) != len(matched_item_ids):
    raise ValueError("matched_item_ids must be unique")
```

Integration tests prove：

- command uses expected version and active lock；
- targets must exist and be active；
- confirmed SIP values are never overwritten or cleared；
- only unconfirmed values with matching provenance are removed on relink；
- `global_scope` creates/reactivates stable no-balloon item；
- `excluded` removes active relation and marks requirement excluded；
- command and requirement update commit atomically；
- frozen working copy rejects command。

- [x] **Step 3: 运行 RED**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_review_schema.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_project_workbench_api.py -q
```

Expected: FAIL because model/API/service do not project requirements。

- [x] **Step 4: 实现 bootstrap 和 suggestion provenance**

`ReviewService.create_from_raw()` 先构造 items，再投影：

```python
items = [
    self._current_item(candidate, raw_result.schema_version)
    for candidate in raw_result.candidates
]
technical_requirements = project_technical_requirements(
    raw_result.technical_requirements,
    items,
)
```

suggestion rules：

- 只写 blank、unconfirmed fields；
- 每个写入 field 记录
  `sip_suggestion_provenance[field_name] = requirement_id`；
- 不写 `inspection_method`、`inspection_role`；
- 不设置 `sip_detail_fields_confirmed=true`；
- matched rule 把 refs 放在 target item；
- global/standalone requirement 使用 stable generated item ID；
- automatic immutable decision 深拷贝到 working-copy requirement state。

- [x] **Step 5: 实现 transactional override**

在 `_apply_command()` 中把 `technical_requirements` 作为同一 deep-copy aggregate
传入，保存时与 items/coverage 一次提交。不要新增独立 endpoint 或 frontend-local
Owner。

API `_working_copy()` 增加：

```python
"technical_requirements": working.technical_requirements,
```

`manual_review_count()` 不能把一个 matched requirement 与 target item 重复计数；
unresolved requirement 仍由 coverage entry 计数。

- [x] **Step 6: 运行 GREEN**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_review_schema.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_project_workbench_api.py -q
```

Expected: PASS。

- [x] **Step 7: 提交**

```bash
git add backend/app/review/schemas.py backend/app/review/service.py backend/app/review/router.py backend/tests/contract/test_review_schema.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_project_workbench_api.py
git commit -m "feat: review technical requirement matches"
```

## Task 5: Expose Matches And SIP Suggestions In The Workbench

**Files:**

- Create: `frontend/src/components/workbench/TechnicalRequirementPanel.tsx`
- Create: `frontend/src/components/workbench/TechnicalRequirementPanel.test.tsx`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

- [x] **Step 1: 检查 live-agent 和 dirty-file ownership**

Run:

```bash
git status --short -- frontend/src/api/types.ts frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/components/workbench/InspectionWorkbench.test.tsx frontend/src/components/workbench/SelectedSipDetailFields.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles/workbench.css
```

并检查 live agents 的 assigned paths。若任何目标文件属于另一个 writer，停止并报告
`blocked/ownership overlap`；不得 reset、stash、restore 或覆盖。

- [x] **Step 2: 写 component RED tests**

Frontend contract：

```ts
export type TechnicalRequirement = {
  requirement_id: string;
  ordinal?: number | null;
  raw_text: string;
  source_location_ids: string[];
  page_index: number;
  category:
    | "standalone_check"
    | "applicability_rule"
    | "unsupported"
    | "ambiguous";
  subtype: string;
  match_outcome: "matched_items" | "global_scope" | "unresolved";
  matched_candidate_ids: string[];
  generated_candidate_id?: string | null;
  rule_version: "technical-requirement/1";
  review_required: boolean;
  review_status?: "suggested" | "confirmed" | "excluded";
};
```

Tests：

```tsx
expect(screen.getByText("未注尺寸公差按 GB/T 1804-m 执行")).not.toBeNull();
expect(screen.getByText("已匹配 2 项")).not.toBeNull();
expect(screen.getByText("全局要求")).not.toBeNull();
expect(screen.getByText("待确认")).not.toBeNull();
```

点击 matched target：

```tsx
fireEvent.click(screen.getByRole("button", { name: "查看匹配检验项：25" }));
expect(onSelectItem).toHaveBeenCalledWith("dimension-25");
```

override command：

```tsx
expect(onCommand).toHaveBeenCalledWith({
  type: "set_technical_requirement_match",
  requirement_id: "requirement-5",
  outcome: "matched_items",
  matched_item_ids: ["dimension-25"],
});
```

- [x] **Step 3: 运行 RED**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/TechnicalRequirementPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx src/components/workbench/SelectedSipDetailFields.test.tsx
```

Expected: FAIL because component/types do not exist。

Execution note: component test 与最小实现同批落盘，未单独保留 RED 输出；随后 focused
suite `36 passed`，production build PASS。未为了补造 RED 回退已验证实现。

- [x] **Step 4: 实现 panel 和唯一 submit seam**

`InspectionWorkbench` 只集成：

```tsx
<TechnicalRequirementPanel
  requirements={workingCopy?.technical_requirements ?? []}
  items={items}
  disabled={reviewCommandsDisabled}
  onSelectItem={selectItem}
  onCommand={submitCommand}
/>
```

要求：

- 不在 frontend 解析 raw text；
- 不在 frontend 重算 match；
- `unresolved` 清晰显示待确认；
- matched target 使用 existing `selectItem()`，同步 PDF、Review、SIP selection；
- override 使用 existing `submitCommand()`；
- panel 不复制 SIP form；
- dirty/save/freeze 行为保持现状。

- [x] **Step 5: 验证 SIP suggestions 未被自动确认**

`SelectedSipDetailFields.test.tsx` 证明：

- `inspection_item` / `inspection_standard` 建议会作为初始值显示；
- method/role 仍为空；
- Confirm 按钮在 mandatory fields 不完整时 disabled；
- 用户补全并提交后才发送 `set_sip_detail_fields`。

- [x] **Step 6: 运行 frontend GREEN 和 build**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/TechnicalRequirementPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx src/components/workbench/SelectedSipDetailFields.test.tsx
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: tests PASS；TypeScript/Vite build PASS。若只有既有 chunk-size warning，原样
记录，不能称为无 warning。

- [x] **Step 7: 提交**

```bash
git add frontend/src/api/types.ts frontend/src/components/workbench/TechnicalRequirementPanel.tsx frontend/src/components/workbench/TechnicalRequirementPanel.test.tsx frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/components/workbench/InspectionWorkbench.test.tsx frontend/src/components/workbench/SelectedSipDetailFields.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles/workbench.css
git commit -m "feat: show technical requirement matches"
```

## Task 6: Prove Review, Numbering, And SIP Export Boundaries

**Files:**

- Modify: `backend/tests/integration/test_excel_export.py`
- Modify: `backend/tests/integration/test_balloon_service.py`
- Modify: `backend/tests/integration/test_review_freeze.py`
- Modify: `backend/tests/e2e/test_offline_automatic_result.py`

- [x] **Step 1: 写 cross-layer RED tests**

必须证明：

```python
assert global_requirement["balloon_required"] is False
assert global_requirement.get("formal_number") is None
assert matched_dimension["upper_tolerance"] is None
assert matched_dimension["lower_tolerance"] is None
assert matched_dimension["inspection_standard"] == "GB/T 1804-m"
assert matched_dimension["sip_detail_fields_confirmed"] is False
```

freeze 前：

```python
with pytest.raises(FreezeBlocked, match="sip_detail_fields_unconfirmed"):
    service.freeze_items(
        working.id,
        expected_version=working.version,
        operator_id="operator-1",
    )
```

确认后 Excel：

```python
assert general_requirement_row["balloon_number"] == ""
assert general_requirement_row["inspection_standard"] == confirmed_standard
assert all(
    "technical-requirement/1" not in cell_value
    for cell_value in visible_business_cells
)
```

`rule_version` 只能进入 provenance/diagnostic，不污染 SIP 业务单元格。

- [x] **Step 2: 运行 RED 或确认已有实现直接满足**

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_excel_export.py backend/tests/integration/test_balloon_service.py backend/tests/integration/test_review_freeze.py backend/tests/e2e/test_offline_automatic_result.py -q
```

Expected: 新 assertions 在缺少完整 cross-layer wiring 时 FAIL；如果直接 PASS，记录
它证明现有 Owner 无需 production 修改，不为了制造 GREEN 而改代码。

- [x] **Step 3: 只修复真实 boundary gap**

允许修改 production export/balloon code 的条件：

- 新测试暴露 requirement item 被编号；
- export 读取 suggestion 而不是 confirmed fields；
- freeze 未阻止未确认 SIP。

若没有这些 failure，不修改 `backend/app/exports/**` 或
`backend/app/balloons/**`。

- [x] **Step 4: 运行 focused backend suite 和 contracts**

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_technical_requirements.py backend/tests/unit/candidates/test_advisor.py backend/tests/contract/test_automatic_result.py backend/tests/contract/test_review_schema.py backend/tests/integration/test_schema.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_review_freeze.py backend/tests/integration/test_balloon_service.py backend/tests/integration/test_excel_export.py backend/tests/e2e/test_offline_automatic_result.py -q
python .agent/harness/scripts/check-contracts.py
```

Expected: 全部 PASS。

- [x] **Step 5: 提交 tests 和必要的最小修复**

如果无 production gap：

```bash
git add backend/tests/integration/test_excel_export.py backend/tests/integration/test_balloon_service.py backend/tests/integration/test_review_freeze.py backend/tests/e2e/test_offline_automatic_result.py
git commit -m "test: cover technical requirement export boundaries"
```

如果有 production gap，只额外 stage 实际修复文件，并在 commit 前用
`git diff --cached --name-only` 核对。

Execution note (`2026-07-30`):

- cross-layer suite `59 passed`；focused backend suite `227 passed`；
- contract mirror PASS：`unclassified=0`、`mirror_drift=0`、
  `bindings_drift=0`；
- existing export、balloon 和 freeze Owners 直接满足边界，未修改 production；
- freeze 对外继续使用稳定的 `unresolved_confirmation`，测试同时证明内部精确
  原因为 `sip_detail_fields_unconfirmed`；
- commit: `15a2e00`.

## Task 7: Real-PDF Browser Acceptance, Smoke Test, And Independent Review

**Files:**

- Create: `.agent/real-pdf-inputs.env`
- Create: `frontend/e2e/technical-requirement-matching.spec.ts`
- Modify: `backend/app/candidates/technical_requirements.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/tests/unit/candidates/test_technical_requirements.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/styles/workbench.css`
- Modify: `docs/superpowers/plans/2026-07-30-technical-requirement-recognition-and-matching.md`

- [x] **Step 1: 确认 approved real PDF precondition**

复用现有 E2E input contract：

```bash
test -n "$QI_MVP_E2E_PDF"
test -f "$QI_MVP_E2E_PDF"
```

Expected: 两项均成功，且 PDF 确实包含本设计的六条技术要求。若只有截图或 PDF 不含
这些要求，runtime acceptance 标记 `blocked`，不得用 synthetic fixture 替代。

- [x] **Step 2: 写 Playwright acceptance**

测试必须上传真实 PDF，并断言：

```ts
await expect(
  page.getByRole("region", { name: "技术要求匹配" }),
).toBeVisible();
await expect(page.getByText("未标注倒角 C0.5")).toBeVisible();
await expect(page.getByText("锐边去毛刺")).toBeVisible();
await expect(page.getByText(/划痕、擦伤/)).toBeVisible();
await expect(page.getByText(/阳极氧化亮光银色/)).toBeVisible();
await expect(page.getByText(/GB\\/T 1804-m/)).toBeVisible();
await expect(page.getByText(/GB\\/T 1184-k/)).toBeVisible();
```

同时从 workbench response 断言：

```ts
expect(snapshot.working_copy.technical_requirements).toHaveLength(6);
expect(
  snapshot.working_copy.technical_requirements
    .find((item) => item.subtype === "general_dimensional_tolerance")
    ?.match_outcome,
).toBe("matched_items");
expect(
  snapshot.working_copy.items
    .filter((item) => item.item_type === "general_requirement")
    .every((item) => item.balloon_required === false),
).toBe(true);
```

完成一个 target navigation、一个 match override、一个 SIP confirm，并刷新页面证明
server persistence。

- [x] **Step 3: 启动 source-mounted runtime 并运行 Playwright**

使用仓库现有入口：

Terminal A：

```bash
make dev-local-api
```

Terminal B：

```bash
make dev-local-frontend
```

Terminal C：

```bash
QI_MVP_BASE_URL=http://127.0.0.1:5173 QI_MVP_E2E_PDF="$QI_MVP_E2E_PDF" micromamba run -n qi-p0 npm --prefix frontend run e2e -- technical-requirement-matching.spec.ts
```

Expected: PASS。保留测试输出和必要截图在现有 Playwright output 位置，不创建新的
evidence convention。

- [x] **Step 4: 使用 Chrome MCP 做 integrated visual QA**

检查：

- 六条原文没有错误截断；
- 第 3 条续行合并正确；
- match/global/unresolved 状态清晰；
- 点击 matched item 同步列表、PDF 和 SIP；
- suggestion 与 confirmed 状态不混淆；
- 窄 viewport 不遮挡 review actions；
- freeze 前 unresolved/SIP blocker 仍生效。

发现 bug 时回到对应 task 做最小修复并重跑 focused tests。

- [x] **Step 5: 使用 `auto-feature-smoke-test`**

必须完整读取并执行 skill，覆盖当前 feature flow。报告实际 runtime URL、操作、console
errors、network failures 和截图证据；不能把 Playwright 单测等同于 smoke test。

Task 7 runtime evidence (`2026-07-30`):

- approved input 固定在 `.agent/real-pdf-inputs.env`；选定 PDF 为
  `BK20101401-09L1000#引拔梁(400W)#C1.PDF`，原生文本包含六条要求；
- fresh upload project `9bd28a2a-6706-4bbb-9be8-fe49ac62fa3a`，
  `automatic-result://fbfa3eae-9f7b-4c7b-856b-a396de65f722`；
- Playwright fresh upload + target navigation + SIP confirm + match override +
  reload persistence：`1 passed (4.1m)`；
- Chrome MCP desktop viewport：requirement count `6`，技术要求列表
  `scrollHeight > clientHeight`，与下方 workspace 无 overlap；匹配目标跳转后
  自动切换“全部”并选中目标；console warning/error 为 `0`，status/lock/workbench/
  source-pdf 四个请求均为 `200`；
- smoke screenshot：`/tmp/qi-techreq-playwright-pass-20260730/`
  `technical-requirement-matching.png`。

- [ ] **Step 6: 独立 reviewer gate**

按仓库规则选择并绑定本地 `reviewer` profile，reviewer 只读，范围为本 plan commits 和
以下问题：

- 旧 classifier 是否真正退役；
- requirement/source/match identity 是否稳定；
- GB/T reference 是否错误写成数值公差；
- confirmed SIP 是否可能被 suggestion 覆盖；
- global requirement 是否错误编号/气泡；
- migration rollback 是否会静默丢数据；
- tests 是否覆盖真实六条输入而不是仅 synthetic happy path。

reviewer 必须输出：

```text
Verdict: accept | accept with concerns | reject
Blocking issues:
Non-blocking concerns:
Evidence:
Minimal follow-up:
```

当前子代理工具若仍不能显式绑定 required profile/model，不得悄悄启动 generic child。
应先报告 tool limitation；没有独立 review evidence 时不得 claim reviewer gate passed。

- [x] **Step 7: Parent final verification**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_technical_requirements.py backend/tests/unit/candidates/test_advisor.py backend/tests/contract/test_automatic_result.py backend/tests/contract/test_review_schema.py backend/tests/integration/test_schema.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_review_freeze.py backend/tests/integration/test_balloon_service.py backend/tests/integration/test_excel_export.py backend/tests/e2e/test_offline_automatic_result.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
python .agent/harness/scripts/check-contracts.py
git diff --check
```

Expected: 全部 PASS；build 仅允许明确报告的既有 warning。

- [ ] **Step 8: Close plan only when runtime and review gates pass**

把本 plan `Status` 改为 `completed`，记录：

- implementation commits；
- focused/full validation commands；
- approved PDF runtime evidence；
- `auto-feature-smoke-test` result；
- independent reviewer verdict；
- remaining non-blocking risk。

Task 7 checkpoint (`2026-07-30`):

- approved real PDF precondition: PASS；用户提供的两个目录固定在
  `.agent/real-pdf-inputs.env`，未写入 `AGENTS.md`；
- runtime root-cause fixes: PASS；真实图框文字不再截断技术要求区块，
  `CandidateAdvisor` 改变候选集合后由 Technical Requirement Rule Owner
  清理旧 relation 并对最终候选重新匹配；
- `auto-feature-smoke-test`: PASS；fresh real-PDF Playwright `1 passed
  (4.1m)`，Chrome MCP integrated visual QA PASS；
- parent verification: backend `250 passed`，frontend `209 passed`，
  production build PASS，保留既有 `>500 kB` chunk warning；contract mirror 与
  `git diff --check` PASS；
- independent reviewer gate: BLOCKED；当前 collaboration tool 无法显式绑定本地
  `reviewer` profile/model，按已批准的主线程串行约束未启动 generic child；
- Task 7 Steps 1–5、7 已完成；Steps 6、8 仍未完成，plan 保持
  `in_progress`。

如果 real PDF 或 reviewer gate blocked，保持 `Status: in_progress` 并记录唯一 blocker，
不得用文档勾选替代实际证据。

Commit:

```bash
git add frontend/e2e/technical-requirement-matching.spec.ts docs/superpowers/plans/2026-07-30-technical-requirement-recognition-and-matching.md
git commit -m "test: verify technical requirement matching flow"
```

## Completion Contract

本 plan 只有同时满足以下条件才完成：

- 六条 approved technical requirements 在 current real PDF processing 中全部可见；
- 第 3 条 OCR/native continuation 正确重建；
- standalone requirements 进入无气泡 SIP items；
- `GB/T 1804-m` 只匹配受支持、无显式公差的 dimensions；
- `GB/T 1184-k` 与 default chamfer 在没有安全 target 时保持 global scope；
- 没有自动标准数值换算；
- suggestions 不覆盖 confirmed SIP，export 只读 confirmed fields；
- global requirements 不生成 balloon、不占 formal number；
- unresolved/conflicting requirements 阻止 freeze 或保持 reviewable；
- migration upgrade、legacy empty-array read、data-safe rollback 有测试；
- old classifier active path 已退役；
- focused backend、full frontend、build、contracts、Playwright、Chrome smoke 全部实际运行；
- independent reviewer 接受，或所有 blocking issues 已修复并复审；
- 所有 task commits 只包含 scoped files，unrelated dirty state 保持不变。
