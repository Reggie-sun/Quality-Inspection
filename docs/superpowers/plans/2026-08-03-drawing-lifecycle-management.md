# Drawing Lifecycle Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在服务端图纸列表提供安全的“重新识别”和“删除图纸”能力，并保证新识别失败不破坏旧结果、删除后所有产品入口不可再访问。

**Architecture:** `ProjectLifecycleService` 是 lifecycle status、version lineage、promotion、failure 和 tombstone 的唯一 Owner。重新识别复用 immutable source `StoredFile`，创建隐藏 successor，并在 working copy 成功后原子切换 active Project；删除只写产品侧 tombstone，保留内部引用和审计数据。Frontend 在既有列表行主操作旁提供 `⋯` 菜单和两个确认框，通过 typed `ProjectApi` 调用稳定 API。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、PostgreSQL、Celery、pytest、React 18、TypeScript、Vitest、Testing Library、OpenAPI TypeScript、Chrome MCP。

## Global Constraints

- Selected lane: `Heavy`。
- Selected plan: `docs/superpowers/plans/2026-08-03-drawing-lifecycle-management.md`。
- Selection evidence: 用户于 2026-08-03 批准 `docs/superpowers/specs/2026-08-03-drawing-lifecycle-management-design.md` 并选择 A 继续 TDD plan 与实施。
- Validation action: `continue -> implement -> independent review -> Chrome MCP smoke`。
- Writer ownership and order: 主线程按 Task 1～8 顺序写入；每个 file group 同时只有一个 writer。独立 reviewer 只读，必须在 Task 7 后派发。
- Next verification: Task 1 首先运行 lifecycle migration/model 的失败测试，确认因字段和 migration 缺失而 RED。
- 用户原有 `.agent/bug-memory.md` 与两个 `__pycache__` dirty files 不在 allowed paths，不得修改、stage 或 commit。
- Lifecycle 唯一 Owner 固定为 `backend/app/projects/lifecycle.py::ProjectLifecycleService`；其他模块不得直接提交 lifecycle state transition。
- 既有 `Project.state` 继续拥有 processing workflow phase；`lifecycle_status` 只拥有产品可见性和版本 lineage。
- 全新上传与失败页 File retry 旧路径执行 `preserve`：仍是首次 intake canonical consumer，不与重新识别形成第二 Owner。
- 重新识别只复用同一 immutable source PDF，不复制 predecessor 的 review、balloon、reviewed result 或 export。
- 新 successor working copy 成功前 predecessor 保持 `active`；失败只影响 successor。
- 删除必须是产品侧 tombstone，不得物理删除 Project、StoredFile、结果、导出或审计记录，不提供 undelete。
- `superseded` 与 `deleted` 对所有正式产品入口返回 `404 project_not_found`；frontend 隐藏不能替代 backend guard。
- API operation IDs 固定为 `QI-API-PRJ-008` 和 `QI-API-PRJ-009`。
- 重新识别确认文案固定为：`系统将使用当前识别能力重新处理原始 PDF。新结果成功前，当前版本仍可继续使用；成功后将切换到新版本。`
- 删除确认文案固定为：`删除后，这张图纸将从图纸列表和工作区永久移除，无法恢复。系统仅按审计和数据完整性要求保留内部记录。`
- Rollback 后第一项验证：对 migration 前已知 active project 调用 `GET /api/v1/projects/{project_id}/status`，必须继续返回成功；只有实际 rollback 时运行。

---

### Task 1: Project Lifecycle Schema And Migration

**Files:**
- Create: `backend/alembic/versions/0014_project_lifecycle.py`
- Modify: `backend/app/projects/models.py:1-47`
- Modify: `backend/alembic/env.py:1-18`
- Test: `backend/tests/integration/test_project_lifecycle_schema.py`
- Test: `backend/tests/integration/test_schema.py:90-120`

**Interfaces:**
- Consumes: 既有 `Project.id`, `Project.state`, `Project.source_filename` 和 migration head `0013`。
- Produces: `ProjectLifecycleStatus(StrEnum)`；`Project.lifecycle_status: str`；`Project.predecessor_project_id: UUID | None`；`Project.deleted_at: datetime | None`；migration revision `0014`。

- [ ] **Step 1: Write the failing model and migration tests**

```python
def test_project_lifecycle_model_defaults_catalog_projects_to_active() -> None:
    project = Project(source_filename="drawing.pdf")
    assert project.lifecycle_status == ProjectLifecycleStatus.ACTIVE
    assert project.predecessor_project_id is None
    assert project.deleted_at is None


def test_project_lifecycle_migration_is_attached_to_current_head() -> None:
    migration = _load_migration("0014_project_lifecycle.py")
    assert migration.revision == "0014"
    assert migration.down_revision == "0013"
```

在 PostgreSQL transaction fixture 中增加 upgrade assertions：catalog row backfill 为 `active`、无 filename row 为 `unlisted`、self predecessor 和 invalid deleted timestamp 被 constraint 拒绝、同一 predecessor 的第二个 `reprocessing` successor 被 partial unique index 拒绝。增加 downgrade assertion：存在非初始 lifecycle truth 时 `downgrade()` 抛出 `RuntimeError`。

同步扩展既有 exact project schema assertion，要求新增且仅新增 `lifecycle_status`、`predecessor_project_id`、`deleted_at` 三列，并验证 lifecycle column non-null/default 与 self foreign key。

- [ ] **Step 2: Run tests to verify RED**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_project_lifecycle_schema.py -q`

Expected: FAIL，因为 `ProjectLifecycleStatus`、model columns 和 migration `0014` 尚不存在。

- [ ] **Step 3: Implement the lifecycle model and migration**

```python
class ProjectLifecycleStatus(StrEnum):
    UNLISTED = "unlisted"
    ACTIVE = "active"
    REPROCESSING = "reprocessing"
    REPROCESS_FAILED = "reprocess_failed"
    SUPERSEDED = "superseded"
    DELETED = "deleted"
```

Model 使用字符串 column 与 self foreign key；migration 先 nullable add/backfill，再改为 non-null，并建立 check constraints 与：

```python
sa.Index(
    "uq_projects_reprocessing_predecessor",
    "predecessor_project_id",
    unique=True,
    postgresql_where=sa.text("lifecycle_status = 'reprocessing'"),
)
```

`downgrade()` 先查询是否存在非 `active/unlisted` row 或非空 predecessor/deleted timestamp；存在即抛错，禁止丢失 lifecycle truth。

- [ ] **Step 4: Run tests to verify GREEN**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_project_lifecycle_schema.py backend/tests/integration/test_schema.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0014_project_lifecycle.py backend/alembic/env.py backend/app/projects/models.py backend/tests/integration/test_project_lifecycle_schema.py backend/tests/integration/test_schema.py
git commit -m "feat: add project lifecycle schema"
```

### Task 2: Lifecycle Owner, Source Resolution, And Catalog Visibility

**Files:**
- Create: `backend/app/projects/lifecycle.py`
- Create: `backend/app/projects/source.py`
- Modify: `backend/app/projects/service.py:51-218`
- Modify: `backend/app/projects/router.py:382-400`
- Test: `backend/tests/integration/test_project_lifecycle_service.py`
- Test: `backend/tests/integration/test_project_catalog_api.py`

**Interfaces:**
- Consumes: Task 1 `ProjectLifecycleStatus` fields、`StoredFile`、`RecognitionPreviewRevision`、`AutomaticResult`、`ReviewWorkingCopy`、`ReviewLock`、`ProjectDispatcher(project_id, source_ref, logical_task_key)`。
- Produces: `project_source_file(session, project_id) -> StoredFile`；`ProjectLifecycleService.start_reprocess(project_id, *, recognition_mode, recognition_router_version) -> Project`；`mark_reprocess_failed(project_id) -> None`；`promote_reprocessed_project(project_id) -> None`；`delete_project(project_id) -> None`；`require_access(project_id, access: ProjectAccess) -> Project`。

- [ ] **Step 1: Write failing lifecycle behavior tests**

```python
def test_start_reprocess_creates_hidden_successor_and_preserves_predecessor(ctx):
    successor = ctx.service.start_reprocess(
        ctx.active.id,
        recognition_mode="qwen_layout_semantic",
        recognition_router_version="symbol-router/2",
    )
    assert successor.predecessor_project_id == ctx.active.id
    assert successor.lifecycle_status == "reprocessing"
    assert ctx.reload(ctx.active.id).lifecycle_status == "active"
    assert ctx.dispatched == [(str(successor.id), ctx.source.resource_ref,
                               f"product-process:{successor.id}")]


def test_delete_tombstones_without_deleting_related_rows(ctx):
    ctx.service.delete_project(ctx.active.id)
    assert ctx.reload(ctx.active.id).lifecycle_status == "deleted"
    assert ctx.reload(ctx.active.id).deleted_at is not None
    assert ctx.session.get(StoredFile, ctx.source.id) is not None
```

同文件增加：source unavailable、duplicate reprocessing、dispatch failure、failed successor permits retry、promotion requires working copy、idempotent promotion、delete blocked by active successor、delete blocked by unexpired review lock、expired lock does not block、deleted/superseded access guard 的 tests。Catalog integration 增加仅 `active` 可列出/打开的 assertions。

- [ ] **Step 2: Run tests to verify RED**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_project_lifecycle_service.py backend/tests/integration/test_project_catalog_api.py -q`

Expected: FAIL，因为 lifecycle Owner 和 active-only catalog filter 尚不存在。

- [ ] **Step 3: Implement immutable source resolver**

将 `router.py::_source_pdf_file` 的 database lookup 移到 `projects/source.py::project_source_file`。解析顺序保持 preview revision 优先、terminal automatic result 次之；不存在 Project 抛 `ProjectNotFound`，无法取得 PDF 抛 `ProjectSourceUnavailable`。Router 只负责 storage read 与 error mapping，避免 lifecycle Owner import router。

- [ ] **Step 4: Implement `ProjectLifecycleService`**

实现 `ProjectAccess` 的 `ACTIVE / PROCESSING_READ / STATUS_READ` 三个值，以及 Interfaces 中列出的五个 public methods。所有 transition 使用 SQLAlchemy `with_for_update()` row lock；commit/rollback 由 Owner 完成。Dispatch 在 successor DB commit 后执行；dispatch exception 进入 `reprocess_failed` 并抛 `ProjectDispatchFailed`。所有同时涉及 lineage 两行的操作固定先锁 predecessor、再锁 successor；promotion 必须在取得两把锁后重新验证 working copy 与双方 lifecycle 状态，并允许已完成状态幂等返回。Delete 使用 PostgreSQL `func.now()` 判断 review lock expiry，只写 tombstone。

- [ ] **Step 5: Make intake and catalog lifecycle-aware**

`ProjectIntakeService.create_pdf()` 显式创建 `lifecycle_status=active`；`ProjectCatalogService.list_projects()` 和 `mark_opened()` 附加 `lifecycle_status == active`，不得继续以 `source_filename IS NOT NULL` 单独决定可见性。

- [ ] **Step 6: Run tests to verify GREEN**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_project_lifecycle_service.py backend/tests/integration/test_project_catalog_api.py backend/tests/integration/test_project_intake_api.py -q`

Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/app/projects/lifecycle.py backend/app/projects/source.py backend/app/projects/service.py backend/app/projects/router.py backend/tests/integration/test_project_lifecycle_service.py backend/tests/integration/test_project_catalog_api.py backend/tests/integration/test_project_intake_api.py
git commit -m "feat: own project lifecycle transitions"
```

### Task 3: Processing Promotion And Failure Hooks

**Files:**
- Modify: `backend/app/processing/tasks.py:168-252`
- Test: `backend/tests/integration/test_processing_entry_task.py`

**Interfaces:**
- Consumes: Task 2 `ProjectLifecycleService.promote_reprocessed_project(project_id)` 与 `mark_reprocess_failed(project_id)`。
- Produces: `inventory_project` 的 existing-result 与 fresh-pipeline 两条 success path 均在 working copy 存在后 promotion；terminal exception 只将 reprocessing successor 标记失败。

- [ ] **Step 1: Write failing task transition tests**

```python
def test_existing_result_path_promotes_reprocessed_project(task_context):
    result = inventory_project.run(
        str(task_context.successor.id),
        task_context.source.resource_ref,
        f"product-process:{task_context.successor.id}",
    )
    assert result == task_context.result_ref
    assert task_context.reload(task_context.successor.id).lifecycle_status == "active"
    assert task_context.reload(task_context.predecessor.id).lifecycle_status == "superseded"


def test_pipeline_failure_marks_only_successor_failed(task_context):
    with pytest.raises(RuntimeError, match="recognition failed"):
        inventory_project.run(
            str(task_context.successor.id),
            task_context.source.resource_ref,
            f"product-process:{task_context.successor.id}",
        )
    assert task_context.reload(task_context.successor.id).lifecycle_status == "reprocess_failed"
    assert task_context.reload(task_context.predecessor.id).lifecycle_status == "active"
```

Fresh-pipeline success 另写一条 test，避免只覆盖 idempotency shortcut。

- [ ] **Step 2: Run tests to verify RED**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_processing_entry_task.py -q`

Expected: FAIL，successor 不会 promotion，exception 也不会写 lifecycle failure。

- [ ] **Step 3: Add lifecycle hooks without moving review ownership**

在两处 `ReviewService.create_from_raw(raw_result_id)` 成功返回后调用 promotion。用 task 顶层 `except Exception` 调用 `mark_reprocess_failed` 后原样 `raise`；Owner 对 normal active intake、already active 和 already failed 做安全 no-op。不得在 `ReviewService` 内写 lifecycle columns。

- [ ] **Step 4: Run tests to verify GREEN**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_processing_entry_task.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_task_idempotency.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/processing/tasks.py backend/tests/integration/test_processing_entry_task.py
git commit -m "feat: promote successful reprocessing"
```

### Task 4: Stable Lifecycle APIs And Product Access Guard

**Files:**
- Modify: `backend/app/projects/schemas.py:1-70`
- Modify: `backend/app/projects/router.py:57-400`
- Modify: `backend/app/review/router.py:39-320`
- Modify: `backend/app/balloons/router.py:38-210`
- Modify: `backend/app/exports/router.py:30-190`
- Modify: `backend/app/exports/service.py`
- Test: `backend/tests/integration/test_project_lifecycle_api.py`
- Test: `backend/tests/integration/test_project_workbench_api.py`
- Test: `backend/tests/integration/test_review_operations.py`
- Test: `backend/tests/integration/test_balloon_api.py`
- Test: `backend/tests/integration/test_excel_export.py`
- Test: `backend/tests/contract/test_openapi_contract.py`

**Interfaces:**
- Consumes: Task 2 lifecycle methods and `ProjectAccess` modes。
- Produces: `POST /api/v1/projects/{project_id}/reprocess` (`QI-API-PRJ-008`)；`DELETE /api/v1/projects/{project_id}` (`QI-API-PRJ-009`)；`ProjectReprocessResponse`；uniform deleted/superseded route rejection。

- [ ] **Step 1: Write failing API and guard tests**

```python
def test_reprocess_returns_new_processing_project(context):
    response = context.client.post(f"/api/v1/projects/{context.active.id}/reprocess")
    assert response.status_code == 202
    assert response.json() == {
        "project_id": str(context.successor_id()),
        "predecessor_project_id": str(context.active.id),
        "phase": "processing",
        "lifecycle_status": "reprocessing",
    }


def test_delete_removes_project_from_all_product_entry_points(context):
    assert context.client.delete(f"/api/v1/projects/{context.active.id}").status_code == 204
    for path in context.project_read_paths(context.active.id):
        response = context.client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_not_found"
```

在 review、balloon、export tests 中分别 tombstone fixture project，再证明 mutation/create/download 被 `404 project_not_found` 阻断。增加 reprocessing status/source/preview allowlist、reprocessing mutation rejection、reprocess conflict/source unavailable、delete lock/conflict/error envelope tests。

- [ ] **Step 2: Run tests to verify RED**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_project_lifecycle_api.py backend/tests/integration/test_project_workbench_api.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_balloon_api.py backend/tests/integration/test_excel_export.py backend/tests/contract/test_openapi_contract.py -q`

Expected: FAIL，新 routes、schemas、operation map 和 access guards 不存在。

- [ ] **Step 3: Add response schema and routes**

```python
class ProjectReprocessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID
    predecessor_project_id: uuid.UUID
    phase: Literal["processing"]
    lifecycle_status: Literal["reprocessing"]
```

Reprocess route 从 server settings 冻结 recognition identity，映射 lifecycle exceptions 到 spec 中的 `404/409/503`。Delete route 返回真正的 empty `Response(status_code=204)`，不得返回 JSON body。

- [ ] **Step 4: Apply lifecycle guard to every formal product entry**

Projects routes 使用：status=`STATUS_READ`；source/preview=`PROCESSING_READ`；open/workbench=`ACTIVE`。Review 和 balloons 的所有 project-scoped reads/writes 均要求 `ACTIVE`。Exports create 要求 active project；export get/download 从 `ExportJob.project_id` 反查并拒绝 deleted/superseded。Guard failure统一映射 `404 project_not_found`，不得泄漏 lifecycle state。

- [ ] **Step 5: Update operation contract map**

在 `FORMAL_OPERATIONS` 增加：

```python
("POST", "/api/v1/projects/{project_id}/reprocess"): "QI-API-PRJ-008",
("DELETE", "/api/v1/projects/{project_id}"): "QI-API-PRJ-009",
```

- [ ] **Step 6: Run tests to verify GREEN**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_project_lifecycle_api.py backend/tests/integration/test_project_workbench_api.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_balloon_api.py backend/tests/integration/test_excel_export.py backend/tests/contract/test_openapi_contract.py -q`

Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/app/projects/schemas.py backend/app/projects/router.py backend/app/review/router.py backend/app/balloons/router.py backend/app/exports/router.py backend/app/exports/service.py backend/tests/integration/test_project_lifecycle_api.py backend/tests/integration/test_project_workbench_api.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_balloon_api.py backend/tests/integration/test_excel_export.py backend/tests/contract/test_openapi_contract.py
git commit -m "feat: expose guarded project lifecycle APIs"
```

### Task 5: Typed Frontend Lifecycle Client

**Files:**
- Modify: `frontend/src/api/client.ts:1-63`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/features/projects/api.ts:1-91`
- Test: `frontend/src/features/projects/api.test.ts`

**Interfaces:**
- Consumes: Task 4 API paths and `ProjectReprocessResponse` transport。
- Produces: `deleteJson(path, signal?) -> Promise<void>`；`ProjectApi.reprocessProject(projectId, signal?) -> Promise<ProjectReprocessResult>`；`ProjectApi.deleteProject(projectId, signal?) -> Promise<void>`。

- [ ] **Step 1: Write failing client tests**

```typescript
it("reprocesses the encoded project id and maps its successor", async () => {
  fetchMock.mockResolvedValue(jsonResponse({
    project_id: NEW_ID,
    predecessor_project_id: OLD_ID,
    phase: "processing",
    lifecycle_status: "reprocessing",
  }, 202));
  await expect(reprocessProject(OLD_ID)).resolves.toEqual({
    projectId: NEW_ID,
    predecessorProjectId: OLD_ID,
  });
  expect(fetchMock).toHaveBeenCalledWith(
    `/api/v1/projects/${OLD_ID}/reprocess`,
    expect.objectContaining({ method: "POST" }),
  );
});


it("accepts an empty 204 delete response", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
  await expect(deleteProject(OLD_ID)).resolves.toBeUndefined();
});
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd frontend && npm test -- --run src/features/projects/api.test.ts`

Expected: FAIL，因为 methods 与 204-aware client 不存在。

- [ ] **Step 3: Implement minimal typed client**

`postJson` 保持现有 JSON semantics；新增专用 `deleteEmpty`，只在 `response.ok` 且 `204` 时返回，否则使用现有 error envelope decoder。扩展 `ProjectApi` fake contract，避免 UI 绕过 feature API 直接 fetch。

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd frontend && npm test -- --run src/features/projects/api.test.ts`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/types.ts frontend/src/features/projects/api.ts frontend/src/features/projects/api.test.ts
git commit -m "feat: add project lifecycle client"
```

### Task 6: Drawing Row Menu And Confirmation Dialogs

**Files:**
- Modify: `frontend/src/app/DrawingListScreen.tsx:1-176`
- Modify: `frontend/src/app/DrawingListScreen.test.tsx:1-140`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `ProjectListItem`。
- Produces: `DrawingListScreenProps.onReprocess(entry) -> Promise<void>`；`onDelete(entry) -> Promise<void>`；accessible row menu and modal state owned by `DrawingListScreen`。

- [ ] **Step 1: Write failing interaction tests**

```typescript
it("opens one accessible row menu beside continue", async () => {
  renderList();
  fireEvent.click(screen.getByRole("button", { name: "打开 A.pdf 的更多操作" }));
  const menu = screen.getByRole("menu", { name: "A.pdf 的图纸操作" });
  expect(within(menu).getByRole("menuitem", { name: "重新识别" })).not.toBeNull();
  expect(within(menu).getByRole("menuitem", { name: "删除图纸" })).not.toBeNull();
});


it("confirms reprocess with the approved safety copy", async () => {
  const onReprocess = vi.fn().mockResolvedValue(undefined);
  renderList({ onReprocess });
  openAction("A.pdf", "重新识别");
  expect(screen.getByRole("dialog", { name: "重新识别这张图纸？" })).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "开始重新识别" }));
  await waitFor(() => expect(onReprocess).toHaveBeenCalledWith(ENTRY_A));
});
```

增加 delete exact copy、cancel、Escape、outside close、one-menu-only、pending disable、rejected promise 保持 dialog 并显示安全 error 的 tests。断言真实 menu/dialog，不断言 mock component。

- [ ] **Step 2: Run tests to verify RED**

Run: `cd frontend && npm test -- --run src/app/DrawingListScreen.test.tsx`

Expected: FAIL，更多操作按钮、menu、dialogs 和 callbacks 不存在。

- [ ] **Step 3: Implement menu and dialog state**

保持“继续处理”为 primary row action；在同一 action cell 加 `⋯` button。使用原生 `role=menu/menuitem` 与 `role=dialog`, `aria-modal=true`, heading label。State 只包含 `openMenuProjectId`, `{kind, entry} | undefined`, `pending`, `actionError`；不建立通用 modal framework。

- [ ] **Step 4: Add scoped styles and approved copy**

只增加 `.drawing-list-actions`, `.drawing-list-menu`, `.drawing-action-dialog`, `.button--danger` 等本功能 selectors；窄屏下 action cell 允许换行但不改变表格其余布局。Error 只显示 `zhCN` 安全文案，不渲染 exception message。

- [ ] **Step 5: Run tests to verify GREEN**

Run: `cd frontend && npm test -- --run src/app/DrawingListScreen.test.tsx`

Expected: PASS，且 stderr 无 React act warning。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/DrawingListScreen.tsx frontend/src/app/DrawingListScreen.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles.css
git commit -m "feat: add drawing lifecycle actions"
```

### Task 7: App Orchestration And Contract Artifacts

**Files:**
- Modify: `frontend/src/app/QualityInspectionApp.tsx:128-330`
- Modify: `frontend/src/app/QualityInspectionApp.test.tsx`
- Modify: `backend/tests/contract/snapshots/api-v1.openapi.json`
- Modify: `frontend/src/api/generated.ts`
- Modify: `docs/contracts/API_SURFACE_INDEX.md`

**Interfaces:**
- Consumes: Task 5 ProjectApi methods、Task 6 callbacks、existing `setCurrentProjectId` 和 server catalog reload effect。
- Produces: reprocess success enters successor processing screen；delete success refreshes server catalog without optimistic removal；synchronized OpenAPI/generated types/index。

- [ ] **Step 1: Write failing app orchestration tests**

```typescript
test("重新识别成功后进入 successor processing", async () => {
  const api = apiWithOneDrawing();
  api.reprocessProject = vi.fn().mockResolvedValue({
    projectId: OTHER_PROJECT_ID,
    predecessorProjectId: PROJECT_ID,
  });
  render(<QualityInspectionApp api={api} pollIntervalMs={60_000} />);
  await openAndConfirm("服务端图纸.pdf", "重新识别", "开始重新识别");
  await waitFor(() => expect(sessionStorage.getItem("qi.current-project-id"))
    .toBe(OTHER_PROJECT_ID));
  expect(api.getProjectStatus).toHaveBeenCalledWith(
    OTHER_PROJECT_ID,
    expect.any(AbortSignal),
  );
});


test("删除成功后重新读取 catalog 而失败时保留图纸", async () => {
  const api = apiWithOneDrawing();
  api.deleteProject = vi.fn().mockResolvedValue(undefined);
  render(<QualityInspectionApp api={api} />);
  await openAndConfirm("服务端图纸.pdf", "删除图纸", "删除图纸");
  await waitFor(() => expect(api.listProjects).toHaveBeenCalledTimes(2));
});
```

增加 delete rejection test，证明 row 仍在且显示安全错误；更新所有 `fakeApi()` 完整实现新 methods。

- [ ] **Step 2: Run tests to verify RED**

Run: `cd frontend && npm test -- --run src/app/QualityInspectionApp.test.tsx`

Expected: FAIL，因为 callbacks 尚未传入，catalog reload token 不存在。

- [ ] **Step 3: Implement app callbacks**

`reprocessDrawing` await API 后写 successor session ID，并设置现有 processing screen；不修改 predecessor list projection。`deleteDrawing` await API 后增加 `catalogRevision`，让 list effect 重新请求；不得在 API resolve 前 filter local state。把两个 async callbacks传入 `DrawingListScreen`。

- [ ] **Step 4: Run frontend tests and build**

Run: `cd frontend && npm test -- --run src/app/QualityInspectionApp.test.tsx src/app/DrawingListScreen.test.tsx src/features/projects/api.test.ts`

Expected: PASS。

Run: `cd frontend && npm run build`

Expected: exit 0。

- [ ] **Step 5: Regenerate stable contract artifacts**

Run: `cd backend && micromamba run -n qi-p0 python -m app.contracts.openapi --baseline tests/contract/snapshots/api-v1.openapi.json --write`

Expected: 输出 `openapi_snapshot_written=tests/contract/snapshots/api-v1.openapi.json`；不得手改 generated schema 来绕过 generator。

Run: `cd frontend && npm run api:generate`

更新 `docs/contracts/API_SURFACE_INDEX.md` 中 projects operation table，加入两个固定 IDs、method/path 和 spec owner。

- [ ] **Step 6: Run contract drift gates**

Run: `API_CONTRACT_BASE_REF=775c79e make check-api-contracts`

Expected: PASS。

Run: `make check-contracts`

Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/QualityInspectionApp.tsx frontend/src/app/QualityInspectionApp.test.tsx backend/tests/contract/snapshots/api-v1.openapi.json frontend/src/api/generated.ts docs/contracts/API_SURFACE_INDEX.md
git commit -m "feat: connect drawing lifecycle workflow"
```

### Task 8: Independent Review, Full Verification, And Chrome MCP Smoke

**Files:**
- Modify only if review or verification exposes a scoped defect; write a failing regression test before each correction.
- Read: all files changed by Tasks 1～7。

**Interfaces:**
- Consumes: complete implementation diff and current runtime。
- Produces: independent verdict、focused/full test evidence、headed browser evidence、final clean scoped commit state。

- [ ] **Step 1: Run focused backend and frontend suites**

Run: `micromamba run -n qi-p0 pytest backend/tests/integration/test_project_lifecycle_schema.py backend/tests/integration/test_project_lifecycle_service.py backend/tests/integration/test_project_lifecycle_api.py backend/tests/integration/test_processing_entry_task.py backend/tests/integration/test_project_catalog_api.py backend/tests/contract/test_openapi_contract.py -q`

Expected: PASS。

Run: `cd frontend && npm test -- --run src/features/projects/api.test.ts src/app/DrawingListScreen.test.tsx src/app/QualityInspectionApp.test.tsx`

Expected: PASS，no warnings。

- [ ] **Step 2: Run repository gates**

Run: `make check-contracts`

Expected: PASS。

Run: `make test-backend`

Expected: PASS。

Run: `make test-frontend`

Expected: PASS。

Run: `cd frontend && npm run build`

Expected: exit 0。

- [ ] **Step 3: Perform independent read-only review**

Reviewer 必须给出 `accept / accept with concerns / reject`，检查：唯一 Owner、old upload retry preserved、promotion 原子性、dispatch failure、delete/reprocess race、expired/active locks、所有正式 route guard、OpenAPI drift、frontend non-optimistic delete、tests 是否覆盖真实 failure mode。父 agent 直接核对每项 blocking claim 后决定是否修复。

- [ ] **Step 4: Use `github-oss-fusion` for a bounded prior-art check**

只检索公开成熟项目中 soft-delete tombstone、successor promotion、FastAPI destructive confirmation/access guard 的小型实现模式。不得复制大段实现；仅在发现能降低当前 race/error-handling 风险且 license-safe 时融合最小思想，并为任何融合写失败测试。记录搜索、 inspected repositories、fused/skipped 理由和验证。

- [ ] **Step 5: Use `auto-feature-smoke-test` and Chrome MCP**

在真实 headed runtime 验证：每行 `⋯` 与继续处理并存；菜单唯一打开；两个确认框文案与 Escape；reprocess 只发一次 `POST /api/v1/projects/{project_id}/reprocess` 并进入 successor；成功前 predecessor 仍可见；delete 只发一次 `DELETE /api/v1/projects/{project_id}`，成功后刷新列表；旧 deep-link/API 返回 404；console 无新增 error。

- [ ] **Step 6: Review final diff and commit scoped fixes**

Run: `git status --short && git diff --check && git diff --stat 775c79e..HEAD`

只 stage review/smoke 产生且属于本任务的 exact files：

```bash
git add backend/alembic/versions/0014_project_lifecycle.py backend/alembic/env.py backend/app/projects/models.py backend/app/projects/lifecycle.py backend/app/projects/source.py backend/app/projects/service.py backend/app/projects/schemas.py backend/app/projects/router.py backend/app/processing/tasks.py backend/app/review/router.py backend/app/balloons/router.py backend/app/exports/router.py backend/app/exports/service.py backend/tests/integration/test_project_lifecycle_schema.py backend/tests/integration/test_project_lifecycle_service.py backend/tests/integration/test_project_lifecycle_api.py backend/tests/integration/test_project_catalog_api.py backend/tests/integration/test_project_intake_api.py backend/tests/integration/test_processing_entry_task.py backend/tests/integration/test_project_workbench_api.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_balloon_api.py backend/tests/integration/test_excel_export.py backend/tests/contract/test_openapi_contract.py backend/tests/contract/snapshots/api-v1.openapi.json frontend/src/api/client.ts frontend/src/api/types.ts frontend/src/api/generated.ts frontend/src/features/projects/api.ts frontend/src/features/projects/api.test.ts frontend/src/app/DrawingListScreen.tsx frontend/src/app/DrawingListScreen.test.tsx frontend/src/app/QualityInspectionApp.tsx frontend/src/app/QualityInspectionApp.test.tsx frontend/src/copy/zhCN.ts frontend/src/styles.css docs/contracts/API_SURFACE_INDEX.md
git commit -m "fix: close drawing lifecycle review findings"
```

如果没有修复 diff，不创建空 commit。用户原有 dirty files 保持 unstaged。

- [ ] **Step 7: Record completion truth**

仅当 focused/full tests、contract gates、build、independent review 和 Chrome MCP smoke 都有 fresh passing evidence 时声明完成。任何 live runtime identity mismatch、migration blocker、guard coverage 缺口或 review reject 都报告为 blocker，不用文档或旧 receipt 覆盖。
