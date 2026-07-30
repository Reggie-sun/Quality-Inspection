# P0-A1-R1 Region-Aware Standalone Number Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用保守页面区域证据替代全局裸数字降级，使图纸主体裸数字恢复 deterministic candidate，同时继续拦截页框页码和标题栏数值噪声。

**Architecture:** `app.candidates.disposition` 继续是 primary disposition 的唯一 Owner。规则只读取 immutable `TextObservation.bbox_normalized`：极窄页框边缘的裸数字直接判为 `non_inspection`，右下标题栏区域的裸数字保留为 `ambiguous`，图纸主体裸数字不再被 primary gate 捕获，继续进入现有 parser；所有结果仍写入 Coverage Ledger。

**Tech Stack:** Python 3.12、dataclass、pytest、PyMuPDF、现有 `qi-p0` Micromamba 环境

---

## Execution Record

- Lane: `Heavy`
- Selected task: `P0-A1-R1`
- Selection evidence: 用户在 current-four 真实回归结果后明确选择“区域化修正”。
- Worktree: `.worktrees/p0-a1-real-pdf-regression`
- Branch: `codex/p0-a1-real-pdf-regression`
- Base: `main@39c71a9`
- Baseline: candidate/PDF/contract focused suite `314 passed in 1.67s`
- Single writer: 主线程
- Reviewer: 独立只读 reviewer

## Problem Boundary

P0-A1 将所有没有 deterministic visual association 的裸数字降为 `ambiguous`。current-four 六页真实输入的只读回归显示：

- pre-P0-A1 automatic candidates: `521`
- P0-A1 deterministic candidates: `349`
- 移出 candidate 的裸数字: `172`
- 其中 ReviewedResult proxy 后续保留为正例: `118`
- candidate precision proxy: `78.5% → 83.4%`
- candidate recall proxy: `100% → 71.1%`
- 自动 `non_inspection`: `37`，全部属于用户明确列出的 metadata / scale / section label 类别，且与 proxy 正例交集为 `0`

这些 `118` 个 observation 没有丢失，仍在 Coverage 中，但需要人工从 `ambiguous` 提升，人工成本不符合 P0-A1 的止血目标。

## Decision Boundary

从 reviewed proxy 的 172 个裸数字样本得到的保守区域：

```text
page frame:
  center_y <= 0.02 or center_y >= 0.98
  proxy: 22 negative / 0 positive

title block:
  center_x >= 0.65 and center_y >= 0.82
  page-frame 去重后 proxy: 19 negative / 0 positive

drawing body:
  其余裸数字恢复 parser
```

阈值是 current-four 的 P0 经验边界，不提升为长期稳定 PDF contract。`page_frame_number` 可直接 `non_inspection`；`title_block_number` 只判 `ambiguous`，避免把未来版式差异转换为不可逆排除。

## Unchanged Contracts

- `parse_annotation("25")` 保持合法并继续由 parser Owner 解释。
- exact metadata、scale、section label 仍为 `non_inspection`。
- standalone Roman label 仍为 `ambiguous`。
- visual-associated number 继续绕过 context-free number gate。
- observation identity、bbox、Coverage identity 与 source lineage 不改变。
- 本任务不调用 Provider，不创建 VLM suggestion，不改变 reviewed result、formal number、balloon placement 或 export。
- ReviewedResult proxy 只用于诊断人工修正成本，不冒充 Quality Owner 完整 ground truth。

## Rollback

只 revert 本任务实现 commit。回滚后运行 focused regression，预期恢复 P0-A1 的全局 `standalone_number → ambiguous` 行为；不得回滚 P0-A1 的 metadata/scale/section/repeated-text 修复。

## Task 1: Freeze Region-Aware Number Semantics

**Files:**

- Modify: `backend/tests/unit/candidates/test_disposition.py`
- Modify: `backend/app/candidates/disposition.py`

- [x] **Step 1: Write failing unit tests**

增加以下精确行为：

```python
def test_body_standalone_number_yields_to_parser() -> None:
    observation = _observation(
        "25",
        bbox_normalized=(0.40, 0.40, 0.44, 0.42),
    )
    assert classify_primary_disposition(observation) is None


@pytest.mark.parametrize(
    "bbox_normalized",
    [
        (0.24, 0.00, 0.26, 0.015),
        (0.74, 0.985, 0.76, 1.00),
    ],
)
def test_page_frame_number_is_non_inspection(bbox_normalized) -> None:
    decision = classify_primary_disposition(
        _observation("1", bbox_normalized=bbox_normalized)
    )
    assert decision is not None
    assert decision.disposition == "non_inspection"
    assert decision.reason == "page_frame_number"
    assert decision.requires_confirmation is False


def test_title_block_number_remains_reviewable() -> None:
    decision = classify_primary_disposition(
        _observation(
            "260710",
            bbox_normalized=(0.70, 0.83, 0.76, 0.86),
        )
    )
    assert decision is not None
    assert decision.disposition == "ambiguous"
    assert decision.reason == "title_block_number"
    assert decision.requires_confirmation is True
```

同时验证 `has_visual_context=True` 会让 page-frame/title-block number 返回 `None`，且 metadata/scale/section 不受该例外影响。

- [x] **Step 2: Run unit tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q tests/unit/candidates/test_disposition.py
```

Expected: body number 仍返回 `standalone_number`，新区域 reason 不存在。

- [x] **Step 3: Implement the minimum region helper**

在 `backend/app/candidates/disposition.py` 增加：

```python
PRIMARY_DISPOSITION_RULE_VERSION = "p0-a1-r1"
PAGE_FRAME_EDGE_RATIO = 0.02
TITLE_BLOCK_MIN_X = 0.65
TITLE_BLOCK_MIN_Y = 0.82


def _bbox_center(
    bbox_normalized: tuple[float, float, float, float],
) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox_normalized
    return (x0 + x1) / 2, (y0 + y1) / 2


def _standalone_number_region(
    observation: TextObservation,
) -> Literal["page_frame", "title_block"] | None:
    center_x, center_y = _bbox_center(observation.bbox_normalized)
    if (
        center_y <= PAGE_FRAME_EDGE_RATIO
        or center_y >= 1.0 - PAGE_FRAME_EDGE_RATIO
    ):
        return "page_frame"
    if center_x >= TITLE_BLOCK_MIN_X and center_y >= TITLE_BLOCK_MIN_Y:
        return "title_block"
    return None
```

在 `STANDALONE_NUMBER` 分支中：

1. `has_visual_context` 时返回 `None`。
2. `page_frame` 返回 `non_inspection / page_frame_number`。
3. `title_block` 返回 `ambiguous / title_block_number / requires_confirmation=true`。
4. drawing body 返回 `None`，交回现有 parser。

- [x] **Step 4: Run unit tests and verify GREEN**

Run Step 2 command. Expected: all pass.

- [x] **Step 5: Commit Task 1**

```bash
git add backend/app/candidates/disposition.py \
  backend/tests/unit/candidates/test_disposition.py
git commit -m "fix: scope standalone number noise by drawing region"
```

## Task 2: Freeze Candidate Snapshot Behavior

**Files:**

- Modify: `backend/tests/e2e/test_offline_automatic_result.py`

- [x] **Step 1: Write failing snapshot tests**

覆盖：

```text
body 25
  -> one linear_dimension candidate
  -> candidate coverage

page-frame 1
  -> no candidate
  -> non_inspection / page_frame_number

title-block 260710
  -> no candidate
  -> ambiguous / title_block_number / requires_confirmation

visual-associated page-frame 1
  -> provisional candidate path remains available
```

同时把 rule-version assertions 更新为 `p0-a1-r1`。

- [x] **Step 2: Run snapshot tests and verify RED**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q \
  tests/unit/candidates/test_disposition.py \
  tests/e2e/test_offline_automatic_result.py
```

Expected: 新 snapshot expectations 在生产实现修改前失败。

- [x] **Step 3: Complete the minimum integration**

若 Task 1 的 pure Owner 修改已经满足 snapshot contract，不修改 `automatic_result.py`。只有发现已验证的调用链缺口时才通过新的 RED/GREEN 修改该文件。

- [x] **Step 4: Run snapshot tests and verify GREEN**

Run Step 2 command. Expected: all pass.

- [x] **Step 5: Commit Task 2**

```bash
git add backend/tests/e2e/test_offline_automatic_result.py
git commit -m "test: cover region-aware candidate noise routing"
```

## Task 3: Current-Four Regression and Independent Review

**Files:**

- Modify: `docs/superpowers/plans/2026-07-30-p0-a1-r1-region-aware-standalone-number.md`
- Verify only: production/test files

- [x] **Step 1: Run the focused candidate/PDF/contract suite**

Run from `backend/`:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 \
  python -m pytest -q \
  tests/unit/candidates/test_parser.py \
  tests/unit/candidates/test_grouping.py \
  tests/unit/candidates/test_disposition.py \
  tests/unit/candidates/test_coverage.py \
  tests/unit/candidates/test_confidence.py \
  tests/unit/candidates/test_advisor.py \
  tests/unit/pdf/test_coordinates.py \
  tests/unit/pdf/test_runtime_ocr.py \
  tests/contract/test_automatic_result.py \
  tests/contract/test_qwen_vl_provider.py
```

Expected: baseline `314 passed` plus新增测试全部通过。

- [x] **Step 2: Run deterministic current-four regression**

只读取 hash-verified current-four source，执行：

```text
build_inventory()
→ candidate_snapshot_from_inventory()
→ compare source IDs against the frozen pre-P0-A1 AutomaticResult
→ separately compare against confirmed ReviewedResult proxy
```

不得调用 `RuntimeRecognition` OCR provider、`CandidateAdvisor` 或外部网络。报告必须至少包含：

- per-document candidate / ambiguous / non_inspection counts
- reason counts
- exact metadata/scale/section candidate leakage
- page-frame/title-block/body standalone number counts
- old/new proxy TP/FP/FN、precision、recall
- automatic result与reviewed proxy的边界说明

Expected narrow gate:

```text
all current-four exact metadata/scale/section labels:
  candidate leakage = 0

all auto non_inspection decisions:
  reviewed-positive intersection = 0

region-aware standalone number:
  reviewed-positive moved to ambiguous = 0
  candidate recall proxy = 1.0
```

不预先固定 precision 的提高幅度；真实结果必须原样记录。

- [x] **Step 3: Verify repeat determinism**

在相同 code/input 下重复执行 Step 2，比较 canonical aggregate JSON。Expected: byte-identical。

- [x] **Step 4: Run independent read-only review**

Reviewer 必须给出 `accept / accept with concerns / reject`，重点检查：

- region helper 是否只影响 standalone number
- title block 是否保持 `ambiguous` 而非不可逆排除
- body number 是否恢复现有 parser
- visual context exception 是否保留
- exact metadata/scale/section 是否没有回归
- 是否误把 ReviewedResult proxy 宣称为正式 ground truth

- [x] **Step 5: Record results and commit evidence**

把实际 commands、metrics、review verdict、remaining risks 写入本计划 `Execution Results`，然后：

```bash
git add docs/superpowers/plans/2026-07-30-p0-a1-r1-region-aware-standalone-number.md
git commit -m "docs: record P0-A1-R1 real PDF regression"
```

## Acceptance Evidence

必须分开报告：

- Automatic capability:
  - deterministic prefilter 的 candidate/disposition 指标
  - 不包含人工修改后的结果
- Human correction cost:
  - ReviewedResult proxy 只用于估算从 automatic 到 reviewed 的 correction burden
  - proxy 未获 Quality Owner 完整 item-level 标注前，不称为正式 ground truth
- Final delivery correctness:
  - 本任务不声明 reviewed result、formal balloon、PDF、Excel 或 manifest 正确率提高
  - 未运行 post-Advisor live path 时，不声明 VLM 不会重新引入噪声

## Remaining Boundary

- repeated `伟立机器人`、更改栏和技术要求 block 仍可能为 `ambiguous`。
- 完整 candidate precision/recall 仍需要 Quality Owner 对 current-four 的 item/group ground truth。
- P0-B grouping/disposition 和局部 VLM Advisor 不在本任务范围。

## Execution Results

### RED / GREEN

- Unit RED:
  - command: `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python -m pytest -q tests/unit/candidates/test_disposition.py`
  - result: `4 failed, 36 passed`
  - failures精确证明 body number、page-frame number 和 title-block number 仍走旧 `standalone_number` 全局 gate。
- Unit GREEN:
  - same command
  - result: `40 passed`
- Boundary follow-up:
  - exact/just-outside page-frame 和 title-block thresholds、bottom-right precedence、Native/OCR canonical bbox consumer parity 已补测试。
  - disposition unit file: `50 passed`
  - reviewer focused PDF/disposition selection: `75 passed`
- Snapshot integration:
  - snapshot tests在 pure Owner 已完成 GREEN 后加入，因此没有伪造第二次 RED。
  - pure snapshot selection: `52 passed, 23 deselected`
  - 第一次运行完整 `test_offline_automatic_result.py` 时，前 `65` 个 pure tests 已通过，后 `10` 个 DB tests 因宿主机无法解析 Compose-only hostname `postgres` 而 setup error。
  - 使用独立临时 PostgreSQL、migration `0007 (head)` 复跑完整文件：`35 passed`。

### Focused and Full Verification

- focused candidate/PDF/contract suite: `320 passed in 1.74s`
- implementation full backend suite: `995 passed, 1 warning in 43.32s`
- boundary-test follow-up 后使用另一全新 PostgreSQL、migration head 复跑：`1005 passed, 1 warning in 41.94s`
- warning: pre-existing Starlette/httpx deprecation warning
- 三个显式临时 PostgreSQL containers 均已删除。

### Current-Four Deterministic Regression

输入 identity：

| order | source SHA-256 |
|---|---|
| 1 | `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec` |
| 2 | `ffee22f2e392f309d3d0acfc2edadc4a8d5330a9bc28009263af5d8597074a86` |
| 3 | `322d56b00456f495830386b8dc50a32e34086a5bc66d4735e2c3c735d5fbc57d` |
| 4 | `8fffd93fa7f055f9fe1a7da25bc85630910bdfc2ea86b2ace6ec54979f0a515e` |

只读路径：

```text
hash-verified PDF
→ build_inventory()
→ candidate_snapshot_from_inventory()
→ deterministic report
```

没有调用 OCR Provider、CandidateAdvisor 或外部网络；数据库只用于读取冻结的 historical AutomaticResult 和 confirmed ReviewedResult proxy。

| PDF | candidates | ambiguous text | non_inspection text | proxy precision | proxy recall |
|---|---:|---:|---:|---:|---:|
| 1 | 255 | 159 | 25 | 92.5% | 100% |
| 2 | 25 | 50 | 8 | 56.0% | 100% |
| 3 | 57 | 59 | 7 | 84.2% | 100% |
| 4 | 143 | 143 | 19 | 77.6% | 100% |
| total | 480 | 411 | 59 | 85.2% | 100% |

Aggregate comparison：

| metric | pre-P0-A1 | P0-A1 global number gate | P0-A1-R1 |
|---|---:|---:|---:|
| candidates | 521 | 349 | 480 |
| precision proxy | 78.5% | 83.4% | 85.2% |
| recall proxy | 100% | 71.1% | 100% |
| reviewed-positive moved to ambiguous | 0 | 118 | 0 |
| reviewed-positive marked non_inspection | 0 | 0 | 0 |

R1 相对 pre-P0-A1 移除 `41` 个 candidate，全部为 proxy negative：

- `page_frame_number`: `22`，直接 `non_inspection`
- `title_block_number`: `19`，保守保留为 `ambiguous`
- exact metadata / scale / section: `37`，candidate leakage `0`
- total automatic `non_inspection`: `59`，与 ReviewedResult proxy 正例交集 `0`

相同 code/input 连续执行两次的 canonical JSON byte-identical，SHA-256：

`1d8c2be91dcbcae476feaf7b4a6c92a2fb04394047f2f2dcd25462cdd06f94e1`

### Evidence Boundary

- 上述 precision/recall 是 ReviewedResult source-relation proxy，不是 Quality Owner 完整 item/group ground truth。
- 区域阈值选择与指标报告使用同一 current-four cohort，因此这些数字属于 in-sample diagnostic，不能外推为独立泛化证明；推广前需要固定 blind/holdout PDF cohort。
- 自动指标没有混入本轮人工修改；历史 ReviewedResult 只用于估算 correction burden。
- 当前回归只证明 deterministic prefilter。Advisor 仍可能消费部分 `ambiguous`，因此不能据此宣称 post-Advisor 或正式交付 precision。
- 本任务没有运行 reviewed result、formal balloon、PDF、Excel 或 manifest 发布验证。

### Independent Review

- initial verdict: `accept with concerns`
  - 无 blocking issue。
  - concern 为 current-four 阈值与 proxy 指标同 cohort，以及 exact boundary / OCR source-type 测试尚未锁定。
- follow-up commit: `9e4844f test: lock candidate noise region boundaries`
  - 只修改测试，不改变 production、schema、Owner、Coverage 或 lineage。
  - 补齐 top/bottom exact 与 just-outside、title exact 与 just-outside、bottom-right page-frame precedence、Native/OCR source-type parity。
- final verdict: `accept`
  - reviewer focused verification: `75 passed in 0.78s`
  - 剩余风险仅为上述 in-sample evidence boundary 与尚未执行的 blind/holdout、post-Advisor 和正式交付验证。
