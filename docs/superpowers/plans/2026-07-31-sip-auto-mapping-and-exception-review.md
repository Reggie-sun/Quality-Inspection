# SIP Auto-Mapping And Exception Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已审核的 active 检验项一次性生成可导出的 SIP 表格，只让无法确定的行进入人工异常处理。

**Architecture:** `ReviewService` 继续唯一拥有正式 item set；新建纯函数
`sip_mapping.py`，只消费结构化 item 和项目默认检验角色，输出 resolved SIP fields、
provenance 和 exception codes。一个 versioned `generate_sip_table` command 在单事务内
应用全部结果；frontend 只展示 ready/exception 派生状态，不重算映射规则。

**Tech Stack:** Python 3.11、Pydantic、FastAPI、SQLAlchemy、pytest、OpenAPI snapshot、
TypeScript、React、Vitest、Chrome DevTools、Micromamba `qi-p0`

## Global Constraints

- Selected lane: `Heavy`。
- Current plan: 本文件是该用户目标唯一 current implementation plan；已完成的
  `2026-07-31-title-block-sip-prefill-and-confirmation-guidance.md` 只作为既有
  baseline，不再拥有“逐项确认 SIP”流程。
- Problem boundary: 只改变
  `active reviewed item -> resolved SIP fields or explicit exception`。
- Single Owner: item membership 仍由 `ReviewService` lifecycle 拥有；SIP field
  mapping 只由 `backend/app/review/sip_mapping.py` 拥有。
- Old path action: “逐项确认后才可导出”执行 `replace`；`set_sip_detail_fields`
  执行 `preserve`，只服务人工异常覆盖；`active` formal set、freeze、ReviewedResult、
  balloons、fixed Excel 和 manifest identity 执行 `preserve`。
- No fabricated results: 自动生成计划字段，不生成测量值或检验结果。
- No automatic merge: 相同文字但 source identity 不同的 items 保持独立。
- No hidden migration: historical `ReviewedResult` 不回写；existing working copy 只在用户
  执行 `generate_sip_table` 时显式写入。
- Single writer: 主线程按 Task 1 → Task 4 串行修改；已有 explorer/auditor/reviewer
  均已完成且保持只读。
- TDD: 每个 production behavior 先运行对应 RED，再写最小实现。
- Git: 只 stage 本 plan 的 allowed paths；不得 stage `.pyc`、Harness runs、
  `index.json` 或其他现有 dirty files。
- Rollback: 按 task commit 逆序 revert。rollback 后第一项验证是
  `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_review_freeze.py -q`，
  证明旧 confirmation gate 完整恢复。

## Status

- Date: `2026-07-31`
- Status: `approved / in progress`
- Design source:
  `docs/superpowers/specs/2026-07-31-sip-auto-mapping-and-exception-review-design.md`
- Selection evidence: 用户批准“检验项只审核一次，SIP 自动映射，仅异常人工处理”，
  并在开源对标后回复“可以”批准 template/materialize + exception-only 流程。
- Validation action: `continue`
- Writer ownership and order: parent/main thread，Task 1 → Task 4；无并发 writer。
- Next verification: Task 2 integration RED。

## Allowed Paths

- `backend/app/review/sip_mapping.py`
- `backend/app/review/schemas.py`
- `backend/app/review/service.py`
- `backend/tests/unit/review/test_sip_mapping.py`
- `backend/tests/integration/test_review_operations.py`
- `backend/tests/integration/test_review_freeze.py`
- `backend/tests/contract/test_openapi_contract.py`
- `backend/tests/contract/snapshots/api-v1.openapi.json`
- `frontend/src/api/generated.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/components/workbench/SipInformationPanel.tsx`
- `frontend/src/components/workbench/SipInformationPanel.test.tsx`
- `frontend/src/components/workbench/SelectedSipDetailFields.tsx`
- `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
- `frontend/src/components/workbench/ExportPanel.tsx`
- `frontend/src/components/workbench/ExportPanel.test.tsx`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/styles/workbench.css`
- `docs/operations/sip-confirmation-demo/**`
- 本 design spec 和本 plan

---

### Task 1: Deterministic SIP Mapping Owner

**Files:**
- Create: `backend/app/review/sip_mapping.py`
- Create: `backend/tests/unit/review/test_sip_mapping.py`

**Interfaces:**
- Consumes:
  `map_sip_item(item: dict[str, Any], *, inspection_role: str)`.
- Produces:
  `SipMappingResult(fields: dict[str, object], provenance: dict[str, str], exceptions: tuple[str, ...])`.
- Stable rule version: `sip-auto-map/1`.
- Exception codes:
  `missing_inspection_role`, `unsupported_item_type`,
  `composite_method_required`, `missing_source_page`.

- [x] **Step 1: Write the failing mapping tests**

Create table-driven literals for:

```python
assert map_sip_item(
    {
        "item_id": "linear-1",
        "item_type": "linear_dimension",
        "normalized_text": "35",
        "quantity": 2,
        "page_index": 0,
    },
    inspection_role="IPQC",
) == SipMappingResult(
    fields={
        "inspection_item": "线性尺寸：35（2处）",
        "inspection_standard": "图纸要求",
        "inspection_method": "游标卡尺",
        "key_dimension": "否",
        "inspection_role": "IPQC",
        "source_page": 1,
        "remarks": "",
    },
    provenance={
        "inspection_item": "sip-auto-map/1",
        "inspection_standard": "sip-auto-map/1",
        "inspection_method": "sip-auto-map/1",
        "key_dimension": "sip-auto-map/1",
        "inspection_role": "sip-auto-map/1",
        "source_page": "sip-auto-map/1",
        "remarks": "sip-auto-map/1",
    },
    exceptions=(),
)
```

Add literal cases for diameter=`游标卡尺`、thread=`螺纹规`、radius=`半径规`、
angle=`万能角度尺`、general requirement=`目视`。Add failure cases for missing role,
missing/negative `page_index`, missing/unknown type and composite. Add a case proving
existing technical-requirement fields and their provenance win over rule defaults.

- [x] **Step 2: Run RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/review/test_sip_mapping.py -q
```

Expected: collection FAIL because `app.review.sip_mapping` does not exist.

- [x] **Step 3: Implement the minimal pure mapping Owner**

Implement immutable result data and exact constants:

```python
RULE_VERSION = "sip-auto-map/1"
METHOD_BY_TYPE = {
    "linear_dimension": "游标卡尺",
    "diameter_dimension": "游标卡尺",
    "thread": "螺纹规",
    "radius": "半径规",
    "angle": "万能角度尺",
    "general_requirement": "目视",
}
```

The function must:

- normalize `inspection_role` with `.strip()`;
- preserve nonblank `inspection_item`, `inspection_standard`, `key_dimension`,
  valid `source_page` and `remarks` already projected from confirmed technical
  requirements;
- derive only missing fields;
- return exceptions instead of guessing unsupported/composite method or page;
- never mutate `item`;
- never read PDF, inventory, Provider, database or Excel state.

- [x] **Step 4: Run GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/review/test_sip_mapping.py -q
```

Expected: all tests PASS.

- [x] **Step 5: Commit Task 1**

```bash
git add backend/app/review/sip_mapping.py backend/tests/unit/review/test_sip_mapping.py docs/superpowers/specs/2026-07-31-sip-auto-mapping-and-exception-review-design.md docs/superpowers/plans/2026-07-31-sip-auto-mapping-and-exception-review.md
git commit -m "feat(review): add deterministic SIP mapping"
```

### Task 2: One Transactional Generate Command And Freeze Gate

**Files:**
- Modify: `backend/app/review/schemas.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_review_operations.py`
- Modify: `backend/tests/integration/test_review_freeze.py`
- Modify: `backend/tests/contract/snapshots/api-v1.openapi.json`
- Regenerate: `frontend/src/api/generated.ts`
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Consumes:
  `{"type": "generate_sip_table", "inspection_role": NonBlankText}`.
- Produces per active item:
  all resolved SIP fields, `sip_suggestion_provenance`,
  `sip_mapping_exceptions: list[str]`, and
  `sip_detail_fields_confirmed = not sip_mapping_exceptions`.
- Preserves manually resolved row when `sip_detail_fields_confirmed is True`
  and its provenance has no `sip-auto-map/1` value.

- [ ] **Step 1: Write integration REDs**

Add tests proving:

1. one command maps all active supported rows, increments `version` exactly once
   and creates exactly one `OperationRecord(command="generate_sip_table")`;
2. inactive rows are untouched;
3. a row manually resolved through `set_sip_detail_fields` is byte-for-byte
   preserved;
4. an auto-mapped row can be regenerated with a changed project role, but no
   manually resolved field is overwritten;
5. composite/unknown rows carry exact exception codes and remain
   `sip_detail_fields_confirmed=False`;
6. complete generated rows satisfy existing freeze SIP readiness, while an
   exception row still yields `unresolved_confirmation`.

- [ ] **Step 2: Run RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py -q
```

Expected: FAIL because `generate_sip_table` is rejected by the discriminated command
schema and no batch branch exists.

- [ ] **Step 3: Add the stable command schema**

Add:

```python
class GenerateSipTable(CommandBase):
    type: Literal["generate_sip_table"]
    inspection_role: NonBlankText
```

Include it in `ReviewCommand`. No endpoint, DB column, migration or alternate write
path is added.

- [ ] **Step 4: Apply all rows inside the existing ReviewService transaction**

In `_apply_command()`:

- iterate active items only;
- preserve manual resolved rows;
- call `map_sip_item()` for all other rows;
- write fields/provenance/exceptions atomically;
- set readiness from exception emptiness;
- return active item IDs as audit targets;
- preserve `numbering_stale` because SIP-only generation does not change formal
  item identity or balloon order.

Update `_clear_sip_detail_fields()` to remove `sip_mapping_exceptions`. Keep
`_sip_confirmation_blockers()` as the freeze Veto: generated complete rows pass
because they carry all fields and readiness; exceptions fail closed.

- [ ] **Step 5: Run integration GREEN**

Run the Step 2 command again.

Expected: all focused integration tests PASS.

- [ ] **Step 6: Update and verify the API contract**

Run:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python -m app.contracts.openapi \
  --write --baseline tests/contract/snapshots/api-v1.openapi.json
cd ../frontend
npm run api:generate
cd ..
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_openapi_contract.py \
  backend/tests/contract/test_openapi_breaking_gate.py -q
npm --prefix frontend run api:check
```

Expected: contract tests and generated-client drift check PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/app/review/schemas.py backend/app/review/service.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_review_freeze.py backend/tests/contract/snapshots/api-v1.openapi.json frontend/src/api/generated.ts frontend/src/api/types.ts docs/superpowers/plans/2026-07-31-sip-auto-mapping-and-exception-review.md
git commit -m "feat(review): generate SIP rows in one command"
```

### Task 3: Exception-Only SIP UI And Metadata Conflict Visibility

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/SipInformationPanel.tsx`
- Modify: `frontend/src/components/workbench/SipInformationPanel.test.tsx`
- Modify: `frontend/src/components/workbench/SelectedSipDetailFields.tsx`
- Modify: `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
- Modify: `frontend/src/components/workbench/ExportPanel.tsx`
- Modify: `frontend/src/components/workbench/ExportPanel.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

**Interfaces:**
- Consumes `ReviewItem.sip_mapping_exceptions?: string[]`.
- Sends one `ReviewCommand`:
  `{type: "generate_sip_table", inspection_role: string}`.
- Presents `readyItemCount` and `exceptionItemCount`; it does not infer mapping.
- Receives complete `ProjectWorkbenchSipMetadataSuggestion[]` so current and
  recognized values can be compared without server mutation.

- [ ] **Step 1: Write component REDs**

Add tests proving:

- input role once + click `生成并检查 SIP 表格` sends exactly one batch command;
- summary says `SIP 表格：已生成 112，异常 3`;
- `处理下一条异常` selects only active rows with exceptions/readiness false;
- when exception count is zero, no next-action button is rendered;
- no copy says `已确认 5 / 115` or asks users to confirm every row;
- a selected exception shows its exact Chinese reason;
- persisted title metadata equal to suggestion shows `图纸识别一致`;
- conflicting value shows `当前值` and `图纸识别值`, and `采用识别值` changes only
  local metadata draft without calling `onCommand`;
- export blocker copy uses `SIP 异常 N 项` rather than `N 项未确认`.

- [ ] **Step 2: Run RED**

Run:

```bash
npm --prefix frontend test -- \
  src/components/workbench/SipInformationPanel.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/SelectedSipDetailFields.test.tsx \
  src/components/workbench/ExportPanel.test.tsx
```

Expected: assertion FAIL because the current UI still renders per-row confirmation
progress and has no batch action/conflict surface.

- [ ] **Step 3: Implement the minimal presenter changes**

- keep role input local until the batch button is clicked;
- derive ready/exception counts only from server-projected item fields;
- rename navigation to exception-only behavior;
- keep single-row `set_sip_detail_fields` form available for exception correction
  and optional manual override;
- render exception code through an exact copy map;
- pass full metadata suggestions, compare them with persisted/draft values, and
  adopt suggestion into local draft only;
- preserve dirty-draft save/cancel behavior and version-conflict error handling;
- do not add frontend mapping rules or local export generation.

- [ ] **Step 4: Run frontend GREEN**

Run the Step 2 command again, then:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: focused/full Vitest and production build PASS. Existing bundle-size warning
may remain but no new error is accepted.

- [ ] **Step 5: Commit Task 3**

```bash
git add frontend/src/api/types.ts frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/components/workbench/InspectionWorkbench.test.tsx frontend/src/components/workbench/SipInformationPanel.tsx frontend/src/components/workbench/SipInformationPanel.test.tsx frontend/src/components/workbench/SelectedSipDetailFields.tsx frontend/src/components/workbench/SelectedSipDetailFields.test.tsx frontend/src/components/workbench/ExportPanel.tsx frontend/src/components/workbench/ExportPanel.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles/workbench.css docs/superpowers/plans/2026-07-31-sip-auto-mapping-and-exception-review.md
git commit -m "feat(frontend): review only SIP exceptions"
```

### Task 4: Integrated Verification, Demo And Independent Review

**Files:**
- Modify: `docs/operations/sip-confirmation-demo/**`
- Modify: `docs/superpowers/plans/2026-07-31-sip-auto-mapping-and-exception-review.md`

**Interfaces:**
- Runtime target: local API and workbench discovered from repository scripts/current
  running services; no port is invented.
- Smoke path: project-level generation → exception summary → exception selection →
  metadata conflict adoption without server write.

- [ ] **Step 1: Run the combined backend gate**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/review/test_sip_mapping.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/contract/test_openapi_contract.py \
  backend/tests/contract/test_openapi_breaking_gate.py -q
```

Expected: PASS with no new warning attributable to this change.

- [ ] **Step 2: Run targeted API verification**

Against an unfrozen disposable/test working copy with a valid lock:

- submit one `generate_sip_table`;
- assert HTTP `200`;
- assert working version increases exactly once;
- assert supported rows become ready and composite/unknown rows carry exceptions;
- assert a second stale-version request returns the existing version-conflict
  envelope and does not partially modify rows.

- [ ] **Step 3: Run Chrome MCP smoke**

Open the affected localhost workbench and exercise:

1. verify the old `已确认 x/y` copy is absent;
2. enter the default role and click `生成并检查 SIP 表格`;
3. verify one successful command request;
4. verify ready/exception counts;
5. click `处理下一条异常`;
6. verify recognized/current metadata conflict is visible;
7. click `采用识别值` and verify no save request occurs until project metadata save;
8. verify console errors and unexpected HTTP `>=400` are zero.

- [ ] **Step 4: Refresh the teaching artifact**

Update `docs/operations/sip-confirmation-demo/` with current screenshots and concise
Chinese steps showing:

```text
审核检验项一次
→ 生成并检查 SIP 表格
→ 只处理异常
→ 异常归零后生成正式文件
```

Clearly label screenshots as current runtime evidence or instructional mock; never mix
the two.

- [ ] **Step 5: Independent focused review**

Reviewer must inspect the complete Task 1–3 diff and report:

- Verdict: accept / accept with concerns / reject;
- whether item membership still has one Owner;
- whether manual values are protected;
- whether any frontend/backend duplicate mapping rule exists;
- whether freeze/export remain fail-closed;
- whether tests cover one transaction, exception path, stale version and metadata
  conflict behavior.

Any blocking finding returns to the owning task with a new RED before remediation.

- [ ] **Step 6: Final diff, status and commit**

Run:

```bash
git diff --check
git status --short
```

Stage only demo/plan changes from Task 4:

```bash
git add docs/operations/sip-confirmation-demo docs/superpowers/plans/2026-07-31-sip-auto-mapping-and-exception-review.md
git commit -m "docs: refresh SIP exception workflow demo"
```

Set this plan status to `completed` only after automated gates, API smoke, Chrome smoke
and independent review all pass. If runtime is unavailable, leave status
`implementation complete / runtime blocked` and report the exact blocker.
