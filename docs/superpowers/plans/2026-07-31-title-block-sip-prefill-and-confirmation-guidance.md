# Title Block SIP Prefill And Confirmation Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从图纸 title block 生成带 provenance 的项目 SIP 待确认建议，并把检验项 SIP 的剩余数量、下一条入口和导出阻断原因明确呈现。

**Architecture:** 新建唯一 deterministic title-block suggestion Owner，消费 persisted native inventory observations 并由 workbench read API additive 投影；confirmed metadata 仍只由既有 `set_sip_metadata` 写入。frontend 使用 confirmed-first、suggestion-second 的本地 draft，并复用既有 per-item SIP command 做连续人工确认。

**Tech Stack:** Python 3.11、Pydantic、FastAPI、pytest、OpenAPI snapshot、TypeScript、React、Vitest、Chrome DevTools、Micromamba `qi-p0`

## Global Constraints

- Selected lane: `Heavy`。
- Current plan: 本文件是该用户目标唯一 current plan；不重开已完成的 technical
  requirement plan。
- No fabricated formal data: suggestion 不自动进入 confirmed state，缺值保持为空。
- No external provider: title block 只使用 local native observations。
- Unchanged contracts: `SetSipMetadata`、freeze、`ReviewedResult`、numbering、balloon、
  fixed SIP Excel 和 export publication 不变。
- Single writer: 主线程串行修改；read-only explorer/reviewer 不得写文件。
- TDD: 每个 production behavior 先运行对应失败测试，再写最小实现。
- Git: 只 stage 本 plan allowed paths；不得 stage `.pyc`、Harness runs 或其他现有 dirty
  files。

---

## Status

- Date: `2026-07-31`
- Status: `completed`
- Design source:
  `docs/superpowers/specs/2026-07-31-title-block-sip-prefill-and-confirmation-guidance-design.md`
- Selected lane: `Heavy`
- Selection evidence: 用户明确要求标题栏大部分字段自动识别填入，并批准安全引导流。
- Validation action: `close`
- Production authorization: 用户已回复“可以”，并在 execution workspace gate 明确
  选择 `当前 main`；根据仓库高自治规则在主线程串行执行。
- Writer ownership and order: parent/main thread，Task 1 → Task 5；无并发 writer。
- Next verification: none；implementation、runtime smoke 和 independent review 已闭环。

### Task 3 Transport Handoff Amendment

- Delta: `ProjectWorkbenchApp` 是 `ProjectWorkbenchResponse` 到
  `InspectionWorkbench` 的唯一 transport handoff，必须显式透传
  `sip_metadata_suggestions`；原 Task 3 allowed paths 漏列该入口。Task 4 build
  进一步证明 typed `ProjectWorkbenchFinalization` fixture 也必须显式提供 additive
  空列表。
- Evidence: `ProjectWorkbenchApp.tsx` 的 render seam 当前只透传
  `working_copy`、pages、candidates、sources、balloons 和 export projection。
- Owner unchanged: backend suggestion Owner 和 `set_sip_metadata` confirmed Owner
  不变；`ProjectWorkbenchApp` 只透传，不解析、不重算。
- Writer ownership: 主线程仍是唯一 writer。
- Next verification: ProjectWorkbenchApp component fixture 返回 suggestions 后，
  workbench 项目 SIP editor 显示建议值且没有提前发出 save command。

### Demo And Browser Fallback Amendment

- Delta: 用户要求可访问的教学截图；新增
  `docs/operations/sip-confirmation-demo/**`。Chrome DevTools runtime 返回
  `Transport closed`，因此按 `auto-feature-smoke-test` 的同等只读目标改用已配置的
  `browse` skill。
- Evidence: localhost `5173` 与 API `8000` 可用；真实项目已存在正式
  `sip_metadata`，所以浏览器不得用建议覆盖。真实页面只验证进度、next action、
  export blocker 和 console/network；新项目首次建议状态使用明确标注的静态教学图。
- Owner unchanged: 教学图不参与 runtime，不成为业务语义或 validation Owner。
- Writer ownership: 主线程仍为唯一 writer。
- Next verification: browser reload 全部当前请求为 HTTP `200`，console errors 为
  `0`，点击 next action 不发出 review command。

### Independent Review Remediation

- Initial verdict: `reject`；第一次修复后的复审仍为 `reject`；类别级修复后的最终
  verdict 为 `accept`。
- Blocking findings:
  1. 一页唯一、另一页同字段冲突时，原聚合会隐藏第二页 ambiguity；
  2. 含 CJK 的日期/页码 token 可能成为 `material_name` suggestion。
- TDD evidence:
  - 第一轮新增三个负向用例后先得到 `3 failed, 7 passed`，修复后
    `10 passed`；
  - reviewer 复现四种额外结构 token 后，扩展测试先得到
    `4 failed, 10 passed`，类别级修复后 `14 passed`。
  - `suggest_sip_metadata()` 聚合每页 ambiguity 并全局 suppress；
    `_STRUCTURAL_METADATA_TOKEN` 拒绝只由数字、日期和页码结构字符组成的产品名称
    候选，同时保留 `横行滑板` 和 `第1轴`。
- Fix commits:
  - `53b30b0 fix(pdf): fail closed on title metadata conflicts`
  - `b217331 fix(pdf): reject structural title metadata tokens`
- Writer ownership: 主线程单 writer；reviewer 保持只读。
- Final reviewer evidence: `git diff --check e8781d3^..b217331` PASS，
  title metadata unit `14 passed`，两个原 blocker 均 closed，无新增 finding。

## Allowed Paths

- `backend/app/pdf/title_block_metadata.py`
- `backend/app/projects/router.py`
- `backend/app/projects/schemas.py`
- `backend/tests/unit/pdf/test_title_block_metadata.py`
- `backend/tests/integration/test_project_workbench_api.py`
- `backend/tests/contract/test_openapi_contract.py`
- `backend/tests/contract/snapshots/api-v1.openapi.json`
- `frontend/src/api/generated.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchFinalization.test.tsx`
- `frontend/src/components/workbench/SipInformationPanel.tsx`
- `frontend/src/components/workbench/SipInformationPanel.test.tsx`
- `frontend/src/components/workbench/SelectedSipDetailFields.tsx`
- `frontend/src/components/workbench/SelectedSipDetailFields.test.tsx`
- `frontend/src/components/workbench/ExportPanel.tsx`
- `frontend/src/components/workbench/ExportPanel.test.tsx`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/styles/workbench.css`
- `docs/operations/sip-confirmation-demo/**`
- 本 spec/plan

### Task 1: Deterministic Title Block Suggestion Owner

**Files:**
- Create: `backend/app/pdf/title_block_metadata.py`
- Create: `backend/tests/unit/pdf/test_title_block_metadata.py`

**Interfaces:**
- Consumes: `pages: list[dict[str, object]]` from persisted inventory JSON.
- Produces:
  `suggest_sip_metadata(pages: list[object]) -> list[dict[str, object]]`.
- Stable fields: `field`, `value`, `observation_id`, `label_observation_id`,
  `page_index`, `bbox_pdf`, `rule_version`, `evidence_codes`.

- [x] **Step 1: Write real-geometry failing tests**

Create tests using the observed WELLI page size `1190.550048828125 ×
841.8900146484375` and native line observations for:

```python
expected = {
    "material_code": "12320096476",
    "material_name": "横行滑板",
    "drawing_number": "ZHZS25032501-04",
    "revision": "A/0",
}
assert {item["field"]: item["value"] for item in result} == expected
assert "material" not in {item["field"] for item in result}
```

Add negative tests for duplicate right-side values, OCR-only values, rotation,
cross-page observations and anchors outside the bottom-right title band.

- [x] **Step 2: Run RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_title_block_metadata.py -q
```

Expected: FAIL because `app.pdf.title_block_metadata` does not exist.

- [x] **Step 3: Implement the minimal Owner**

Implement:

```python
RULE_VERSION = "welli-title-metadata/1"
SIP_FIELD_ORDER = (
    "material_code",
    "material_name",
    "drawing_number",
    "material",
    "revision",
)

def suggest_sip_metadata(
    pages: list[object],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for page in pages:
        for suggestion in _suggest_page(page):
            grouped.setdefault(str(suggestion["field"]), []).append(suggestion)
    return [
        grouped[field][0]
        for field in SIP_FIELD_ORDER
        if len(grouped.get(field, ())) == 1
    ]
```

Only admit native horizontal line observations in the bottom-right title band.
Use exact compact labels, bounded same-row-right relation for material code,
drawing number and explicit material, bounded same-column-above relation for
revision, and a unique name candidate above the resolved drawing-number value.
Define `_suggest_page(page: object) -> list[dict[str, object]]` in the same
module; it must return an empty list for malformed pages and omit every
ambiguous field. If two pages suggest the same field,
`suggest_sip_metadata()` must omit that field instead of allowing the later
page to overwrite it.

- [x] **Step 4: Run GREEN**

Run the Task 1 command again.

Expected: all tests PASS without creating `.pyc`.

- [x] **Step 5: Commit Task 1**

```bash
git add backend/app/pdf/title_block_metadata.py backend/tests/unit/pdf/test_title_block_metadata.py
git commit -m "feat(pdf): derive title block SIP suggestions"
```

### Task 2: Additive Workbench API Projection

**Files:**
- Modify: `backend/app/projects/router.py`
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/tests/integration/test_project_workbench_api.py`
- Modify: `backend/tests/contract/snapshots/api-v1.openapi.json`
- Regenerate: `frontend/src/api/generated.ts`
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Consumes: `suggest_sip_metadata(pages)`.
- Produces: `ProjectWorkbenchResponse.sip_metadata_suggestions:
  list[ProjectWorkbenchSipMetadataSuggestionResponse]`.
- Does not modify: `working_copy.sip_metadata`.

- [x] **Step 1: Write API integration RED**

Add an inventory fixture with the Task 1 relations, call
`GET /api/v1/projects/{project_id}/workbench`, then assert:

```python
assert payload["working_copy"]["sip_metadata"] == {}
assert payload["sip_metadata_suggestions"][0] == {
    "field": "material_code",
    "value": "12320096476",
    "observation_id": "material-code-value",
    "label_observation_id": "material-code-label",
    "page_index": 0,
    "bbox_pdf": [1098.47, 807.02, 1152.38, 821.77],
    "rule_version": "welli-title-metadata/1",
    "evidence_codes": [
        "bottom_right_title_anchor",
        "native_line",
        "same_row_right_of_label",
        "unique_candidate",
    ],
}
```

Also assert serialized response contains no storage path or resource ref.

- [x] **Step 2: Run integration RED**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_project_workbench_api.py -q
```

Expected: FAIL because the response schema/projection lacks
`sip_metadata_suggestions`.

- [x] **Step 3: Add schema and projection**

Create `ProjectWorkbenchSipMetadataSuggestionResponse` with `extra="forbid"` and
literal SIP field names. Call the Task 1 Owner once inside
`_workbench_payload()` using the already loaded `pages`; add its result to the
response. Do not call it from frontend or export.

- [x] **Step 4: Run integration GREEN**

Run the Task 2 integration command again.

Expected: all tests PASS.

- [x] **Step 5: Update approved OpenAPI projection**

Run:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python -m app.contracts.openapi --write --baseline tests/contract/snapshots/api-v1.openapi.json
cd ../frontend
micromamba run -n qi-p0 npm run api:generate
```

Then run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/test_openapi_contract.py backend/tests/contract/test_openapi_breaking_gate.py -q
micromamba run -n qi-p0 npm --prefix frontend run api:check
```

Expected: snapshot, breaking gate and generated transport type all PASS.

- [x] **Step 6: Commit Task 2**

```bash
git add backend/app/projects/router.py backend/app/projects/schemas.py backend/tests/integration/test_project_workbench_api.py backend/tests/contract/snapshots/api-v1.openapi.json frontend/src/api/generated.ts frontend/src/api/types.ts
git commit -m "feat(api): expose title block SIP suggestions"
```

### Task 3: Confirmed-First Project SIP Prefill

**Files:**
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Modify: `frontend/src/components/workbench/SipInformationPanel.tsx`
- Modify: `frontend/src/components/workbench/SipInformationPanel.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

**Interfaces:**
- Consumes:
  `sipMetadataSuggestions: ProjectWorkbenchSipMetadataSuggestionView[]`.
- Produces: confirmed-first `MetadataDraft` and per-field recognized-state UI.
- Confirmation remains existing `set_sip_metadata`.

- [x] **Step 1: Write component RED**

Cover:

```tsx
expect(screen.getByLabelText("图号")).toHaveValue("ZHZS25032501-04");
expect(screen.getByText("图纸识别，待确认")).toBeInTheDocument();
expect(onSave).not.toHaveBeenCalled();
```

Add cases proving confirmed values override suggestions, a dirty draft survives
workbench refresh, missing `material` remains empty, and clicking confirmation
submits exactly one existing `set_sip_metadata` command. Add a
`ProjectWorkbenchApp` test proving the API field is only forwarded and does not
trigger a command during load.

- [x] **Step 2: Run frontend RED**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/SipInformationPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx src/components/workbench/ProjectWorkbenchApp.test.tsx
```

Expected: FAIL because suggestions are not accepted or rendered.

- [x] **Step 3: Implement minimal prefill**

Extend the UI view type from the generated suggestion transport. Change
`metadataDraft()` to fill each field from confirmed metadata first, suggestion
second. Pass recognized field names to `SipInformationPanel`; render
`图纸识别，待确认` beside those inputs. Preserve dirty and confirmed refresh guards.

- [x] **Step 4: Run frontend GREEN**

Run the Task 3 test command.

Expected: all focused tests PASS.

- [x] **Step 5: Commit Task 3**

```bash
git add frontend/src/api/types.ts frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/components/workbench/InspectionWorkbench.test.tsx frontend/src/components/workbench/ProjectWorkbenchApp.tsx frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx frontend/src/components/workbench/SipInformationPanel.tsx frontend/src/components/workbench/SipInformationPanel.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles/workbench.css
git commit -m "feat(frontend): prefill project SIP from drawing evidence"
```

### Task 4: Sequential Item SIP Guidance And Export Blocker

**Files:**
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
- `SelectedSipDetailFields` produces `onConfirmed(itemId: string)` only after a
  successful command.
- `SipInformationPanel` consumes `confirmedItemCount`, `activeItemCount`,
  `onSelectNextUnconfirmed`.
- `ExportPanel` consumes `sipPendingCount` and `projectMetadataConfirmed`.

- [x] **Step 1: Write sequential-flow RED**

Add tests proving:

```tsx
expect(screen.getByText("检验项 SIP")).toBeInTheDocument();
expect(screen.getByText("3 / 115")).toBeInTheDocument();
fireEvent.click(screen.getByRole("button", {
  name: "处理下一条未确认 SIP",
}));
```

The next action selects the first active unconfirmed item. A successful
`set_sip_detail_fields` selects the next unconfirmed item; a failed command does
not. `ExportPanel` with `sipPendingCount={112}` renders
`还需确认 112 条检验项 SIP`.

- [x] **Step 2: Run sequential-flow RED**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/SelectedSipDetailFields.test.tsx src/components/workbench/SipInformationPanel.test.tsx src/components/workbench/ExportPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL because callbacks, progress and blocker props do not exist.

- [x] **Step 3: Implement the guidance**

Compute active/pending counts once in `InspectionWorkbench`. Use stable current
item order to find the next active unconfirmed item, switch filter to `all`, and
reuse `selectItem()`. Trigger auto-next only from `onConfirmed` after command
success. Replace the summary label, add SIP progress/action, and prioritize exact
SIP blocker copy in `ExportPanel` without changing `canFinalize`.

- [x] **Step 4: Run sequential-flow GREEN**

Run the Task 4 test command.

Expected: all focused tests PASS.

- [x] **Step 5: Commit Task 4**

```bash
git add frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/components/workbench/InspectionWorkbench.test.tsx frontend/src/components/workbench/SipInformationPanel.tsx frontend/src/components/workbench/SipInformationPanel.test.tsx frontend/src/components/workbench/SelectedSipDetailFields.tsx frontend/src/components/workbench/SelectedSipDetailFields.test.tsx frontend/src/components/workbench/ExportPanel.tsx frontend/src/components/workbench/ExportPanel.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles/workbench.css
git commit -m "feat(frontend): guide sequential SIP confirmation"
```

### Task 5: Full Verification, Browser Smoke And Independent Review

**Files:**
- Modify: this plan status/evidence only after gates pass.

**Interfaces:**
- Active path: native inventory → suggestions → local draft → explicit confirm.
- Failure path: ambiguous/missing evidence → blank manual field; failed item save
  → no navigation.
- Rollback first check: existing workbench bootstrap integration test.

- [x] **Step 1: Run backend verification**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_title_block_metadata.py backend/tests/integration/test_project_workbench_api.py backend/tests/contract/test_openapi_contract.py backend/tests/contract/test_openapi_breaking_gate.py -q
```

- [x] **Step 2: Run frontend verification**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run api:check
micromamba run -n qi-p0 npm --prefix frontend run build
```

- [x] **Step 3: Run repository checks**

```bash
python .agent/harness/scripts/check-contracts.py
git diff --check
```

- [x] **Step 4: Execute `auto-feature-smoke-test`**

Read the skill completely, then use current runtime and Chrome DevTools to
verify suggestion evidence, confirmed-vs-suggested state, item progress,
next-item navigation, export blocker text, console and network health. Do not
write the user's current project; use a test project or request interception for
the confirm command.

- [x] **Step 5: Independent reviewer gate**

Inspect and bind `/home/reggie/.codex/agents/reviewer.toml` through the repository
task-name-safe profile path. Reviewer is read-only and checks:

- suggestion Owner uniqueness and ambiguity fail-closed behavior；
- no confirmed metadata mutation before command；
- no Provider/title-block privacy regression；
- no candidate/coverage/freeze/export semantic drift；
- frontend success-only auto-next；
- tests cover the real failure surface。

Required output:

```text
Verdict: accept | accept with concerns | reject
Blocking issues:
Non-blocking concerns:
Evidence:
Minimal follow-up:
```

- [x] **Step 6: Parent final diff and commit**

Review `git diff --stat`, `git diff --check`, every scoped diff and current
`git status`. Fix verified blocking findings, rerun affected checks, then:

```bash
git add docs/superpowers/specs/2026-07-31-title-block-sip-prefill-and-confirmation-guidance-design.md docs/superpowers/plans/2026-07-31-title-block-sip-prefill-and-confirmation-guidance.md
git commit -m "docs: close title block SIP guidance plan"
```

- [x] **Step 7: Close only with runtime truth**

Set `Status: completed` only when focused/full checks, browser smoke and
independent review pass. Otherwise keep `in_progress` and record the single
blocker and remaining risk.

## Completion Evidence

### Commits

- `e8781d3 feat(pdf): derive title block SIP suggestions`
- `e44058e feat(api): expose title block SIP suggestions`
- `585d1e4 feat(frontend): prefill project SIP from drawing evidence`
- `b87ff30 feat(frontend): guide sequential SIP confirmation`
- `53b30b0 fix(pdf): fail closed on title metadata conflicts`
- `b217331 fix(pdf): reject structural title metadata tokens`

### Automated Verification

- Backend focused unit/integration/OpenAPI/breaking gate:
  `39 passed, 1 StarletteDeprecationWarning`。
- Backend full suite:
  `1484 passed, 2 warnings`。使用隔离 Postgres `127.0.0.1:55433`；先重建
  `qi_test` 并执行 Alembic `upgrade head`，避免 previous focused runs 的数据污染。
- Frontend full suite: `24 files, 266 tests passed`。
- `npm --prefix frontend run api:check`: PASS。
- `npm --prefix frontend run build`: PASS；仅保留既有 `>500 kB` chunk warning。
- `.agent/harness/scripts/check-contracts.py`: all drift/error counts `0`。
- `git diff --check`: PASS。

### Runtime And Browser Evidence

- Live workbench API:
  - `material_code = 12320096476`
  - `material_name = 横行滑板`
  - `drawing_number = ZHZS25032501-04`
  - `revision = A/0`
  - `material` 未建议。
- Live project active item SIP:
  `3 / 115`，pending `112`。
- Browser:
  - current reload 的 API、PDF、JS/CSS 请求均为 HTTP `200`；
  - console errors 为 `0`；
  - `处理下一条未确认 SIP` 只改变本地 selection；
  - export panel 显示 `还需确认 112 条检验项 SIP`；
  - 未发送 review command、freeze、confirm 或 export 请求；只续租既有 editor
    lock。
- Chrome DevTools transport 不可用（`Transport closed`），按 amendment 使用
  `browse` skill 完成同等 localhost smoke。

### Independent Review

- Applied profile: `reviewer`。
- Verified child runtime: `agent_role=reviewer`、`model=gpt-5.6-sol`、
  `reasoning_effort=high`。
- Final verdict: `accept`。
- Blocking issues: none。

### Demo

- `docs/operations/sip-confirmation-demo/07-title-block-prefill-demo.png`：
  新项目标题栏建议和人工确认边界。
- `docs/operations/sip-confirmation-demo/05-live-guided-progress.png`：
  当前真实 `3 / 115` 进度。
- `docs/operations/sip-confirmation-demo/08-live-next-unconfirmed.png`：
  next action 选择下一条。
- `docs/operations/sip-confirmation-demo/06-live-export-blocker.png`：
  精确的 `112` 条 export blocker。
