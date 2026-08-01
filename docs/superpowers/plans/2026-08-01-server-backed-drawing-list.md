# Server-Backed Drawing List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 origin-local 图纸目录替换为 PostgreSQL-backed catalog，使 loopback、LAN 和 public hostname 显示同一组项目。

**Architecture:** `Project` aggregate 新增 nullable catalog visibility filename 和 authoritative timestamps；`GET /projects` 读取 catalog，`POST /projects/{id}/open` 更新全局最近打开时间。Frontend 只消费 server catalog，删除 `localDrawingRegistry` active path；部署后用显式事务回填当前 4 个真实项目。

**Tech Stack:** FastAPI, SQLAlchemy 2, PostgreSQL, Alembic, Pydantic, React 19, TypeScript, Vitest, OpenAPI

## Global Constraints

- Selected lane: `Heavy`。
- Selected plan: 本文件。
- Selection evidence: 2026-08-01 用户选择永久 server-backed list 方案 A。
- Validation action: `replan -> implement -> review`。
- Owner after: Project aggregate owns catalog metadata；database-only `ProjectCatalogService` owns list/open activity；frontend is projection only。
- Old path: `remove` active `localDrawingRegistry` module and all consumers；do not clear browser storage key so rollback remains possible。
- Visibility: only `Project.source_filename IS NOT NULL` rows enter catalog；do not expose all 129 historical/test projects。
- Security: current anonymous QA catalog is intentionally global; do not claim account or department isolation。
- Allowed paths: the spec/plan; `backend/app/projects/{models,schemas,service,router}.py`; `backend/alembic/versions/0013_project_catalog.py`; focused backend integration/contract/schema tests and OpenAPI snapshot; `docs/contracts/API_SURFACE_INDEX.md`; generated frontend API types; `frontend/src/api/{client,types}.ts`; `frontend/src/features/projects/api.ts` and test; `frontend/src/app/{QualityInspectionApp,DrawingListScreen}.tsx` and tests; `frontend/src/main.tsx` and test; remove `frontend/src/app/localDrawingRegistry.ts` and its test。
- Forbidden overlap: do not modify main's dirty workbench/SIP files or `frontend/src/copy/zhCN.ts`。
- Rollback: revert feature commit, downgrade to `0012`, then first verify known project status API before checking restored local list。
- OSS fusion: borrow only response envelope/count, deterministic DB ordering, explicit response schema and integration-test ideas from inspected MIT FastAPI examples; do not copy implementations or add dependencies。

---

### Task 1: Persist Catalog Metadata And Migration

**Files:**
- Modify: `backend/app/projects/models.py`
- Create: `backend/alembic/versions/0013_project_catalog.py`
- Modify: `backend/tests/integration/test_project_intake_api.py`

**Interfaces:**
- Consumes: multipart `UploadFile.filename`, existing `ProjectIntakeService.create_pdf()` transaction.
- Produces: `Project.source_filename: str | None`, `created_at: datetime`, `last_opened_at: datetime`, and `create_pdf(..., source_filename: str)`.

- [x] **Step 1: RED — assert safe filename and timestamps are persisted**

Extend the successful intake integration test to assert `../../credential-secret.pdf` becomes `credential-secret.pdf`, both timestamps are timezone-aware, and `last_opened_at >= created_at`. This catches path leakage and missing catalog persistence.

- [x] **Step 2: Run RED test**

Run the focused test against an isolated PostgreSQL upgraded to current head. Expected: FAIL because the `Project` fields and `create_pdf` argument do not exist.

- [x] **Step 3: GREEN — add migration and minimal model/service intake fields**

Migration `0013` adds:

```python
sa.Column("source_filename", sa.String(length=255), nullable=True)
sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
sa.Column("last_opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
```

Normalize filename with `source_filename.replace("\\\\", "/").rsplit("/", 1)[-1].strip()[:255] or "未命名图纸.pdf"`. Set it on the same new `Project` before the existing commit.

- [x] **Step 4: Verify migration and intake GREEN**

Run upgrade `0012 -> 0013`, the focused intake test, downgrade `0013 -> 0012`, and upgrade again. Expected: schema transitions succeed and the test passes.

---

### Task 2: Add Stable Catalog Read And Open APIs

**Files:**
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/projects/router.py`
- Create: `backend/tests/integration/test_project_catalog_api.py`
- Modify: `backend/tests/contract/test_openapi_contract.py`
- Modify: `backend/tests/contract/snapshots/api-v1.openapi.json`
- Modify: `docs/contracts/API_SURFACE_INDEX.md`
- Modify: `frontend/src/api/generated.ts`

**Interfaces:**
- Produces: `ProjectListItemResponse`, `ProjectListResponse`, `GET /api/v1/projects` (`QI-API-PRJ-006`), `POST /api/v1/projects/{project_id}/open` (`QI-API-PRJ-007`).
- Ordering: `last_opened_at DESC, id DESC`; filter `source_filename IS NOT NULL`.

- [x] **Step 1: RED — list visibility/order/count**

Create real DB rows for two catalog projects and one `source_filename=None` history row. Assert GET returns only two items in literal last-opened order with `count: 2`.

- [x] **Step 2: RED — open activity and failure path**

Assert POST open updates the selected row to a later server timestamp and makes it first; assert a missing or non-catalog UUID returns sanitized `404 project_not_found`.

- [x] **Step 3: Run RED API tests**

Expected: FAIL with route missing / `405` before implementation.

- [x] **Step 4: GREEN — implement schemas, service methods and routes**

Use explicit Pydantic response models. `list_projects()` performs the filtered ordered query and returns an envelope. `mark_opened()` loads a catalog row, raises `ProjectNotFound` otherwise, updates `last_opened_at` using server UTC time, commits, refreshes and returns the item.

- [x] **Step 5: Verify focused backend GREEN**

Run catalog and intake/status integration tests. Expected: all pass, including hidden-history and not-found paths.

- [x] **Step 6: Update API contract projections**

Add both exact operations to `EXPECTED_OPERATIONS` and `API_SURFACE_INDEX.md`; regenerate the OpenAPI snapshot and `frontend/src/api/generated.ts` with repository commands, then run `API_CONTRACT_BASE_REF=8dc07d5 make check-api-contracts`.

---

### Task 3: Replace Frontend Local Registry With Server Projection

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/features/projects/api.ts`
- Modify: `frontend/src/features/projects/api.test.ts`
- Modify: `frontend/src/app/QualityInspectionApp.tsx`
- Modify: `frontend/src/app/QualityInspectionApp.test.tsx`
- Modify: `frontend/src/app/DrawingListScreen.tsx`
- Modify: `frontend/src/app/DrawingListScreen.test.tsx`
- Delete: `frontend/src/app/localDrawingRegistry.ts`
- Delete: `frontend/src/app/localDrawingRegistry.test.ts`

**Interfaces:**
- Produces: `listProjects(signal?)`, `markProjectOpened(projectId, signal?)`, and `ProjectApi` methods backed by generated schemas.
- Consumes: `ProjectListItemResponse` mapped to UI camelCase at the feature API boundary.

- [x] **Step 1: RED — feature API requests**

Add tests asserting `listProjects()` GETs `/api/v1/projects` and maps literal snake_case timestamps/name; assert `markProjectOpened()` POSTs the encoded `/api/v1/projects/{id}/open` path.

- [x] **Step 2: RED — app ignores localStorage and loads server list**

Seed `qi.drawing-list.v1` with a fake local entry, return a different server item from `listProjects`, and assert only the server item renders. Add a list rejection case that renders a safe warning instead of the empty-state claim.

- [x] **Step 3: Run RED frontend tests**

Expected: FAIL because `ProjectApi` lacks list/open methods and the app still reads local storage.

- [x] **Step 4: GREEN — implement transport and app loading/open flow**

Load server items whenever list screen becomes active. Remove `read/register/touchLocalDrawing` calls. On open, set current project immediately and fire the server activity update without blocking navigation; refresh from the server when returning to list.

- [x] **Step 5: Remove old registry active path**

Delete the registry implementation/test and verify `rg -n "localDrawingRegistry|qi.drawing-list.v1" frontend/src` has no production matches except the regression test that proves the old key is ignored.

- [x] **Step 6: Verify frontend GREEN**

Run focused feature/list/app tests, then all frontend tests and `npm --prefix frontend run build`.

---

### Task 4: Migrate Live Data And Prove Cross-Origin Runtime

> Deployment gate: execute Task 5 Steps 1–3 first. Task 4 is forbidden until the independent reviewer accepts the committed feature diff; after Task 4, finish with Task 5 Step 4.

**Files:**
- Modify: `docs/superpowers/plans/2026-08-01-server-backed-drawing-list.md` checkboxes only after evidence.

**Interfaces:**
- Consumes: live PostgreSQL at migration `0012`, the four exact project IDs in the spec.
- Produces: exactly four visible catalog rows in the live database.

- [x] **Step 1: Preflight live migration identity**

Confirm current DB Alembic head is `0012`, each of the four IDs exists, and no catalog columns exist yet. If any assertion fails, stop without mutation.

- [x] **Step 2: Upgrade schema and backfill in one checked transaction**

Run `alembic upgrade 0013`, then one SQL transaction that updates the four exact IDs and aborts unless the affected/visible row count is exactly four. Use stored-file `created_at` for each selected project's `created_at` and the spec's exact `last_opened_at` values.

- [x] **Step 3: Activate current main runtime after merge**

Fast-forward/merge the reviewed branch into main without touching unrelated dirty files, restart `make dev-local-api` and `make dev-local-frontend`, and verify listener identity.

- [x] **Step 4: API and browser cross-origin smoke**

Verify GET list returns the same four IDs/names through loopback, LAN and public hostname. Open loopback and public pages in browser automation; assert both render `共 4 份图纸`, the same four filenames, working status calls and no console errors.

- [x] **Step 5: Failure-path and rollback proof**

Against an isolated test database, prove a non-catalog project is absent and POST open for it returns sanitized 404. Verify migration downgrade/upgrade, but do not downgrade the live database unless rollback is required.

---

### Task 5: Independent Review And Commit

**Files:** all allowed paths above only.

- [x] **Step 1: Run final verification**

Run `git diff --check`, contract checker, focused/full backend and frontend tests, migration cycle, production build, live API and browser smoke.

- [x] **Step 2: Independent reviewer**

Require `accept` or resolve blockers. Reviewer must check global-anonymous visibility, hidden 129-history behavior, filename sanitization, migration reversibility, exact old-path removal, API compatibility and dirty-file isolation.

- [x] **Step 3: Commit exact files**

Stage only allowed paths with explicit `git add`/`git rm`, verify cached diff, and commit `feat: share drawing list across origins`.

- [x] **Step 4: Integrate safely**

Follow `superpowers:finishing-a-development-branch`; preserve main's unrelated dirty work and verify the merged runtime before reporting completion.
