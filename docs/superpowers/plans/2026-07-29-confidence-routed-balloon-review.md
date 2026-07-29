# Confidence-Routed Balloon Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让满足统一证据门控的 high-confidence 自动识别项无需逐条人工确认即可进入正式候选集并显示红色自动通过气泡，只将 medium/low、legacy 和 source-only ambiguity 放入人工审核队列。

**Architecture:** 在 candidate projection/local validation 与 `AutomaticResult` 冻结之间新增唯一 `ConfidencePolicy Owner`。Provider 只提供 source signal，policy 结合 typed semantics、source ownership、coverage 和 conflict evidence 提交不可变 decision；Review、workbench、frontend 和 export 只消费该 decision，不重算 confidence。现有 project-level freeze、formal numbering、balloon validation、SIP confirmation、immutable `ReviewedResult` 和 atomic export 保持原 Owner。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy、Pydantic、PyMuPDF、pytest、TypeScript、React、Vitest、Playwright、Micromamba `qi-p0`

---

## Status

- Date: `2026-07-29`
- Status: `draft; awaiting user approval`
- Selected lane: `Heavy`
- Validation action: `replan`
- Design source:
  `docs/superpowers/specs/2026-07-29-confidence-routed-balloon-review-design.md`
- Supersession boundary: 本 plan 是该 feature 的唯一 successor implementation plan；
  不修改或重开已 sealed 的七天 P0 task 状态。
- Production authorization: 用户批准本 plan 前，不得执行 Task 1 之后的 production
  code 修改。

## Problem Boundary

| Dimension | Decision |
| --- | --- |
| Changed decision | automatic candidate 的 `confidence_band` 与 `review_disposition` |
| Single owner | `backend/app/candidates/confidence.py::ConfidencePolicy` |
| Owner insertion point | `InventoryPipeline.run()` 中 `check_coverage()` 之后、`build_automatic_result()` 之前 |
| Old Provider path | `visual-symbol-review/1.requires_confirmation` → `replace` |
| Old projection path | visual candidate 无条件 `requires_confirmation=true` → `replace` |
| Old Review path | `_current_item()` 对所有 candidate 写 `status="pending"` → `replace` |
| Old frontend path | 根据 pending/color 猜测 disposition → `replace` |
| Preserved contracts | project freeze、formal numbering、placement/collision veto、SIP Owner、ReviewedResult、atomic export |
| Database impact | JSON/response additive changes；不做 database migration |

多来源 signal 的 canonical 聚合规则固定为：

```python
candidate_signal = min(source_signal[source_id] for source_id in source_location_ids)
```

任一贡献来源 signal 缺失、非法、非有限或不属于该 candidate 时，不计算部分平均值，
直接触发 `source_signal_invalid` veto 并得到 `low / review_required`。这个规则同时适用
于 composite text、同一 visual candidate 的多个 detection，以及 text/visual 混合证据。

当前实现不维护 source/type high 白名单。所有现有 typed candidate family 都使用同一
eligibility gates；coarse fallback、unknown feature、未解决冲突或缺少 local
association 的 family 自然 fail closed。首批 release gate 必须对当前 native、OCR、
visual 的所有支持 family 跑完本 plan 的 frozen positive/negative fixtures，才视为
Quality Owner 对 `candidate-confidence/1` high path 的批准。

## Runtime Flow

```text
native / Tencent OCR / visual Provider signals
                     │
                     ▼
candidate projection + local semantic validation
                     │
                     ▼
Coverage Owner ── blocking/ambiguity/conflict evidence
                     │
                     ▼
ConfidencePolicy Owner
  ├─ high   → auto_accepted
  └─ medium/low/legacy → review_required
                     │
                     ▼
AutomaticResult /2 (immutable decision + evidence codes)
                     │
                     ▼
Review working copy
  ├─ auto_accepted → editable, no per-item confirmation
  └─ review_required → manual queue
                     │
                     ▼
project freeze → formal numbering → placement/collision veto
                     │
                     ▼
ReviewedResult → PDF + SIP Excel + manifest /2
```

## Ownership And Writer Order

同一 task 同一 file group 只允许一个 writer。推荐执行顺序不可并行改写：

1. Task 1：contract 与 schema guard；
2. Task 2：纯 confidence policy；
3. Task 3：source signal 与 visual Provider v2；
4. Task 4：pipeline 与 AutomaticResult `/2`；
5. Task 5：Review/workbench；
6. Task 6：frontend；
7. Task 7：export provenance；
8. Task 8：cross-layer verification、browser、independent review。

只读 explorer/reviewer 可并行，但不得更新 plan、status、fixtures 或代码。任何 writer
开始前必须先检查 live agents 和 assigned paths，避免与其他 writer 重叠。

## Task 1: Amend Durable Contracts And Add `/2` Contract Guards

**Files:**

- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Create: `backend/app/candidates/confidence.py`
- Modify: `backend/app/processing/automatic_result.py`
- Create: `backend/tests/contract/test_automatic_result.py`
- Test: `backend/tests/contract/test_review_schema.py`
- Test: `backend/tests/contract/harness/test_contract_architecture.py`

- [ ] **Step 1: 使用 `github-oss-fusion` 做受限 prior-art 检查**

仅研究 confidence calibration 边界测试、evidence provenance 和 fail-closed schema
validation 的成熟做法；不得引入外部阈值、模型评分器、依赖或大段实现。最终 handoff
记录搜索过的 repositories、采用的测试/错误处理思路和明确跳过的内容。

- [ ] **Step 2: 更新 durable contract**

在既有 rows 中最小修改：

- `CAND-001`：candidate envelope 冻结 `confidence_decision`、policy version 和
  ordered evidence codes；
- `CAND-004`：Provider confidence 只是 signal，不能提交 auto acceptance；
- `CAND-006`：`ConfidencePolicy Owner` 独占 high/medium/low 和
  auto-accepted/review-required mapping，low 不得 auto-exclude；
- `REV-003`：working copy 保留 status、acceptance source 和 immutable confidence
  provenance；
- `REV-006`：auto-accepted candidate 不需要逐条确认，但 SIP、coverage 和 placement
  blockers 不变；
- `BAL-002/BAL-003`：freeze 前红色 marker 是 provisional candidate number，
  freeze 后才是 formal number。

不得新增第二组 contract IDs，也不得修改已 sealed P0 plan 的完成状态。

- [ ] **Step 3: 先写 `/2` envelope RED tests**

在 `backend/tests/contract/test_automatic_result.py` 覆盖：

- `test_automatic_result_v2_rejects_candidate_without_confidence_decision`
- `test_automatic_result_v2_rejects_unknown_confidence_policy`
- `test_automatic_result_v2_accepts_complete_confidence_decision`
- `test_automatic_result_v1_remains_readable_without_confidence_decision`

断言 `/2` 必须精确包含：

```python
{
    "band": "high" | "medium" | "low",
    "review_disposition": "auto_accepted" | "review_required",
    "policy_version": "candidate-confidence/1",
    "evidence_codes": list[str],
}
```

运行：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_automatic_result.py \
  backend/tests/contract/test_review_schema.py -q
```

Expected: 新 tests 因 `/2` 尚无 validator 而失败；既有 `/1` test 保持通过。

- [ ] **Step 4: 实现 exact `/2` validator**

在 `automatic_result.py`：

```python
from app.candidates.confidence import (
    CONFIDENCE_POLICY_VERSION,
    validate_confidence_decision,
)

AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/1"
NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/2"
```

`CONFIDENCE_POLICY_VERSION`、frozen evidence-code order 和
`ConfidenceDecisionContractError`、`validate_confidence_decision()` 实际定义在新
`backend/app/candidates/confidence.py`；`automatic_result.py` 只 import/reuse，
不得复制常量或 validator。Task 1 先建立 exact decision contract，Task 2 在同一模块
扩展 evaluator。

新增 `_validated_candidates_for_schema()`，要求：

- `/2` 每个 candidate 有且只有合法 decision；
- `high` 只能配 `auto_accepted`；
- `medium/low` 只能配 `review_required`；
- policy version 必须精确匹配；
- evidence codes 必须是非空、无重复、按 policy canonical order 排列的 strings；
- 未知 schema 或 policy 抛出 `ValueError`，不创建 `AutomaticResult`；
- `/1` reader 不回填、不改写；其 Review projection 在 Task 5 fail closed。

`build_automatic_result()` 在任何数据库 mutation 前调用 validator。本 task 只允许
test 显式传 `/2` 验证新 guard；active writer default 暂时保持 `/1`，避免在 policy
尚未接入时产生没有 decision 的 `/2` 或让中间 commit 失绿。Task 4 接入 policy 后再把
active default 切到 `/2`，并禁止 production caller 显式写 `/1`。

- [ ] **Step 5: 运行 focused contract checks**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_automatic_result.py \
  backend/tests/contract/test_review_schema.py \
  backend/tests/contract/harness/test_contract_architecture.py -q
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py
```

Expected: focused tests 和 contract checker 全部通过；不产生 generated-file drift。

- [ ] **Step 6: Commit**

```bash
git add docs/contracts/MAIN_CONTRACT_MATRIX.md \
  backend/app/candidates/confidence.py \
  backend/app/processing/automatic_result.py \
  backend/tests/contract/test_automatic_result.py \
  backend/tests/contract/test_review_schema.py \
  backend/tests/contract/harness/test_contract_architecture.py
git commit -m "feat: define confidence decision contract"
```

## Task 2: Implement The Single `ConfidencePolicy Owner`

**Files:**

- Modify: `backend/app/candidates/confidence.py`
- Create: `backend/tests/unit/candidates/test_confidence.py`
- Create: `backend/tests/fixtures/confidence/candidate-confidence-v1.json`
- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/tests/e2e/test_offline_automatic_result.py`

- [ ] **Step 1: 写 policy boundary RED tests**

`test_confidence.py` 必须覆盖：

- native deterministic exact signal `1.0`；
- Tencent OCR percent normalization：`0`、`70`、`95`、`100`；
- unit interval normalization：`0`、`0.70`、`0.95`、`1`；
- `NaN`、`inf`、负值、越界、`bool` 和缺失；
- `0.699... / 0.700... / 0.949... / 0.950...`；
- 多来源 signal 取 minimum；
- 任一缺失/invalid source 使 band 为 low；
- 每个 hard eligibility veto 阻止 high；
- low 永远映射 `review_required`，绝不 auto-exclude；
- evidence code 顺序和 decision digest deterministic。

`backend/tests/fixtures/confidence/candidate-confidence-v1.json` 保存参数化 release
gate cases；每个 source/type family 至少一条 positive 和一条逐字段 negative，并覆盖
native、Tencent OCR、visual 三类 signal。fixture 只保存 candidate envelope、source
signals、coverage/conflict facts 和 expected decision，不保存 PDF bytes 或 Provider
reasoning。

运行：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_confidence.py -q
```

Expected: import/new behavior 不存在，tests 失败。

- [ ] **Step 2: 定义 frozen types 与 constants**

`confidence.py` 使用不可变 dataclasses：

```python
CONFIDENCE_POLICY_VERSION = "candidate-confidence/1"
HIGH_THRESHOLD = Decimal("0.95")
MEDIUM_THRESHOLD = Decimal("0.70")


@dataclass(frozen=True)
class CandidateSourceSignal:
    source_location_id: str
    source_type: Literal["native", "ocr", "visual"]
    normalized_value: Decimal | None


@dataclass(frozen=True)
class ConfidenceDecision:
    band: Literal["high", "medium", "low"]
    review_disposition: Literal["auto_accepted", "review_required"]
    policy_version: str
    evidence_codes: tuple[str, ...]
```

只允许 frozen evidence enum；禁止保存 raw Provider payload 或 reasoning text。

- [ ] **Step 3: 实现 source normalization**

提供明确 adapter，不猜量纲：

```python
normalize_native_signal(*, exact_match: bool) -> Decimal | None
normalize_tencent_ocr_signal(percent: float | None) -> Decimal | None
normalize_visual_signal(unit_value: float | None) -> Decimal | None
```

使用 `Decimal(str(value))`，先拒绝 `bool`、非有限和越界值。Tencent OCR 只按
`value / 100`；visual 只接受 `[0, 1]`。

- [ ] **Step 4: 实现 policy evaluation**

`ConfidencePolicy.evaluate_candidates()` 输入 candidate envelopes、coverage report、
duplicate/conflict relations 和 source signals，输出带 immutable
`confidence_decision` 的新 envelopes。

semantic completeness 使用 frozen per-family table，不能只依赖
`Candidate.model_validate()`：

| `item_type` | High eligibility required semantic fields |
| --- | --- |
| `linear_dimension` | finite `nominal` |
| `diameter_dimension` | finite `nominal`；`feature_kind` 必须是 `hole / shaft / cylindrical_feature`，不得是 `unknown/null` |
| `thread` | non-blank canonical `thread_spec`；`through` 是 boolean；有 `thread_depth` 时必须 finite/non-negative |
| `radius` | finite/non-negative `radius_value` |
| `angle` | finite `angle_value` 且在 frozen parser 支持范围；tolerance 若存在必须 finite |
| `general_requirement` | `scope="global_requirement"`、`balloon_required=false`、deterministic requirement classifier evidence |
| `composite` | non-empty、order 从 `0` 连续；primary kind/字段符合本表；`depth` modifier 要求 finite/non-negative `value`，`through` modifier 要求 `value=true`；不得包含 orphan modifier、unknown feature 或 coarse four-field fallback |

所有 family 还必须满足 non-blank raw/normalized text、valid coordinates、唯一且非空
source ownership、明确 boolean `balloon_required`、semantic
`requires_confirmation=false`、coverage clear、no conflict 和 complete source signal。
`CoarseCandidate` 永远没有 high eligibility。

policy 顺序固定：

1. 验证 source ownership 与 signal completeness；
2. 验证 typed schema 与 semantic completeness；
3. 验证 coverage clear；
4. 验证 duplicates/conflicts；
5. 验证 semantic `requires_confirmation` 和 `balloon_required`；
6. 取所有贡献来源的 minimum signal；
7. 按 `0.95 / 0.70` 映射 band 和 disposition；
8. 按 frozen enum order 写 evidence codes。

原 input envelope 不得原地修改。

- [ ] **Step 5: 把 source signals 纳入 snapshot**

扩展 `CandidateSnapshot`：

```python
source_signals: tuple[CandidateSourceSignal, ...] = ()
```

更新本 task 触及的 constructors/`replace()` tests，确保 deterministic JSON-safe
decision；此时还不在 pipeline 调用 policy。

- [ ] **Step 6: 运行 policy tests**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_confidence.py \
  backend/tests/e2e/test_offline_automatic_result.py -q
```

Expected: 全部通过。

- [ ] **Step 7: Commit**

```bash
git add backend/app/candidates/confidence.py \
  backend/app/processing/automatic_result.py \
  backend/tests/fixtures/confidence/candidate-confidence-v1.json \
  backend/tests/unit/candidates/test_confidence.py \
  backend/tests/e2e/test_offline_automatic_result.py
git commit -m "feat: add candidate confidence policy"
```

## Task 3: Route Native, OCR, And Visual Signals Into The Policy

**Files:**

- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/app/processing/runtime_recognition.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/candidates/symbol_review.py`
- Modify: `backend/app/candidates/coverage.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/app/providers/visual_symbol_review.schema.json`
- Modify: `backend/app/providers/qwen_vl.py`
- Delete: `.agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json`
- Create: `.agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v2.json`
- Modify: `.agent/harness/scripts/run-provider-contracts.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Test: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Test: `backend/tests/unit/candidates/test_advisor.py`
- Test: `backend/tests/unit/candidates/test_coverage.py`
- Test: `backend/tests/integration/test_review_working_copy.py`
- Test: `backend/tests/unit/pdf/test_runtime_ocr.py`
- Test: `backend/tests/contract/test_qwen_symbol_provider.py`
- Test: `backend/tests/contract/test_provider_call_records.py`
- Test: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Test: `backend/tests/e2e/test_symbol_recognition.py`
- Test: `backend/tests/contract/harness/test_live_run_contract.py`

- [ ] **Step 1: 写 visual v2 与 source plumbing RED tests**

覆盖：

- `visual-symbol-review/2` detection 必须有 `[0,1] confidence_signal`；
- v2 detection 出现 `requires_confirmation` 被 schema 拒绝；
- missing、`NaN`、负值和 `>1` 被拒绝；
- Qwen adapter 强制 runtime schema version `/2`；
- native observation 产生 deterministic source signal；
- Tencent OCR `TextObservation.confidence` 精确除以 `100`；
- advisor 返回的新 snapshot 保留所有既有 signals；
- visual 多 detection 投影到同 candidate 时采用 minimum signal；
- complete supported projection 不再被无条件标记 confirmation；
- `coverage.py::_valid_visual_semantics()` 接受完整 visual candidate 的
  `requires_confirmation=false`；
- unknown/coarse/conflict projection 仍提交 semantic confirmation/veto。

运行：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/pdf/test_runtime_ocr.py -q
```

Expected: v2/schema/signal tests 失败。

- [ ] **Step 2: Replace active visual Provider schema**

将 `VISUAL_SCHEMA_VERSION` 改为 `visual-symbol-review/2`。在
`visual_symbol_review.schema.json` 中删除 detection 的
`requires_confirmation`，新增：

```json
"confidence_signal": {
  "type": "number",
  "minimum": 0,
  "maximum": 1
}
```

并加入 detection `required`。用 `visual-symbol-review-v2.json` 替换 active Qwen
fixture，并同步 `run-provider-contracts.py` 与 `generate-receipt.py` 的 fixture path；
active Harness 不得再引用 v1 fixture。历史 database call records 不改写。

- [ ] **Step 3: Validate and carry visual signal**

扩展：

```python
@dataclass(frozen=True)
class ValidatedSymbolDetection:
    visual_observation_id: str
    symbol_kind: SymbolKind
    bbox_pdf: BBox
    associated_text_observation_ids: tuple[str, ...]
    confidence_signal: float


@dataclass(frozen=True)
class VisualReviewDecision:
    observation_id: str
    disposition: Disposition
    source_location_ids: tuple[str, ...]
    coordinates: BBox
    candidate_id: str | None
    existing_candidate_index: int | None
    candidate_envelope: dict[str, Any] | None
    requires_confirmation: bool
    symbol_kinds: tuple[SymbolKind, ...]
    rejection_code: str | None
    confidence_signal: float | None
```

`parse_visual_symbol_json()`/`validate_symbol_detections()` 做 finite/range validation。
任何 grouped/merged detection 的 signal 取 minimum。diagnostic safe-member
allowlist 使用 `confidence_signal`，不再接受 Provider 的 confirmation verdict。

- [ ] **Step 4: Retire unconditional projection confirmation**

在 `project_visual_observation()` 和各 supported symbol projector 中：

- complete typed projection 不再写入 `requires_confirmation=true`；
- semantic incomplete、unknown feature、coarse fallback、ambiguous association 或
  projection conflict 仍写 semantic confirmation/veto；
- `CandidateAdvisor.review()` 返回 snapshot 时 append visual source signals，并
  保留 native/OCR signals；
- `coverage.py` 的 active trusted diagnostic schema 改为 `/2`；
- `_valid_visual_semantics()` 不再强制所有 visual candidate confirmation=true，
  但 ambiguous/non-inspection rejection 仍保持人工 confirmation；
- `ReviewService._review_coverage()` 作为 historical reader 接受冻结的 v1
  diagnostic 和 active v2 diagnostic，再剥离 `advisor_review`。这只是 legacy read
  compatibility，不是 v1 runtime writer/readthrough fallback。

- [ ] **Step 5: Populate native and OCR signals**

`candidate_snapshot_from_inventory()` 为每个 selected source location 生成：

- `source_type="native"`：只有 deterministic typed projection 且原 candidate 没有
  semantic confirmation 时为 `1.0`；
- `source_type="ocr"`：调用 `normalize_tencent_ocr_signal()`；
- visual signal 由 advisor append。

不得在 `RuntimeRecognition` 或 frontend 按 `<=1` 猜测 OCR 量纲。

- [ ] **Step 6: Run source/provider regression**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

Expected: 全部通过，active runtime/test fixture 不再写
`visual-symbol-review/1.requires_confirmation`。

- [ ] **Step 7: Verify old path retirement**

```bash
rg -n 'visual-symbol-review/1|\"requires_confirmation\"' \
  backend/app/providers/visual_symbol_review.schema.json \
  backend/app/providers/qwen_vl.py \
  backend/app/candidates/symbol_review.py \
  .agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v2.json \
  .agent/harness/scripts/run-provider-contracts.py \
  .agent/harness/scripts/generate-receipt.py
```

Expected: active Provider response 和 complete visual projection 中无旧 verdict；只允许
明确的 legacy-read test 或 semantic-level candidate confirmation。

- [ ] **Step 8: Commit**

```bash
git add backend/app/processing/automatic_result.py \
  backend/app/processing/runtime_recognition.py \
  backend/app/candidates/advisor.py \
  backend/app/candidates/symbol_review.py \
  backend/app/candidates/coverage.py \
  backend/app/review/service.py \
  backend/app/providers/visual_symbol_review.schema.json \
  backend/app/providers/qwen_vl.py \
  .agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v2.json \
  .agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json \
  .agent/harness/scripts/run-provider-contracts.py \
  .agent/harness/scripts/generate-receipt.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py \
  backend/tests/contract/harness/test_live_run_contract.py
git commit -m "feat: normalize recognition confidence signals"
```

## Task 4: Freeze Confidence Decisions In `AutomaticResult /2`

**Files:**

- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/app/processing/automatic_result.py`
- Test: `backend/tests/e2e/test_offline_automatic_result.py`
- Test: `backend/tests/integration/test_processing_entry_task.py`
- Test: `backend/tests/integration/test_task_idempotency.py`
- Test: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Test: `backend/tests/integration/test_result_layers.py`
- Test: `backend/tests/integration/test_balloon_service.py`
- Test: `backend/tests/integration/test_export_atomicity.py`
- Test: `backend/tests/integration/test_operator_audit.py`
- Test: `backend/tests/integration/test_project_status_api.py`
- Test: `backend/tests/integration/test_review_freeze.py`
- Test: `backend/tests/integration/test_review_operations.py`
- Test: `backend/tests/integration/test_review_version.py`
- Test: `backend/tests/integration/test_review_working_copy.py`

- [ ] **Step 1: 写 pipeline RED tests**

覆盖：

- policy 在 coverage 之后、result build 之前执行；
- mixed high/medium/low candidates 被写入 `/2` decisions；
- candidate-associated coverage ambiguity 阻止 high；
- duplicate/conflict relation 阻止 high；
- policy exception 不留下部分 `AutomaticResult`，job/project 进入现有 structured
  processing failure path；
- unknown policy version 拒绝持久化；
- repeated logical task 返回同一个 frozen result，不重算 decision。

同时审计 `rg -l 'build_automatic_result\\(' backend/tests` 的所有 fixture：

- 测 active processing/result contract 的 fixture 改为 complete `/2` decision；
- 只测试 Review/Balloon/Export legacy behavior 的 fixture 显式传
  `schema_version="automatic-result/1"`，不得依赖 default；
- `test_result_layers.py::_automatic_result()` 必须显式选择其 case 的 `/1` legacy 或
  `/2` complete envelope，不能留下无 decision 的 implicit default。

运行：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/e2e/test_offline_automatic_result.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_balloon_service.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_operator_audit.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_version.py \
  backend/tests/integration/test_review_working_copy.py -q
```

Expected: policy 尚未接入，tests 失败。

- [ ] **Step 2: Inject and call the single policy**

`InventoryPipeline.__init__()` 增加可测试 dependency：

```python
confidence_policy: ConfidencePolicy = ConfidencePolicy()
```

同时把 `AUTOMATIC_RESULT_SCHEMA_VERSION` 切到 `automatic-result/2`，删除
`NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION` 过渡 constant。active production caller
不得再传 `/1`；`/1` 仅保留 persisted legacy reader 和 explicit legacy fixtures。

`run()` 中顺序固定为：

```python
snapshot = self._candidate_snapshot_builder(pages)
coverage = check_coverage(
    snapshot.coverage_entries,
    expected_observation_ids=snapshot.expected_observation_ids,
    required_visual_observation_ids=snapshot.required_visual_observation_ids,
)
decided_candidates = self._confidence_policy.evaluate_candidates(
    candidates=snapshot.candidates,
    coverage=coverage,
    duplicate_relations=snapshot.duplicate_relations,
    source_signals=snapshot.source_signals,
)
automatic_result = build_automatic_result(
    self._session,
    project_id=project.id,
    source_file_id=source_file.id,
    logical_job_id=job.id,
    inventory_ref=inventory_ref,
    candidates=decided_candidates,
    coverage=coverage,
    provider_call_ids=snapshot.provider_call_ids,
    duplicate_relations=snapshot.duplicate_relations,
    schema_version="automatic-result/2",
)
```

policy 不得重读 PDF、调用 Provider、修改 coverage 或创建 balloon。

- [ ] **Step 3: Map failures without partial success**

新增明确 `ConfidencePolicyError`，pipeline 记录：

```text
code=confidence_policy_failed
stage=confidence_policy
cause_category=processing_defect
```

不得把 policy failure 降级为全 pending 后继续成功；这会掩盖 `/2` contract defect。

- [ ] **Step 4: Run pipeline integration**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/e2e/test_offline_automatic_result.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_balloon_service.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_operator_audit.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_version.py \
  backend/tests/integration/test_review_working_copy.py -q
```

Expected: 全部通过；新 result 为 `/2` 且每个 candidate 有 exactly one decision。

- [ ] **Step 5: Commit**

```bash
git add backend/app/processing/pipeline.py \
  backend/app/processing/automatic_result.py \
  backend/tests/e2e/test_offline_automatic_result.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_balloon_service.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_operator_audit.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_version.py \
  backend/tests/integration/test_review_working_copy.py
git commit -m "feat: freeze confidence decisions in automatic results"
```

## Task 5: Bootstrap Exception-Based Review And Backend Workbench Counts

**Files:**

- Modify: `backend/app/review/service.py`
- Modify: `backend/app/projects/router.py`
- Modify: `backend/app/review/router.py`
- Test: `backend/tests/integration/test_review_working_copy.py`
- Test: `backend/tests/integration/test_review_operations.py`
- Test: `backend/tests/integration/test_review_freeze.py`
- Test: `backend/tests/integration/test_result_layers.py`
- Test: `backend/tests/integration/test_operator_audit.py`
- Test: `backend/tests/integration/test_project_workbench_api.py`
- Test: `backend/tests/integration/test_balloon_service.py`
- Test: `backend/tests/integration/test_balloon_validation.py`

- [ ] **Step 1: 写 Review bootstrap 和 override RED tests**

创建 mixed `/2` raw result，断言：

- high → `status="auto_accepted"`、`requires_confirmation=false`、
  `acceptance_source="confidence_policy"`；
- medium/low → `status="pending"`、`requires_confirmation=true`、
  `acceptance_source=null`；
- legacy `/1` missing decision → pending/fail closed；
- legacy `/1` 即使伪造 high-shaped decision 也必须 pending；
- `/2` decision 的 unknown/duplicate/out-of-order evidence code、extra field、错误
  type 或非法 band/disposition pairing 全部 pending；
- high 无需 `keep`/`resolve_confirmation` 即不形成 review blocker；
- high 的 edit/exclude/balloon toggle 改为 `manual_override` 并保留原 decision；
- automatic review-required 的 keep/resolve 改为 `manual_override`；
- add/promote source 使用 `acceptance_source="manual"`；
- merge/split output 使用 `manual_override`，不继承 high decision；
- raw result 不被任何 command 改写；
- numbering stale 与 operation audit 保持。

- [ ] **Step 2: Replace `_current_item()`**

`create_from_raw()` 必须把 `raw_result.schema_version` 显式传给
`_current_item(candidate, raw_schema_version)`。只在 `/2` 且共享 exact validator
通过时消费 immutable decision：

```python
try:
    validated_decision = (
        validate_confidence_decision(decision)
        if raw_schema_version == "automatic-result/2"
        else None
    )
except ConfidenceDecisionContractError:
    validated_decision = None
is_auto_accepted = (
    validated_decision is not None
    and validated_decision.review_disposition == "auto_accepted"
)
if is_auto_accepted:
    status = "auto_accepted"
    requires_confirmation = False
    acceptance_source = "confidence_policy"
else:
    status = "pending"
    requires_confirmation = True
    acceptance_source = None
```

unknown/malformed/missing decision 一律走 pending；Review 不读取 raw score，也不按
item type 放行。`validate_confidence_decision()` 来自唯一
`backend/app/candidates/confidence.py`；Review 不复制 evidence enum/order。validator
抛出的 contract error 在 `_current_item()` 内只转成 fail-closed pending，不让 malformed
legacy data触发 500。

- [ ] **Step 3: Centralize human acceptance provenance**

新增 `_mark_manual_acceptance()`/`_mark_manual_override()` helper，并从
`keep`、`edit`、`exclude`、`resolve_confirmation`、`set_balloon_required`、
`merge`、`split` 调用。规则：

- 已有 automatic decision 的人工语义 action → `manual_override`；
- manual add/promote → `acceptance_source="manual"`、backend status 为 `kept`；
- edit/keep/accepted resolve 是显式完成，不把 item 重置为 pending；
- merge/split 新 item 删除继承的 `confidence_decision`，backend status 为 `kept`；
- exclude 保留 provenance，active=false；
- SIP-only field update 不改变 automatic candidate disposition，但继续由 SIP Owner
  记录确认。

backend status vocabulary 固定为 `auto_accepted / pending / kept / excluded /
superseded`；frontend 只把 `kept` 投影为用户可见的 `confirmed`，不新增第二个 backend
`confirmed` writer。

- [ ] **Step 4: Add one backend-owned `manual_review_count`**

在 `backend/app/review/service.py` 定义共享 pure helper
`manual_review_count(items, coverage)`，由 project/review 两个 serializers 复用，按唯一
target 统计：

```python
review_item_ids = {
    item_id for active item
    if item.get("requires_confirmation") is True
}
source_only_ids = {
    observation_id for coverage entry
    if requires_confirmation is True and candidate_id is None
}
count = len(review_item_ids) + len(source_only_ids)
```

candidate-linked coverage entry 不重复计数。将 count 放进两个 workbench serializers
的 `working_copy.manual_review_count`；`coverage.review_required_count` 仍只统计
coverage entries。

`_project_items()` 同时投影 candidate 的 `confidence_band`、
`review_disposition` 和 `status`，供 overlay 直接消费。

`BalloonService.generate_formal()` 不改 production owner；只添加回归断言，证明 frozen
auto-accepted 与人工确认 items 一起获得唯一、连续 formal numbers，且
`manual_required`/collision 仍由既有 validator 阻断。

- [ ] **Step 5: Run Review/workbench regression**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_operator_audit.py \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_balloon_service.py \
  backend/tests/integration/test_balloon_validation.py -q
```

Expected: mixed confidence、legacy、override、deduplicated count、freeze/SIP blockers
全部通过。

- [ ] **Step 6: Commit**

```bash
git add backend/app/review/service.py \
  backend/app/projects/router.py \
  backend/app/review/router.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_operator_audit.py \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_balloon_service.py \
  backend/tests/integration/test_balloon_validation.py
git commit -m "feat: route only confidence exceptions to review"
```

## Task 6: Render Auto-Accepted Red Markers And Default Exception Queue

**Files:**

- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/candidateNumbering.ts`
- Modify: `frontend/src/components/pdf/OverlayLayer.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.tsx`
- Modify: `frontend/src/components/workbench/inspectionItemPresentation.ts`
- Modify: `frontend/src/components/workbench/RecognitionSummary.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`
- Test: `frontend/src/components/pdf/OverlayLayer.test.tsx`
- Test: `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- Test: `frontend/src/components/workbench/candidateNumbering.test.ts`
- Test: `frontend/src/components/workbench/inspectionItemPresentation.test.ts`
- Test: `frontend/src/components/workbench/RecognitionSummary.test.tsx`
- Test: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Test: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Test: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Test: `frontend/src/components/review/ReviewPanel.test.tsx`

- [ ] **Step 1: 写 frontend RED tests**

覆盖：

- `auto_accepted` item presentation 状态文本；
- provisional auto marker 使用红色空心样式，selected 仍为红色实心高对比；
- aria label 为 `自动通过气泡 {number}，待统一编号`，不能称为正式气泡；
- backend Balloon row 仍使用 `正式气泡 {number}`；
- medium/low 显示 `中置信度/低置信度` badge 和 evidence summary；
- summary 独立显示 auto-accepted count、backend `manual_review_count`、
  placement `manual_required` 和 collision count；
- 默认 filter 为 `review_required`；
- high 不在默认人工队列，但在全部 filter 可选中并编辑；
- unknown status/band 按待审核显示，不自动变红；
- selection identity、dirty-selection guard、retry behavior 不退化。

运行：

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/pdf/OverlayLayer.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/candidateNumbering.test.ts \
  src/components/workbench/inspectionItemPresentation.test.ts \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/ProjectWorkbenchApp.test.tsx \
  src/components/review/ReviewPanel.test.tsx
```

Expected: 新 status、count、style 和 filter tests 失败。

- [ ] **Step 2: Add additive API types**

```ts
export type ConfidenceBand = "high" | "medium" | "low";
export type ReviewDisposition = "auto_accepted" | "review_required";

export type ConfidenceDecision = {
  band: ConfidenceBand;
  review_disposition: ReviewDisposition;
  policy_version: "candidate-confidence/1";
  evidence_codes: string[];
};
```

`ReviewItem` 增加 `confidence_decision?`、`acceptance_source?`；
`ReviewWorkingCopy` 增加 `manual_review_count`；`ProjectWorkbenchCandidate`/
`OverlayBox` 增加 backend 投影的 band、disposition 和 status。unknown/missing fields
不得被 frontend 推断成 high。

- [ ] **Step 3: Render red provisional auto marker**

`ProjectWorkbenchApp.tsx` 原样传递 backend status/disposition。
`OverlayLayer.tsx` 仅在：

```ts
item.reviewDisposition === "auto_accepted"
&& item.status === "auto_accepted"
```

时使用 `#c23b3b` 红色系：

- unselected：白/透明 fill + 红 stroke；
- selected：红 fill + 白 text；
- blue candidate style 保留给 review-required candidate；
- backend `BalloonOverlay` 的 formal style/label 保持现有 Owner。

- [ ] **Step 4: Separate review and placement filters**

`InspectionFilter` 增加 `auto_accepted`、`review_required`；保留
`manual_required` 仅表示 placement。`RecognitionSummary`：

- auto count 从 backend item status/disposition 计数；
- review count 只显示 `working_copy.manual_review_count`；
- 不把 `pendingSourceCount` 加到 placement manual count；
- “全部”保持所有 editable items/source；
- workbench 初始 filter 改为 `review_required`。

`InspectionItemTable` 对 unknown/missing confidence fail closed 到 review filter。
`ReviewPanel` 在 selected item heading 附近只读显示 band、policy version 和 ordered
evidence summary，不提供修改 policy/band 的 input。

- [ ] **Step 5: Add non-color copy and legend**

`zhCN.ts` 增加：

```text
自动通过
待人工审核
高置信度
中置信度
低置信度
自动通过，待统一编号
正式气泡
自动通过气泡 {number}，待统一编号
```

CSS legend 使用同一红 hue 的 hollow/solid 区分，summary grid 响应新增 chips，不隐藏
existing collision/placement states。

- [ ] **Step 6: Run frontend tests and build**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/pdf/OverlayLayer.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/candidateNumbering.test.ts \
  src/components/workbench/inspectionItemPresentation.test.ts \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/ProjectWorkbenchApp.test.tsx \
  src/components/review/ReviewPanel.test.tsx
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: tests 和 production build 全部通过，无 TypeScript errors。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts \
  frontend/src/components/workbench/ProjectWorkbenchApp.tsx \
  frontend/src/components/workbench/candidateNumbering.ts \
  frontend/src/components/pdf/OverlayLayer.tsx \
  frontend/src/components/pdf/PdfWorkspace.tsx \
  frontend/src/components/workbench/inspectionItemPresentation.ts \
  frontend/src/components/workbench/RecognitionSummary.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css \
  frontend/src/components/pdf/OverlayLayer.test.tsx \
  frontend/src/components/pdf/PdfWorkspace.test.tsx \
  frontend/src/components/workbench/candidateNumbering.test.ts \
  frontend/src/components/workbench/inspectionItemPresentation.test.ts \
  frontend/src/components/workbench/RecognitionSummary.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx
git commit -m "feat: show auto-accepted balloon candidates"
```

## Task 7: Preserve Confidence Provenance In Export Manifest

**Files:**

- Modify: `backend/app/exports/manifest.py`
- Modify: `backend/app/exports/service.py`
- Test: `backend/tests/unit/exports/test_manifest.py`
- Test: `backend/tests/integration/test_export_consistency.py`
- Test: `backend/tests/integration/test_export_atomicity.py`
- Test: `backend/tests/integration/test_export_preflight.py`

- [ ] **Step 1: 写 manifest `/2` RED tests**

断言：

- schema version 为 `export-manifest/2`；
- `confidence_policy_versions` 去重、排序、deterministic；
- `auto_accepted_item_count` 只统计 active
  `acceptance_source="confidence_policy"`；
- `manual_override_item_count` 只统计 active
  `acceptance_source="manual_override"`；
- excluded/superseded 不计 active counts；
- legacy-only result 的 policy versions 为空；
- confidence provenance 不进入 SIP business columns；
- PDF、Excel、manifest 继续引用同一 `reviewed_result_id`。

运行：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_manifest.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py -q
```

Expected: `/2` fields 不存在，tests 失败。

- [ ] **Step 2: Extend manifest model and service**

```python
MANIFEST_SCHEMA_VERSION = "export-manifest/2"

@dataclass(frozen=True)
class ExportManifest:
    schema_version: str
    export_id: str
    project_id: str
    reviewed_result_id: str
    input_pdf_sha256: str
    template_id: str
    template_version: str
    template_sha256: str
    mapping_version: str
    font_sha256: str
    renderer_version: str
    reviewed_item_count: int
    balloon_required_count: int
    balloon_count: int
    source_page_count: int
    confidence_policy_versions: tuple[str, ...]
    auto_accepted_item_count: int
    manual_override_item_count: int
    artifacts: tuple[ArtifactDigest, ...]
```

`ExportService._manifest()` 只从 immutable `reviewed.items` 计算，不回查 Provider、
working copy 或 frontend state。现有 `sort_keys=True` deterministic bytes 保持。

- [ ] **Step 3: Run export regression**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_manifest.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py -q
```

Expected: 全部通过，atomic publish/cleanup tests 不退化。

- [ ] **Step 4: Commit**

```bash
git add backend/app/exports/manifest.py \
  backend/app/exports/service.py \
  backend/tests/unit/exports/test_manifest.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_preflight.py
git commit -m "feat: export confidence review provenance"
```

## Task 8: Cross-Layer Verification, Browser Proof, And Independent Review

**Files:**

- Modify: `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`
- Modify: `frontend/e2e/p0-workbench.spec.ts`
- Create: `frontend/e2e/confidence-routed-review.spec.ts`

- [ ] **Step 1: Add cross-layer E2E assertions**

使用 existing upload/workbench helpers 覆盖：

1. mixed high/medium/low result；
2. high 无需 click 即显示 red provisional marker；
3. 默认 queue 只展示 review-required targets；
4. red marker → table row → detail form 使用同一 `item_id`；
5. edit high 后 refresh，`manual_override` 持久化；
6. 解决 manual queue 和独立 SIP blockers 后 freeze；
7. formal numbering 对 auto/manual items 连续；
8. freeze 后 marker 由 backend Balloon projection 接管；
9. `manual_required`/collision 仍阻止 final confirm；
10. export 三产物 identity 一致。

`chinese-pdf-upload-mvp.spec.ts` 当前遍历并确认所有 active items；删除这个旧“全量人工
审核”假设，改为只处理 backend `review_required` targets。focused confidence flow
写入 `confidence-routed-review.spec.ts`，避免用旧 spec 的宽泛 assertions 掩盖新语义。

- [ ] **Step 2: Run full automated verification**

```bash
micromamba run -n qi-p0 pytest backend/tests -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e:list
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py
```

Expected: backend、frontend、build、E2E discovery、contract checks 全部通过。

- [ ] **Step 3: Run production-entry browser verification**

启动：

```bash
make dev-local-api
make dev-local-frontend
```

两个 long-lived commands 分别在独立 terminal/process 运行；确认 API 与 frontend
health 后再启动 Chrome MCP/Playwright，不在同一 blocking shell 串行执行。

使用 Chrome MCP 在 `http://127.0.0.1:5173` 执行 approved spec 的 Browser 七步。
必须使用真实 PDF/current source-mounted runtime，不用 synthetic screenshot 或旧
receipt 冒充。记录：

- no per-item click 的 high red marker；
- medium/low exception queue；
- refresh 后 manual override；
- freeze 前 provisional label；
- freeze 后 formal number；
- collision/manual-required veto；
- PDF/SIP/manifest 同一 `reviewed_result_id`。

若 runtime/provider 无法产生已批准 high fixture，browser verdict 必须是 blocked，
不得通过前端 mock claim 完成。

运行 focused Playwright：

```bash
test -n "${QI_MVP_E2E_PDF:-}"
micromamba run -n qi-p0 npm --prefix frontend run e2e -- \
  confidence-routed-review.spec.ts
```

Expected: `QI_MVP_E2E_PDF` 必须由当前 approved real PDF runtime 提供；缺失时命令在
测试前失败并报告真实 blocker。

- [ ] **Step 4: Use `auto-feature-smoke-test`**

按 skill 对实现后的主用户流做一次 bounded smoke。若 skill 的 runtime assumptions 与
本 repo 的 `make dev-local-*` 冲突，以 repo commands 为准并记录原因。

- [ ] **Step 5: Request independent reviewer**

reviewer 必须只读，检查：

- `ConfidencePolicy` 是否真是唯一 disposition writer；
- old Provider/projection/all-pending/frontend inference paths 是否退役；
- tests 是否覆盖真实 failure mode，而非只测 happy path；
- legacy、unknown、invalid signal 是否 fail closed；
- human override 是否保留 immutable raw decision；
- SIP、formal numbering、collision/manual-required、export owners 未被绕过；
- no dual writer、shadow path、runtime flag 或 silent fallback。

Reviewer 输出必须有 verdict、blocking issues、non-blocking concerns、文件/测试证据和
minimal follow-up。父 agent 必须逐条复核 blocking claims。

- [ ] **Step 6: Inspect exact diff and old-path search**

```bash
git diff --check
git status --short
rg -n 'visual-symbol-review/1|status\": \"pending\"|status=\"pending\"' \
  backend/app frontend/src
rg -n 'auto_accepted|candidate-confidence/1|manual_review_count' \
  backend/app frontend/src
```

Expected:

- no whitespace errors；
- unrelated dirty files 保持未 staged；
- legacy `/1` 仅出现在 explicit read/test compatibility；
- Review 不再对所有 candidates 无条件 pending；
- frontend 不自行计算 confidence band。

- [ ] **Step 7: Commit E2E evidence code**

```bash
git add frontend/e2e/chinese-pdf-upload-mvp.spec.ts \
  frontend/e2e/p0-workbench.spec.ts \
  frontend/e2e/confidence-routed-review.spec.ts
git commit -m "test: verify confidence-routed review flow"
```

若 Harness 生成新 receipt，单独 exact-stage receipt files 并使用独立 commit；不得 stage
`.local/`、credentials、cookies、provider secrets 或 unrelated existing artifacts。

## Rollback

按 task commit 逆序 revert，但必须先停止新 processing submissions，并等待 active
logical tasks 到终态。

Rollback constraints：

- 不删除或改写已有 `AutomaticResult /2`、working copy、`ReviewedResult` 或 export；
- reader 必须继续安全读取 `/2` provenance；不能安全读取时 rollback verdict 为
  blocked，采用 forward-fix compatible reader；
- working copy 不得把 `auto_accepted/manual_override` 静默改回 pending；
- 不恢复 `visual-symbol-review/1` active writer、all-pending bootstrap、shadow
  scorer、runtime feature flag 或 frontend confidence calculator；
- rollback 后先验证 `/1` legacy 全部 fail closed，再验证 formal numbering、
  collision veto 和 atomic export baseline。

## Completion Contract

只有同时满足以下条件才可 claim complete：

- [ ] high item 无需逐条 command 即进入正式候选集；
- [ ] freeze 前 high item 是红色、可编辑、非 formal 的 provisional marker；
- [ ] medium/low、legacy 和 source-only ambiguity 才进入 manual queue；
- [ ] Provider 只提供 signal，唯一 policy 提交 disposition；
- [ ] legacy/unknown/invalid paths 全部 fail closed；
- [ ] manual override 保存原 decision，raw result 保持 immutable；
- [ ] `manual_review_count` 不重复计算 candidate-linked coverage；
- [ ] SIP、freeze、formal numbering、placement/collision 和 export blockers 未改变；
- [ ] manifest `/2` 保存 policy/acceptance provenance；
- [ ] focused、full suite、build、contract checks、browser proof 实际运行；
- [ ] independent reviewer 无 blocking issue；
- [ ] final diff 只包含本 feature 文件，相关 commits 已创建。
