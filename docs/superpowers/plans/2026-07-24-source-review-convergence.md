# Source Review Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 source-only coverage 待确认项原子地合入检验项审核列表，确保“添加为检验项”生成真实可导出的 `ReviewItem`，“忽略”生成明确的 `non_inspection` disposition。

**Architecture:** `ReviewService` 继续是 working-copy mutation 的单一 Owner，新增 `promote_source` 与 `ignore_source` 两个稳定命令，在一个 PostgreSQL transaction 内同时更新 item-set、Coverage Ledger、version、numbering state 和 operation record。Frontend 从现有 working-copy coverage 与 workbench sources 派生待判定来源行，把它们加入 `InspectionItemTable` 的统一搜索、筛选、分页和详情区域，并在新路径通过后删除 `CoverageReviewPanel` 旧路径。

**Tech Stack:** Python 3.12、FastAPI/Pydantic、SQLAlchemy/PostgreSQL、pytest、React 19、TypeScript、Vitest/Testing Library、Vite、Chrome DevTools MCP。

---

## Execution Contract

- **Selected lane:** `Heavy`
  - 新增稳定 review command schema，并改变 review aggregate 与 Coverage Ledger 的
    data-integrity transition。
- **Selected spec:** `docs/superpowers/specs/2026-07-24-source-review-convergence-design.md`
- **Selection evidence:** 用户已于 2026-07-24 复核并批准 written spec；现有
  `resolve_confirmation` 只清 flag，不能生成 export-consumed item。
- **Validation action:** `continue`
- **Problem boundary:** 只处理 `candidate_id is None` 且
  `requires_confirmation is True` 的 source-only coverage entries。
- **Single owner:** `backend/app/review/service.py::ReviewService.apply` /
  `_apply_command`。
- **Old path to remove:** `CoverageReviewPanel` 及 source-only 使用
  `resolve_confirmation(observation_id, accepted)` 的路径。
- **Unchanged contracts:**
  - Automatic result 保持 immutable；
  - Coverage Owner 继续拥有 observation completeness；
  - 普通 item `resolve_confirmation` 保持；
  - unresolved confirmation 继续阻止 freeze；
  - reviewed result/export 继续只消费 active items；
  - 不改变 migration、processing、Provider、balloon、export 和多 PDF。
- **Writer ownership and order:** 一个 write-capable executor 串行完成 Task 1～5；
  reviewer 只读且只能在实现完成后检查 diff。
- **Focused verification command:**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_review_schema.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
micromamba run -n qi-p0 npm --prefix frontend run build
```

- **Rollback:** 每个 task 只 revert 自己的 commit。Task 4 删除旧路径后若回滚，必须
  同时回滚 Task 3 的 frontend replacement，避免没有 source-only 入口。实际发生
  rollback 后第一项验证：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_review_freeze.py::test_source_only_confirmation_blocks_freeze -q
```

## File Structure

### Backend

- `backend/app/review/schemas.py`
  - 定义 `PromoteSource`、`IgnoreSource` 命令 payload 和 union。
- `backend/app/review/service.py`
  - 唯一提交 source-only eligibility、item creation、coverage disposition 和
    numbering transition。
- `backend/tests/contract/test_review_schema.py`
  - 验证新命令的 discriminated union 与字段约束。
- `backend/tests/integration/test_review_operations.py`
  - 验证 promote/ignore atomic behavior、旧 source-only resolve retirement 和 audit。
- `backend/tests/integration/test_review_freeze.py`
  - 保持 unresolved source freeze blocker regression。

### Frontend

- `frontend/src/api/types.ts`
  - 镜像两个 review command payload。
- `frontend/src/copy/zhCN.ts`
  - 增加统一列表与来源详情文案，删除旧 panel 文案。
- `frontend/src/components/workbench/RecognitionSummary.tsx`
  - 把 pending source count 纳入“全部”和“需人工处理”。
- `frontend/src/components/workbench/RecognitionSummary.test.tsx`
  - 证明汇总计数与 filter action。
- `frontend/src/components/workbench/InspectionItemTable.tsx`
  - 拥有统一 row projection、source selection 和 source detail editor。
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
  - 证明 source row、筛选、promotion validation 和 command payload。
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
  - 派生 pending sources、协调 source/item selection，并移除旧 panel。
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
  - 证明真实 workbench save flow 与 overlay selection。
- `frontend/src/styles/workbench.css`
  - 只增加统一列表 source row/detail editor 的必要样式。
- 删除：
  - `frontend/src/components/review/CoverageReviewPanel.tsx`
  - `frontend/src/components/review/CoverageReviewPanel.test.tsx`
  - `frontend/src/styles/coverage-review.css`

### Durable Contract

- `docs/contracts/MAIN_CONTRACT_MATRIX.md`
  - 细化 `REV-004`：source-only decision 必须原子提交 disposition 与 item transition。

## Task 1: Add Explicit Source Review Command Contracts

**Files:**
- Modify: `backend/app/review/schemas.py`
- Modify: `backend/tests/contract/test_review_schema.py`

- [ ] **Step 1: Write failing contract tests**

在 `test_review_command_union_accepts_only_planned_commands` 的参数中加入：

```python
        {
            "type": "promote_source",
            "observation_id": "source-only",
            "raw_text": "M16",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        },
        {
            "type": "ignore_source",
            "observation_id": "source-only",
        },
```

新增严格字段测试：

```python
@pytest.mark.parametrize(
    "command",
    [
        {
            "type": "promote_source",
            "observation_id": "source-only",
            "raw_text": "   ",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        },
        {
            "type": "promote_source",
            "observation_id": "source-only",
            "raw_text": "M16",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
        },
        {
            "type": "ignore_source",
            "observation_id": "source-only",
            "accepted": False,
        },
    ],
)
def test_source_review_commands_require_exact_fields(
    command: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        parse_review_command(command)
```

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_review_schema.py::test_review_command_union_accepts_only_planned_commands \
  backend/tests/contract/test_review_schema.py::test_source_review_commands_require_exact_fields -q
```

Expected: FAIL because `promote_source` and `ignore_source` are not members of
`ReviewCommand`.

- [ ] **Step 3: Add minimal Pydantic command models**

在 command models 之前保留一个可复用 nonblank type：

```python
NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
```

加入：

```python
class PromoteSource(CommandBase):
    type: Literal["promote_source"]
    observation_id: str = Field(min_length=1)
    raw_text: NonBlankText
    item_type: CandidateType
    scope: Literal["local_feature", "global_requirement"]
    balloon_required: bool
    page_index: int = Field(ge=0)


class IgnoreSource(CommandBase):
    type: Literal["ignore_source"]
    observation_id: str = Field(min_length=1)
```

把两个 model 加入 `ReviewCommand` union，删除文件后部重复的 `NonBlankText`
定义。不要给 promote 增加 coordinates；坐标必须来自服务端 coverage entry。

- [ ] **Step 4: Run GREEN**

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_review_schema.py -q
```

Expected: all tests PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/schemas.py backend/tests/contract/test_review_schema.py
git commit -m "feat: define source review commands"
```

## Task 2: Make Promote And Ignore Atomic In ReviewService

**Files:**
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_review_operations.py`
- Verify: `backend/tests/integration/test_review_freeze.py`

- [ ] **Step 1: Replace the old source-only resolve test with failing promote/ignore tests**

添加 fixture helper：

```python
def _set_source_only_coverage(
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-only",
            "disposition": "ambiguous",
            "source_location_id": "source-location",
            "coordinates": [21, 22, 23, 24],
            "candidate_id": None,
            "requires_confirmation": True,
        }
    ]
    coverage["review_required_count"] = 1
    working_copy.coverage = coverage
    db_session.commit()
```

用以下测试替换
`test_resolve_source_only_coverage_decrements_review_required_count`：

```python
def test_promote_source_atomically_creates_item_and_resolves_coverage(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_source_only_coverage(working_copy, db_session)
    before_item_ids = {item["item_id"] for item in working_copy.items}

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "promote_source",
            "observation_id": "source-only",
            "raw_text": " M16 ",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 1,
        },
    )

    promoted = next(
        item for item in saved.items if item["item_id"] not in before_item_ids
    )
    assert promoted == {
        "item_id": promoted["item_id"],
        "item_type": "thread",
        "raw_text": "M16",
        "normalized_text": "M16",
        "coordinates": [21, 22, 23, 24],
        "scope": "local_feature",
        "balloon_required": True,
        "requires_confirmation": False,
        "source_location_ids": ["source-location"],
        "page_index": 1,
        "source_type": "manual",
        "status": "pending",
        "active": True,
    }
    entry = saved.coverage["entries"][0]
    assert entry["disposition"] == "candidate"
    assert entry["candidate_id"] == promoted["item_id"]
    assert entry["requires_confirmation"] is False
    assert entry["confirmation_accepted"] is True
    assert saved.coverage["review_required_count"] == 0
    assert saved.numbering_stale is True
    operation = db_session.scalar(
        select(OperationRecord).where(
            OperationRecord.command == "promote_source"
        )
    )
    assert operation is not None
    assert operation.target_ids == ["source-only", promoted["item_id"]]


def test_ignore_source_marks_non_inspection_without_creating_item(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_source_only_coverage(working_copy, db_session)
    before_items = copy.deepcopy(working_copy.items)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={"type": "ignore_source", "observation_id": "source-only"},
    )

    assert saved.items == before_items
    entry = saved.coverage["entries"][0]
    assert entry["disposition"] == "non_inspection"
    assert entry["candidate_id"] is None
    assert entry["requires_confirmation"] is False
    assert entry["confirmation_accepted"] is False
    assert saved.coverage["review_required_count"] == 0
    assert saved.numbering_stale is False
    operation = db_session.scalar(
        select(OperationRecord).where(
            OperationRecord.command == "ignore_source"
        )
    )
    assert operation is not None
    assert operation.target_ids == ["source-only"]
```

加入旧路径退休和 eligibility failure：

```python
def test_resolve_confirmation_rejects_source_only_observation(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_source_only_coverage(working_copy, db_session)

    with pytest.raises(ReviewNotFound):
        review_service.apply(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
            command={
                "type": "resolve_confirmation",
                "item_id": "source-only",
                "accepted": True,
            },
        )

    db_session.refresh(working_copy)
    assert working_copy.coverage["entries"][0]["requires_confirmation"] is True
    assert working_copy.version == 1


@pytest.mark.parametrize("command_type", ["promote_source", "ignore_source"])
def test_source_review_rejects_candidate_backed_entry(
    command_type: str,
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    payload: dict[str, object] = {
        "type": command_type,
        "observation_id": "s-complex",
    }
    if command_type == "promote_source":
        payload.update(
            raw_text="Ra 3.2",
            item_type="general_requirement",
            scope="local_feature",
            balloon_required=True,
            page_index=0,
        )
    with pytest.raises(ReviewNotFound):
        review_service.apply(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
            command=payload,
        )
```

从 `app.review.service` import `ReviewNotFound`。

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_review_operations.py \
  -k 'promote_source or ignore_source or source_only_observation or source_review_rejects' -q
```

Expected: FAIL because `_apply_command` does not support the new models and old
`resolve_confirmation` still accepts source-only observation IDs。

- [ ] **Step 3: Implement one eligibility helper and two atomic transitions**

Import the new models:

```python
from app.review.schemas import (
    IgnoreSource,
    PromoteSource,
    ResolveConfirmation,
    ReviewCommand,
    # keep the existing imports
)
```

Add helpers:

```python
@staticmethod
def _pending_source_entry(
    coverage: dict[str, Any],
    observation_id: str,
) -> dict[str, Any]:
    matches = [
        entry
        for entry in coverage.get("entries", [])
        if entry.get("observation_id") == observation_id
    ]
    if (
        len(matches) != 1
        or matches[0].get("requires_confirmation") is not True
        or matches[0].get("candidate_id") is not None
    ):
        raise ReviewNotFound(
            f"pending source {observation_id} was not found"
        )
    return matches[0]


@staticmethod
def _refresh_review_required_count(coverage: dict[str, Any]) -> None:
    coverage["review_required_count"] = sum(
        entry.get("requires_confirmation") is True
        for entry in coverage.get("entries", [])
    )
```

In `_apply_command`, before `ResolveConfirmation`, add:

```python
        if isinstance(command, PromoteSource):
            entry = self._pending_source_entry(
                coverage,
                command.observation_id,
            )
            source_id = entry.get("source_location_id")
            coordinates = entry.get("coordinates")
            if not isinstance(source_id, str) or not source_id:
                raise ValueError("pending source must have a source location")
            if (
                not isinstance(coordinates, (list, tuple))
                or len(coordinates) != 4
                or not all(isinstance(value, (int, float)) for value in coordinates)
            ):
                raise ValueError("pending source must have PDF coordinates")
            item_id = str(uuid.uuid4())
            raw_text = command.raw_text
            items.append(
                {
                    "item_id": item_id,
                    "item_type": command.item_type,
                    "raw_text": raw_text,
                    "normalized_text": raw_text,
                    "coordinates": list(coordinates),
                    "scope": command.scope,
                    "balloon_required": command.balloon_required,
                    "requires_confirmation": False,
                    "source_location_ids": [source_id],
                    "page_index": command.page_index,
                    "source_type": "manual",
                    "status": "pending",
                    "active": True,
                }
            )
            entry.update(
                {
                    "disposition": "candidate",
                    "candidate_id": item_id,
                    "requires_confirmation": False,
                    "confirmation_accepted": True,
                }
            )
            self._refresh_review_required_count(coverage)
            return [command.observation_id, item_id], True
        if isinstance(command, IgnoreSource):
            entry = self._pending_source_entry(
                coverage,
                command.observation_id,
            )
            entry.update(
                {
                    "disposition": "non_inspection",
                    "candidate_id": None,
                    "requires_confirmation": False,
                    "confirmation_accepted": False,
                }
            )
            self._refresh_review_required_count(coverage)
            return [command.observation_id], numbering_stale
```

Narrow `_resolve_confirmation` coverage matching:

```python
        for entry in coverage.get("entries", []):
            if entry.get("candidate_id") == item_id:
                entry["requires_confirmation"] = False
                entry["confirmation_accepted"] = accepted
                resolved = True
```

Replace its inline counter with `_refresh_review_required_count(coverage)`。

- [ ] **Step 4: Run GREEN and freeze regression**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_review_schema.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py -q
```

Expected: all tests PASS。

- [ ] **Step 5: Commit**

```bash
git add \
  backend/app/review/service.py \
  backend/tests/integration/test_review_operations.py
git commit -m "feat: resolve source reviews atomically"
```

## Task 3: Add Pending Sources To Summary And Unified Table

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/components/workbench/RecognitionSummary.tsx`
- Modify: `frontend/src/components/workbench/RecognitionSummary.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/styles/workbench.css`

- [ ] **Step 1: Write failing summary and table tests**

在 `RecognitionSummary.test.tsx` 给现有 render 增加
`pendingSourceCount={2}`，并把 assertions 改为：

```typescript
expect(screen.getByRole("button", { name: "筛选全部" }).textContent)
  .toContain("5");
expect(screen.getByTestId("summary-manual-count").textContent).toBe("3");
```

在 `InspectionItemTable.test.tsx` 增加：

```typescript
test("待判定来源进入统一列表并产生显式 source review commands", () => {
  const onSelectSource = vi.fn();
  const onCommand = vi.fn();
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-1",
        sourceId: "source-1",
        rawText: "技术要求：去除毛刺",
        coordinates: [60, 70, 150, 84],
        pageIndex: 1,
      }]}
      filter="all"
      selectedSourceId="source-1"
      onSelectItem={vi.fn()}
      onSelectSource={onSelectSource}
      onCommand={onCommand}
    />,
  );

  const row = screen.getByRole("row", { name: /技术要求：去除毛刺/ });
  expect(row.textContent).toContain("原始来源");
  expect(row.textContent).toContain("第 2 页");
  expect(row.textContent).toContain("待判定来源");
  fireEvent.click(row);
  expect(onSelectSource).toHaveBeenCalledWith("source-1");

  expect(screen.getByRole("button", { name: "添加为检验项" }))
    .toBeDisabled();
  fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
    target: { value: "general_requirement" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));
  expect(onCommand).toHaveBeenLastCalledWith({
    type: "promote_source",
    observation_id: "observation-1",
    raw_text: "技术要求：去除毛刺",
    item_type: "general_requirement",
    scope: "local_feature",
    balloon_required: true,
    page_index: 1,
  });

  fireEvent.click(screen.getByRole("button", {
    name: "忽略，不作为检验项",
  }));
  expect(onCommand).toHaveBeenLastCalledWith({
    type: "ignore_source",
    observation_id: "observation-1",
  });
});


test("需人工处理筛选包含待判定来源", () => {
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-1",
        sourceId: "source-1",
        rawText: "伟立机器人",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="manual_required"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
    />,
  );
  expect(screen.getByRole("row", { name: /伟立机器人/ })).not.toBeNull();
});
```

If the local Testing Library typings do not expose `toBeDisabled`, use:

```typescript
expect(
  screen.getByRole("button", { name: "添加为检验项" })
    .hasAttribute("disabled"),
).toBe(true);
```

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx
```

Expected: TypeScript/test FAIL because pending source props, copy and commands do not
exist。

- [ ] **Step 3: Mirror command types and copy**

在 `ReviewCommand` union 加入：

```typescript
  | {
      type: "promote_source";
      observation_id: string;
      raw_text: string;
      item_type: CandidateType;
      scope: "local_feature" | "global_requirement";
      balloon_required: boolean;
      page_index: number;
    }
  | { type: "ignore_source"; observation_id: string }
```

在 `zhCN.inspection` 增加：

```typescript
sourceType: "原始来源",
sourcePending: "待判定来源",
sourceEditor: "待判定来源处理",
sourceRawText: "原始标注",
sourceItemType: "检验类型",
sourceScope: "范围",
sourceBalloonRequired: "需要气泡",
promoteSource: "添加为检验项",
ignoreSource: "忽略，不作为检验项",
selectItemType: "请选择检验类型",
```

- [ ] **Step 4: Make summary counts source-aware**

Add a defaulted prop:

```typescript
type RecognitionSummaryProps = {
  items: ReviewItem[];
  balloons: BalloonOverlay[];
  pendingSourceCount?: number;
  filter: InspectionFilter;
  onFilterChange: (filter: InspectionFilter) => void;
};
```

Destructure `pendingSourceCount = 0`，then:

```typescript
const manual = balloons.filter(
  (balloon) =>
    balloon.status !== "deleted"
    && balloon.placementStatus === "manual_required",
).length + pendingSourceCount;
```

The “all” chip uses:

```tsx
<strong>{items.length + pendingSourceCount}</strong>
```

- [ ] **Step 5: Add a source-row projection and source editor to the table**

Export the frontend-only view type:

```typescript
export type PendingSourceReview = {
  observationId: string;
  sourceId: string;
  rawText: string;
  coordinates: [number, number, number, number];
  pageIndex?: number;
};
```

Extend props:

```typescript
pendingSources?: PendingSourceReview[];
selectedSourceId?: string;
onSelectSource?: (sourceId: string) => void;
```

Destructure with the backward-compatible default:

```typescript
pendingSources = [],
```

Add `source_pending` to `ItemStatus` and `STATUS_LABELS`:

```typescript
source_pending: zhCN.inspection.sourcePending,
```

Build a unified discriminated projection before filtering:

```typescript
type ListEntry =
  | { kind: "item"; key: string; item: ReviewItem }
  | { kind: "source"; key: string; source: PendingSourceReview };

const entries: ListEntry[] = [
  ...items.map((item) => ({
    kind: "item" as const,
    key: `item:${item.item_id}`,
    item,
  })),
  ...pendingSources.map((source) => ({
    kind: "source" as const,
    key: `source:${source.observationId}`,
    source,
  })),
];
```

Filtering rules:

```typescript
const filtered = entries.filter((entry) => {
  if (entry.kind === "source") {
    const matchesSummary =
      filter === "all" || filter === "manual_required";
    const matchesStatus =
      statusFilter === "all" || statusFilter === "source_pending";
    const matchesSearch = entry.source.rawText
      .toLocaleLowerCase("zh-CN")
      .includes(search.trim().toLocaleLowerCase("zh-CN"));
    return matchesSummary && matchesStatus && matchesSearch;
  }
  // Keep the current item filter logic unchanged here.
});
```

Use both selection identities when locating the selected page:

```typescript
const selectedFilteredIndex = filtered.findIndex((entry) =>
  entry.kind === "item"
    ? entry.item.item_id === selectedItemId
    : entry.source.sourceId === selectedSourceId,
);
```

Keep the existing page calculation, and include `selectedSourceId` in the effect that
jumps to `selectedPage`。This guarantees a source selected from the drawing or another
control becomes visible even when it is beyond the first 50 unified rows。

Render a source row with the same five cells:

```tsx
if (entry.kind === "source") {
  const source = entry.source;
  return (
    <div
      key={entry.key}
      role="row"
      tabIndex={0}
      aria-selected={selectedSourceId === source.sourceId}
      data-selected={selectedSourceId === source.sourceId}
      data-source-id={source.sourceId}
      className="inspection-table__row inspection-table__row--source"
      onClick={() => onSelectSource?.(source.sourceId)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          onSelectSource?.(source.sourceId);
        }
      }}
    >
      <strong role="cell" className="inspection-number inspection-number--empty">
        {zhCN.workbench.unknown}
      </strong>
      <span role="cell" className="inspection-item-copy">
        <strong title={source.rawText}>{source.rawText}</strong>
        <small>{zhCN.inspection.sourceType}</small>
      </span>
      <span role="cell">{zhCN.workbench.unknown}</span>
      <span role="cell">
        {source.pageIndex === undefined
          ? zhCN.workbench.unknown
          : zhCN.inspection.sourcePage(source.pageIndex + 1)}
      </span>
      <span role="cell" className="geometry-state geometry-state--source_pending">
        <strong>{zhCN.inspection.sourcePending}</strong>
      </span>
    </div>
  );
}
```

Maintain `SourceDraft` by `observationId`:

```typescript
type SourceDraft = {
  rawText: string;
  itemType: CandidateType | "";
  scope: "local_feature" | "global_requirement";
  balloonRequired: boolean;
};
```

Initialize selected source with no guessed type:

```typescript
{
  rawText: selectedSource.rawText,
  itemType: "",
  scope: "local_feature",
  balloonRequired: true,
}
```

Render the source detail fieldset in the same location that otherwise renders SIP
detail fields. The promote button emits:

```typescript
onCommand({
  type: "promote_source",
  observation_id: selectedSource.observationId,
  raw_text: sourceDraft.rawText,
  item_type: sourceDraft.itemType,
  scope: sourceDraft.scope,
  balloon_required: sourceDraft.balloonRequired,
  page_index: selectedSource.pageIndex,
});
```

Guard this call so `itemType !== ""` and `pageIndex !== undefined`; disable the button
otherwise. Ignore emits:

```typescript
onCommand({
  type: "ignore_source",
  observation_id: selectedSource.observationId,
});
```

Reuse `onDraftChange` for both SIP and source draft dirty IDs. Do not clear source draft
when a command is queued; clear only its dirty marker so a failed save retains values
while the pending command remains retryable。

- [ ] **Step 6: Add minimal existing-style CSS**

Append only:

```css
.inspection-table__row--source {
  background: #fffaf0;
}

.inspection-table__row--source[data-selected="true"] {
  background: #fff3d6;
}

.source-review-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
  border: 1px solid #f2c46d;
  border-radius: 8px;
  background: #fffaf0;
}

.source-review-fields legend {
  color: var(--qi-text);
  font-weight: 700;
}

.source-review-actions {
  display: flex;
  grid-column: 1 / -1;
  justify-content: flex-end;
  gap: 8px;
}
```

Use existing input/select/checkbox button styles; do not introduce a new visual token。

- [ ] **Step 7: Run GREEN**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx
```

Expected: all tests PASS。

- [ ] **Step 8: Commit**

```bash
git add \
  frontend/src/api/types.ts \
  frontend/src/copy/zhCN.ts \
  frontend/src/components/workbench/RecognitionSummary.tsx \
  frontend/src/components/workbench/RecognitionSummary.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/styles/workbench.css
git commit -m "feat: list pending sources with inspection items"
```

## Task 4: Wire Workbench Save Flow And Retire CoverageReviewPanel

**Files:**
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Delete: `frontend/src/components/review/CoverageReviewPanel.tsx`
- Delete: `frontend/src/components/review/CoverageReviewPanel.test.tsx`
- Delete: `frontend/src/styles/coverage-review.css`

- [ ] **Step 1: Rewrite the existing source-only workbench test to describe the replacement**

Replace the current
`source-only coverage 可通过中文审核入口保存并解除冻结前置项` test with:

```typescript
test("source-only coverage 在统一列表中添加为真实检验项并保存", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const items = [{
    item_id: "item-1",
    item_type: "thread" as const,
    raw_text: "M6",
    balloon_required: true,
    requires_confirmation: false,
    active: true,
  }];
  render(
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[]}
      sources={[{
        id: "hidden-source-id",
        pageIndex: 0,
        bbox: [60, 70, 150, 84],
        rawText: "技术要求：去除毛刺",
      }]}
      balloons={[]}
      items={items}
      workingCopy={{
        id: "hidden-working-id",
        project_id: "hidden-project-id",
        raw_result_id: "hidden-result-id",
        version: 4,
        items,
        coverage: {
          blocking_count: 0,
          review_required_count: 1,
          entries: [{
            observation_id: "hidden-observation-id",
            source_location_id: "hidden-source-id",
            candidate_id: null,
            disposition: "ambiguous",
            coordinates: [60, 70, 150, 84],
            requires_confirmation: true,
          }],
        },
        numbering_stale: false,
        items_frozen_at: null,
        items_frozen_by: null,
        items_frozen_version: null,
      }}
      onSave={onSave}
      onFreeze={vi.fn()}
      onGenerate={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );

  expect(screen.queryByRole("region", { name: "来源待确认" })).toBeNull();
  const sourceRow = screen.getByRole("row", { name: /技术要求：去除毛刺/ });
  fireEvent.click(sourceRow);
  expect(screen.getByTestId("source-hidden-source-id").getAttribute("data-selected"))
    .toBe("true");
  fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
    target: { value: "general_requirement" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));
  fireEvent.click(screen.getByRole("button", { name: "保存审核修改" }));

  await waitFor(() => {
    expect(onSave).toHaveBeenCalledWith({
      type: "promote_source",
      observation_id: "hidden-observation-id",
      raw_text: "技术要求：去除毛刺",
      item_type: "general_requirement",
      scope: "local_feature",
      balloon_required: true,
      page_index: 0,
    });
  });
});
```

- [ ] **Step 2: Run RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionWorkbench.test.tsx
```

Expected: FAIL because `CoverageReviewPanel` still renders and workbench does not pass
pending sources to the table。

- [ ] **Step 3: Derive pending source rows once in InspectionWorkbench**

Import `PendingSourceReview` from `InspectionItemTable` and add:

```typescript
const pendingSources = useMemo<PendingSourceReview[]>(() => {
  if (workingCopy === undefined) return [];
  return (workingCopy.coverage.entries ?? [])
    .filter(
      (entry) =>
        entry.requires_confirmation === true
        && (entry.candidate_id === null || entry.candidate_id === undefined),
    )
    .map((entry) => {
      const source = sources.find(
        (candidate) => candidate.id === entry.source_location_id,
      );
      return {
        observationId: entry.observation_id,
        sourceId: entry.source_location_id,
        rawText: source?.rawText?.trim() || zhCN.workbench.unknown,
        coordinates: entry.coordinates,
        pageIndex: source?.pageIndex,
      };
    });
}, [sources, workingCopy?.coverage.entries]);
```

Pass `pendingSourceCount={pendingSources.length}` to `RecognitionSummary`。

Pass to `InspectionItemTable`:

```tsx
pendingSources={pendingSources}
selectedSourceId={selectedSourceId}
onSelectSource={(sourceId) => {
  setSelectedItemId(undefined);
  setSelectedSourceId(sourceId);
  setSelectedBalloonId(undefined);
  const source = sources.find((candidate) => candidate.id === sourceId);
  setPageIndex(source?.pageIndex ?? pageIndex);
}}
```

Keep `selectItem()` clearing `selectedSourceId`。Do not auto-select the first source; the
normal first active item remains the initial selection。

- [ ] **Step 4: Delete the old panel and copy**

Remove the import/render of `CoverageReviewPanel` from
`InspectionWorkbench.tsx`。Delete the component, its test and its CSS file。Remove the
entire `zhCN.coverageReview` object after no consumers remain。

Run:

```bash
rg -n "CoverageReviewPanel|coverageReview|coverage-review|来源待确认" frontend/src
```

Expected: no output。

- [ ] **Step 5: Run GREEN plus frontend regression**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: all tests PASS and build exits 0。

- [ ] **Step 6: Commit**

```bash
git add \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/copy/zhCN.ts
git add -u \
  frontend/src/components/review/CoverageReviewPanel.tsx \
  frontend/src/components/review/CoverageReviewPanel.test.tsx \
  frontend/src/styles/coverage-review.css
git commit -m "refactor: converge source and item review"
```

## Task 5: Bind The Durable Contract, Verify Runtime, Review, And Close

**Files:**
- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Review all files changed by Tasks 1～4

- [ ] **Step 1: Refine REV-004 without creating a second Owner**

Change only the `REV-004` stable contract cell to:

```text
Keep/exclude/edit/add/merge/split/confirmation/source/balloon-required 等命令保留
operation summary、provenance 和 lineage，不物理改写原始证据；source-only 决策必须
在同一 working-copy transaction 中原子提交 coverage disposition 与 item transition。
```

Do not change Owner, consumers, fields, compatibility rule or enforcement stage。

- [ ] **Step 2: Run focused backend and frontend gates**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_review_schema.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: zero failures; build exits 0。

- [ ] **Step 3: Run the wider review regression**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_review_schema.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_version.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_operator_audit.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
```

Expected: zero failures。

- [ ] **Step 4: Run authenticated localhost Chrome smoke**

Use the existing `127.0.0.1:3000` runtime only after confirming it serves the current
source commit。Use an editing project with at least one real pending source；if none exists, create a
fresh local project by uploading an existing repository/test PDF through the real upload
flow rather than modifying DB rows。

Exercise:

1. independent “来源待确认” card is absent；
2. “全部” and “需人工处理” counts include pending sources；
3. selecting a source row jumps to its page and highlights its source box；
4. item type is required before “添加为检验项”；
5. command remains pending until “保存审核修改”；
6. after save, the row disappears and working-copy item count increases；
7. a second pending source can be ignored and becomes `non_inspection`；
8. freeze remains disabled while any pending source exists。

Capture a screenshot of the unified table state and inspect the current backend API
working-copy payload to confirm the UI and server agree。

- [ ] **Step 5: Run independent read-only review**

Reviewer scope:

- verify the old source-only resolve path is retired；
- verify promote/ignore are atomic and source eligibility is fail-closed；
- verify coordinates remain server-owned；
- verify pending sources cannot disappear without candidate/non-inspection disposition；
- verify normal item confirmation, freeze and export inputs remain unchanged；
- inspect exact diff and focused test output；
- return verdict `accept / accept with concerns / reject` with blocking and non-blocking
  findings。

Parent must reproduce any blocking claim before changing code。

- [ ] **Step 6: Resolve any reproduced review blocker with a new RED/GREEN cycle**

Only when Step 5 returns `reject` or a blocking concern that the parent reproduces:

- backend schema blocker → add the failing case to
  `backend/tests/contract/test_review_schema.py`, edit
  `backend/app/review/schemas.py`；
- backend transition/integrity blocker → add the failing case to
  `backend/tests/integration/test_review_operations.py`, edit
  `backend/app/review/service.py`；
- frontend list/selection/command blocker → add the failing case to
  `frontend/src/components/workbench/InspectionItemTable.test.tsx` or
  `InspectionWorkbench.test.tsx`, edit the matching component；
- styling-only blocker → reproduce it in Chrome at the same viewport, edit only
  `frontend/src/styles/workbench.css`。

Run the single new test first and record the expected RED, make the minimal fix, rerun
the focused Task 2 or Task 4 gate。Stage only the matching pair:

```bash
# schema finding
git add backend/tests/contract/test_review_schema.py backend/app/review/schemas.py

# backend transition finding
git add backend/tests/integration/test_review_operations.py backend/app/review/service.py

# frontend table finding
git add \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx

# frontend workbench finding
git add \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx

# styling finding
git add frontend/src/styles/workbench.css

# Run only after choosing exactly the applicable block above.
git commit -m "fix: close source review finding"
```

If the reviewer returns `accept` or only non-blocking concerns outside the approved
scope, this step makes no code change and no commit。

- [ ] **Step 7: Run final verification after review fixes**

Run fresh:

```bash
git diff --check
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_review_schema.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/RecognitionSummary.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: `git diff --check` clean, zero test failures, build exits 0。

- [ ] **Step 8: Commit the durable contract projection**

Stage only task-owned paths:

```bash
git add docs/contracts/MAIN_CONTRACT_MATRIX.md
git commit -m "docs: bind atomic source review contract"
```

Do not include implementation review fixes in this docs commit；Step 6 owns their
separate RED/GREEN commit。Do not stage `.env.example`、`.gitignore`、`AGENTS.md`、
`compose.yaml`、`.local/`、`__pycache__/` or `frontend/test-results/`。

## Completion Checklist

- [ ] `CoverageReviewPanel` code, test, CSS and copy have no remaining consumers。
- [ ] Source-only `resolve_confirmation` is rejected fail-closed。
- [ ] Promote creates one active export-consumed item and one candidate coverage entry。
- [ ] Ignore creates no item and one non-inspection coverage entry。
- [ ] Both commands write one version increment and one operation record。
- [ ] Pending source count matches unified list and freeze state。
- [ ] Normal item review/SIP/pagination/selection tests remain green。
- [ ] Browser smoke uses current source/runtime and a real pending-source project。
- [ ] Independent reviewer has no unresolved blocking finding。
- [ ] Every task commit stages only owned files。
