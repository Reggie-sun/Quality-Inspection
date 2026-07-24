# Chinese PDF Upload MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个可从裸根地址 `/` 直接使用的中文浏览器 MVP：用户上传原始工程 PDF 后，应用自动创建项目、执行现有解析/必要 OCR/候选生成链、进入 Review Workbench 完成审核和气泡调整，并下载同一 `reviewed_result` 生成的带气泡 PDF 与固定 SIP Excel。

**Architecture:** 保留现有 FastAPI、Celery、PostgreSQL、Redis、FileStorage、Review aggregate、Balloon Owner 和 Export orchestrator；新增的 Project Intake Owner 只负责“验证上传 → 原子保存 → 创建真实 Project → 调度 canonical processing task”，Project Status 只是只读投影。React 根入口由一个 application shell 管理上传、轮询和项目上下文；现有 `ProjectWorkbenchApp` 继续执行 review/balloon/export contract，所有用户可见文案集中为中文，内部 ID 不进入产品 URL 或可见界面。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Celery、PostgreSQL、Redis、PyMuPDF、React 19、TypeScript、Vite、PDF.js、Vitest、Playwright、Docker Compose、Micromamba。

---

## Source Of Truth And Execution Selection

- Stable semantics: `docs/contracts/MAIN_CONTRACT_MATRIX.md`。
- Approved delivery scope: `docs/superpowers/specs/2026-07-21-pdf-auto-balloon-and-excel-design.md`, Section 10。
- Sealed predecessor plan: `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`，已结束于 `D7-T3`；本计划不得修改该文件。
- Selected lane: `Heavy`。本计划新增稳定 upload/status API、真实 runtime entry，并跨 API、Celery、storage、review 和 frontend 串接产品数据流。
- Selected plan: `docs/superpowers/plans/2026-07-23-chinese-pdf-upload-mvp.md`，是七天 P0 结束后的唯一 successor implementation plan。
- Selection evidence: branch `feature/d1-t1-contract-harness` at `8acb318595ebb20174b2bea26fadda91e0ad3d27`；fresh predecessor run `20260723T042259807705Z-4e3e5f85` 的 `overall_verdict=passed`；当前裸 `/`、create/upload/status API 和 production OCR wiring 的代码事实见下文。
- Validation action: `replan` 后 `continue`。不是回写或重开七天计划，因为新的产品入口与 API surface 是 predecessor closure 之后的新 scope。
- Writer ownership and order: 主线程或执行窗口指定的单一 writer 严格按 Task 1 → Task 5；read-only explorer/reviewer 不得修改文件；同一 task 的 frontend/backend file group 不并发写。
- Frontend design prerequisite: Task 3 开始时必须依次调用 `product-design:index`、`product-design:image-to-code`，并完成 `image-to-code` 内置的 design-QA workflow。Workbench 视觉方向复用 `design-qa.md` 记录的已确认基线；若执行窗口拿不到该基线对应的参考截图，必须在 Task 3 写 production frontend 前停下取得用户确认，不得自行发明第二套视觉方向。
- First implementation verification:

  ```bash
  micromamba run -n qi-p0 pytest \
    backend/tests/integration/test_project_intake_api.py \
    backend/tests/integration/test_project_status_api.py -q
  ```

  Expected RED: route contract 不存在，测试以 `404/405` 或 import failure 失败。

## Problem Boundary And Ownership

### Product boundary

本计划只补齐以下闭环：

```text
裸 /
→ 中文上传页
→ multipart PDF intake
→ 真实 Project + StoredFile
→ canonical Celery processing
→ native inventory + hybrid missing-region OCR when needed
→ immutable AutomaticResult
→ idempotent ReviewWorkingCopy bootstrap
→ 中文 Review Workbench
→ item freeze
→ canonical balloon generation and manual adjustment
→ immutable ReviewedResult
→ canonical atomic export
→ ballooned PDF / SIP Excel / manifest downloads
```

纯扫描 PDF 仍按 Section 10 返回 `unsupported_input`，不在本计划中提升为正式支持。正式气泡仍只能在人工完成 item-set 审核并 freeze 后生成；入口层不得为了看起来“自动”而提前创建 `ReviewedResult`、绕过 freeze，或把 candidate/source overlay 冒充正式气泡。

### Single Owners

| Decision dimension | Single Owner | This plan's role |
| --- | --- | --- |
| PDF intake identity and dispatch | `ProjectIntakeService` | 新增 Owner；只提交 Project、StoredFile 和 canonical task dispatch |
| Processing result | `InventoryPipeline` / `AutomaticResult` Owner | 复用；入口和 status 不重算候选 |
| Missing-region OCR fact | existing OCR Signal Provider boundary via `RuntimeRecognition` | 只追加独立 OCR observations；不覆盖 native fact |
| Review mutation/freeze/confirm | `ReviewService` | 复用；frontend 只是 Executor |
| Balloon numbering/placement/validation | existing Balloon Owners and Veto Gate | 复用；不创建 frontend-side balloon truth |
| Formal publication | `ExportService` | 复用；PDF、Excel、manifest 仍 all-or-nothing |
| Product view state | `QualityInspectionApp` | 新增 frontend Owner；只管理 upload/poll/workbench screen |
| Processing status | `ProjectStatusService` read projection | 只组合 Project、LogicalJob、ErrorRecord、ReviewWorkingCopy，不提交业务状态 |

### Old path action

当前 `frontend/src/main.tsx` 的“缺 query parameter 就显示英文 alert”选择 `replace`：裸 `/` 改为唯一产品入口。

同时保留完整 `project_id + operator_id` query 的 run-bound deep link 作为临时 compatibility entry，因为 `.agent/harness/scripts/run-p0.py` 与 `frontend/e2e/p0-workbench.spec.ts` 是 verified real consumers。产品 UI 不生成、不展示、不要求该 URL。

```text
[REMOVAL_CANDIDATE] frontend/src/main.tsx run-bound query compatibility branch
  reason: bare-root product entry becomes canonical after this successor plan
  owner: frontend/src/app/QualityInspectionApp.tsx
  real_consumer: .agent/harness/scripts/run-p0.py and frontend/e2e/p0-workbench.spec.ts
  trigger: Harness browser phase can open an app-managed project context without query IDs
  deadline: one development cycle after this successor MVP passes its final browser gate
  last_verification: predecessor full-p0 run 20260723T042259807705Z-4e3e5f85
```

到 deadline 时只能 `remove` 或转换为明确的 internal test adapter；不得把该 branch 继续当产品入口，也不得建立第二套 Workbench。

### Unchanged contracts

- Provider 仍是 Signal/Advisor，不成为 candidate、review 或 export final Owner。
- native PDF text/coordinates remain authoritative；OCR 只补 missing/abnormal local crop。
- `raw automatic result → review working copy → reviewed result` 三层不可合并。
- item-set freeze、balloon validation、Confirm 和 export 顺序不变。
- hard collision、unreadable glyph、`manual_required`、coverage/freeze blocker、export preflight failure 均不得转换为 warning success。
- PDF、Excel、manifest 仍来自同一 `reviewed_result`，三个产物全部通过才显示下载。
- 不新增 RBAC/SSO、可信身份、通用 i18n、project dashboard、history browser、Provider cache、完整 retry-attempt model 或 P1/P2 能力。
- 不修改 `.agent/EXECUTION_STATUS.md`，也不创建该文件。
- 不修改 predecessor plan、P0 traceability matrix、历史 receipt 或 `.agent/harness/runs/`。

## Current Code Evidence

### Existing capabilities to reuse

| Capability | Current code evidence | Reuse contract |
| --- | --- | --- |
| Atomic local storage | `backend/app/storage/local.py` | `write_verified()`、hash check、atomic rename 保持 canonical |
| Background task | `backend/app/processing/tasks.py::inventory_project` | 继续作为唯一 processing task entry |
| Processing and raw freeze | `backend/app/processing/pipeline.py::InventoryPipeline.run` | 继续产生 immutable `AutomaticResult` |
| Working-copy bootstrap | `backend/app/review/service.py::ReviewService.create_from_raw` | 成功后由同一 Celery task 幂等调用 |
| Workbench projection/PDF delivery | `backend/app/projects/router.py::{get_workbench,get_source_pdf}` | 继续提供安全 projection，不泄露 `resource_ref`/host path |
| Review APIs | `backend/app/review/router.py` | lock、commands、freeze、confirm 全部复用 |
| Balloon APIs | `backend/app/balloons/router.py` | generate、move、delete、rebuild、reorder、renumber 全部复用 |
| Atomic export/download | `backend/app/exports/{service,router}.py` | 保持三产物一个 success Owner |
| Browser workbench | `frontend/src/components/workbench/ProjectWorkbenchApp.tsx` | 作为 root application shell 的 ready screen 复用 |
| Existing browser regression | `frontend/e2e/p0-workbench.spec.ts` | 改为中文 selector 后保留 run-bound regression |

### Missing product-entry capabilities

| Gap | Evidence | Planned closure |
| --- | --- | --- |
| Bare-root upload | `frontend/src/main.tsx` 缺参只显示英文 alert | Task 3 |
| Project create/upload API | projects router 只有 workbench/source GET | Task 1 |
| Processing status/error API | frontend 无 polling surface；transient preflight failure 可令 Project 留在 `processing` 而 LogicalJob 已 failed | Task 1 |
| Processing-to-review handoff | normal task 成功只到 `ready_for_edit`；Harness/tests 才显式 `create_from_raw()` | Task 2 |
| Active OCR wiring | `append_ocr_observations()` 和 OCR adapter 存在，但 default production task 未调用 | Task 2 |
| App-owned identity/context | `project_id/operator_id` 来自 query 且显示在页面 | Task 3/4 |
| Chinese UI and errors | Workbench、aria、status、empty/error/download copy 基本为英文 | Task 4 |
| Refresh recovery | `reviewedResultId` 和 successful export 只在 React memory | Task 4 |
| Bare-root browser proof | existing Playwright starts from prepared deep link | Task 5 |

## Product API And State Contract

### `POST /api/v1/projects`

Request:

```http
POST /api/v1/projects
Content-Type: multipart/form-data

file=<one PDF file>
```

Rules:

1. accept exactly one non-empty file;
2. validate MIME as `application/pdf`, `%PDF-` signature, and PyMuPDF open/page count;
3. ignore the untrusted filename for storage addressing; store at `projects/<project-id>/source.pdf`;
4. write bytes through `LocalFileStorage.write_verified()` before publishing metadata;
5. persist one real `Project(state=processing)` and one `StoredFile`;
6. dispatch `inventory_project.delay(project_id, source_ref, "product-process:<project-id>")`;
7. if DB persistence fails, delete only the just-written source object;
8. if dispatch fails, keep the failed Project as evidence, write sanitized `project_dispatch_failed`, mark `processing_failed`, and return a retryable `503`;
9. never echo source bytes, host paths, `resource_ref`, credentials, or operator identity.

Accepted response:

```json
{
  "project_id": "internal-uuid",
  "phase": "queued",
  "workbench_ready": false,
  "error": null
}
```

`project_id` is an internal transport field consumed by the application shell. It is never rendered, copied into the product URL, or requested from the user.

### `GET /api/v1/projects/{project_id}/status`

Response shape:

```json
{
  "phase": "queued | processing | ready_for_review | failed",
  "workbench_ready": false,
  "retryable": false,
  "error": {
    "code": "unsupported_input",
    "stage": "page_inventory"
  }
}
```

`error` is `null` outside failure. The projection resolves in this order:

1. a matching `ReviewWorkingCopy` means `ready_for_review`, including `editing/reviewed/exporting/export_succeeded/export_failed`;
2. `LogicalJob.status=failed`、Project state `processing_failed/unsupported_input`，或最新 blocking ErrorRecord 为 `review_bootstrap_failed` 均 means `failed`，即使 Project 仍为 `processing/ready_for_edit`;
3. Project `processing` with no job means `queued`;
4. Project `processing/ready_for_edit` with an active or just-completed job and no working copy means `processing`;
5. only `cause_category=transient_dependency_unavailable` or `project_dispatch_failed` is retryable;
6. response includes stable code/stage only; backend English `message` is not passed through to the user.

### Frontend state

Required user-visible coverage is explicit: loading、processing、success、fatal failure、retry 和 download。每一状态都有中文文案、可操作的下一步和对应 component/browser assertion；不得以 console、API payload 或 Harness receipt 代替页面状态。

```text
idle
→ uploading
→ processing(queued|processing)
→ ready
→ ProjectWorkbenchApp
→ reviewed
→ exporting
→ downloads
```

Failure branches:

```text
upload network/validation failure
→ 中文错误 + 重新上传

status network failure
→ 保留 current project + 重新获取状态

fatal processing failure
→ 中文 code mapping + 重新处理同一内存 File
→ 若 reload 后 File 不在内存，则重新选择 PDF
```

自动 retry 不得重复触发 Provider 或创建隐藏 attempts。点击“重新处理”创建一个新 Project，旧失败 Project 保持 terminal evidence；不把 `processing_failed` 静默改回 `processing`。

### Local MVP operator identity

本地 MVP 的 operator identity 由浏览器首次打开时调用 `crypto.randomUUID()` 生成，并存入 `localStorage["qi.local-operator-id"]`。它只作为现有 `X-QI-Operator` header 的简单操作人标签：

- 不要求用户输入；
- 不进入 query/path；
- 不在 DOM、日志或下载文件名显示；
- 同一浏览器 profile/origin 复用；
- 明确不是认证、授权或可信身份，RBAC/SSO 仍属 P1/P2。

当前 project context 存在 React state 与 `sessionStorage["qi.current-project-id"]`。reload 可恢复 polling/workbench；清除 session storage 或点击“处理另一份 PDF”回到上传页。

## File Map

### Backend product entry

| File | Responsibility |
| --- | --- |
| `backend/app/projects/schemas.py` | intake/status response types and stable phase/error fields |
| `backend/app/projects/service.py` | Project Intake Owner and Project Status read projection |
| `backend/app/projects/router.py` | multipart create/status routes; existing workbench/source routes remain |
| `backend/app/processing/tasks.py` | canonical task calls pipeline then idempotent working-copy bootstrap |
| `backend/app/processing/runtime_recognition.py` | callbacks for native inventory plus bounded missing-region OCR |
| `backend/app/providers/runtime.py` | server-only Tencent OCR client construction from existing Settings |
| `backend/app/pdf/inventory.py` | public, coordinate-safe conversion seam for OCR observations |

### Frontend product entry and copy

| File | Responsibility |
| --- | --- |
| `frontend/src/app/QualityInspectionApp.tsx` | root upload/poll/retry/workbench screen Owner |
| `frontend/src/app/localContext.ts` | non-auth local operator and session project context |
| `frontend/src/features/projects/api.ts` | multipart intake and status polling API |
| `frontend/src/copy/zhCN.ts` | single-language Chinese copy, state labels and stable error-code mapping |
| `frontend/src/main.tsx` | bare-root canonical entry plus bounded run-only compatibility branch |
| `frontend/src/components/workbench/ProjectWorkbenchApp.tsx` | existing Workbench wiring, Chinese runtime states, restore reviewed/export projection |
| existing Workbench/PDF/review/balloon components | Chinese visible copy and aria labels; no semantic rewrite |

### Verification

| File | Responsibility |
| --- | --- |
| `backend/tests/integration/test_project_intake_api.py` | actual multipart/storage/dispatch active and failure contract |
| `backend/tests/integration/test_project_status_api.py` | queued/processing/ready/failed projection |
| `backend/tests/integration/test_processing_entry_task.py` | pipeline → working-copy idempotent bridge |
| `backend/tests/unit/pdf/test_runtime_ocr.py` | hybrid crop OCR, coordinates, native authority, no-call vector path |
| `frontend/src/app/QualityInspectionApp.test.tsx` | root upload/loading/processing/fatal/retry/ready states |
| `frontend/src/app/localContext.test.ts` | IDs are generated/stored but not shown or added to URL |
| existing frontend component tests | Chinese selectors and unchanged review/balloon/export behavior |
| `frontend/e2e/chinese-pdf-upload-mvp.spec.ts` | real bare-root browser closure |

## Harness And Evidence Boundary

- Predecessor receipt `20260723T042259807705Z-4e3e5f85` is historical proof for the unchanged P0 core at commit `8acb318`; implementation commits will make it non-current for whole-repository release claims.
- Do not edit or regenerate historical run/receipt evidence and do not project successor status into the P0 traceability matrix.
- Successor evidence is intentionally light:
  1. new intake/status/processing contract and focused tests;
  2. existing backend/frontend regression suites;
  3. existing P0 Workbench Playwright regression kept compatible with Chinese selectors;
  4. one new bare-root real-browser smoke.
- `python .agent/harness/scripts/check-contracts.py` remains a static no-drift gate. This plan does not add a second Harness phase, policy, receipt format, baseline registry, or run type.
- The new browser smoke is product-entry evidence, not a replacement current-four formal receipt and not permission to label synthetic input as current-four live evidence.

## Task 1: Add The Real PDF Intake And Status API

**Allowed paths:**

- Create: `backend/app/projects/schemas.py`
- Create: `backend/app/projects/service.py`
- Modify: `backend/app/projects/router.py`
- Create: `backend/tests/integration/test_project_intake_api.py`
- Create: `backend/tests/integration/test_project_status_api.py`

**Do not modify:** database models/migrations, `InventoryPipeline`, Review/Balloon/Export Owners, Harness, predecessor docs.

- [ ] **Step 1: Write RED multipart intake tests**

Add tests that override only the session/storage/dispatcher dependencies and use one actual in-memory PDF:

```python
def test_create_project_accepts_one_pdf_and_dispatches_canonical_task(
    client,
    db_session,
    tmp_storage,
    dispatched,
    one_page_vector_pdf,
) -> None:
    response = client.post(
        "/api/v1/projects",
        files={"file": ("drawing.pdf", one_page_vector_pdf, "application/pdf")},
    )
    assert response.status_code == 202
    payload = response.json()
    project_id = uuid.UUID(payload["project_id"])
    assert payload == {
        "project_id": str(project_id),
        "phase": "queued",
        "workbench_ready": False,
        "retryable": False,
        "error": None,
    }
    project = db_session.get(Project, project_id)
    source = db_session.scalar(select(StoredFile))
    assert project.state == ProjectState.PROCESSING
    assert source.mime_type == "application/pdf"
    assert tmp_storage.read_bytes(source.resource_ref) == one_page_vector_pdf
    assert dispatched == [
        (str(project_id), source.resource_ref, f"product-process:{project_id}")
    ]
    assert "asset://" not in response.text
    assert str(tmp_storage.root) not in response.text


@pytest.mark.parametrize(
    ("filename", "content_type", "payload"),
    [
        ("empty.pdf", "application/pdf", b""),
        ("drawing.txt", "text/plain", b"%PDF-invalid"),
        ("broken.pdf", "application/pdf", b"%PDF-not-a-document"),
    ],
)
def test_create_project_rejects_invalid_upload_without_dispatch(
    client, dispatched, filename, content_type, payload
) -> None:
    response = client.post(
        "/api/v1/projects",
        files={"file": (filename, payload, content_type)},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_pdf"
    assert dispatched == []
```

Add a dispatch failure test proving `project_dispatch_failed` is sanitized, retryable, and leaves no formal result/download.

- [ ] **Step 2: Run RED and record the expected route failure**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_intake_api.py \
  backend/tests/integration/test_project_status_api.py -q
```

Expected: FAIL because `POST /api/v1/projects`, status route, schemas and service do not exist.

- [ ] **Step 3: Implement minimal intake/status schemas**

Use a closed response surface:

```python
class ProjectPhase(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    FAILED = "failed"


class ProjectError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    stage: str


class ProjectStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID | None = None
    phase: ProjectPhase
    workbench_ready: bool
    retryable: bool
    error: ProjectError | None
```

The status GET serializes with `exclude_none=True` for `project_id`; only the create response returns it.

- [ ] **Step 4: Implement the Project Intake Owner**

`ProjectIntakeService.create_pdf()` must:

```python
def create_pdf(self, *, content: bytes, content_type: str) -> ProjectStatusResponse:
    validate_pdf(content, content_type)
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    stored = self.storage.write_verified(
        f"projects/{project.id}/source.pdf",
        content,
        hashlib.sha256(content).hexdigest(),
    )
    source = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    self.session.add_all([project, source])
    try:
        self.session.commit()
    except Exception:
        self.session.rollback()
        self.storage.delete(stored.resource_ref)
        raise
    try:
        self.dispatch(
            str(project.id),
            source.resource_ref,
            f"product-process:{project.id}",
        )
    except Exception as error:
        failed_status = self._record_dispatch_failure(project.id)
        raise ProjectDispatchFailed(failed_status) from error
    return self.status(project.id, include_project_id=True)
```

`validate_pdf()` opens bytes with PyMuPDF and requires at least one page. It logs neither content nor filename.

`status()` must query the exact logical key for this project and inspect `ReviewWorkingCopy` before Project state. It returns only error code/stage and derives `retryable` from `cause_category`, never from frontend guesses.

- [ ] **Step 5: Add the two routes without changing existing workbench routes**

```python
@router.post("", status_code=202)
async def create_project(
    file: Annotated[UploadFile, File()],
    service: ProjectServiceDependency,
) -> JSONResponse:
    try:
        result = service.create_pdf(
            content=await file.read(),
            content_type=file.content_type or "",
        )
    except InvalidPdf:
        return _error(422, "invalid_pdf", "uploaded file is not a valid PDF")
    except ProjectDispatchFailed as error:
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(error.status),
        )
    return JSONResponse(status_code=202, content=jsonable_encoder(result))


@router.get("/{project_id}/status")
def get_project_status(
    project_id: uuid.UUID,
    service: ProjectServiceDependency,
) -> JSONResponse:
    try:
        result = service.status(project_id)
    except ProjectNotFound:
        return _error(404, "project_not_found", "project was not found")
    return JSONResponse(content=jsonable_encoder(result, exclude_none=True))
```

`ProjectDispatchFailed.status` is a closed `ProjectStatusResponse` with `phase=failed`, `retryable=true`, `error.code=project_dispatch_failed`, `error.stage=dispatch`, and the internal Project ID needed only by the application shell. Keep the existing `_error()` envelope for `invalid_pdf`, `project_not_found` and a final sanitized `500 project_intake_failed` handler. No response includes the caught exception message; validation and unknown persistence failures are not retryable.

- [ ] **Step 6: Prove active and failure status paths**

The status tests must cover:

```python
@pytest.mark.parametrize(
    ("project_state", "job_status", "has_working_copy", "expected_phase"),
    [
        ("processing", None, False, "queued"),
        ("processing", "pending", False, "processing"),
        ("processing", "failed", False, "failed"),
        ("ready_for_edit", "succeeded", False, "processing"),
        ("editing", "succeeded", True, "ready_for_review"),
        ("reviewed", "succeeded", True, "ready_for_review"),
    ],
)
def test_project_status_projects_real_owners(
    client,
    seeded_project_status,
    project_state,
    job_status,
    has_working_copy,
    expected_phase,
) -> None:
    project_id = seeded_project_status(
        project_state=project_state,
        job_status=job_status,
        has_working_copy=has_working_copy,
    )
    response = client.get(f"/api/v1/projects/{project_id}/status")
    assert response.status_code == 200
    assert response.json()["phase"] == expected_phase
    assert response.json()["workbench_ready"] is (expected_phase == "ready_for_review")
```

Also prove `processing + failed LogicalJob` and `ready_for_edit + review_bootstrap_failed` cannot remain a forever-processing UI state. Response text contains no `resource_ref`, path, credential or raw backend message.

- [ ] **Step 7: Run GREEN and focused regressions**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_intake_api.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_error_records.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

```bash
git add \
  backend/app/projects/schemas.py \
  backend/app/projects/service.py \
  backend/app/projects/router.py \
  backend/tests/integration/test_project_intake_api.py \
  backend/tests/integration/test_project_status_api.py
git diff --cached --check
git commit -m "feat: add PDF project intake API"
```

Rollback: `git revert <task-1-commit>`。若实际 rollback，第一项验证是：

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_project_workbench_api.py -q
```

## Task 2: Connect Processing To Necessary OCR And Review Bootstrap

**Allowed paths:**

- Create: `backend/app/processing/runtime_recognition.py`
- Create: `backend/app/providers/runtime.py`
- Modify: `backend/app/pdf/inventory.py`
- Modify: `backend/app/processing/tasks.py`
- Create: `backend/tests/unit/pdf/test_runtime_ocr.py`
- Create: `backend/tests/integration/test_processing_entry_task.py`
- Modify only for regression assertions: `backend/tests/integration/test_processing_state.py`
- Modify only for regression assertions: `backend/tests/integration/test_error_records.py`

**Do not modify:** candidate semantics, review command semantics, migrations, Provider contract fixtures, P0 policy/receipt files.

- [ ] **Step 1: Write RED tests for product processing orchestration**

```python
def test_inventory_task_bootstraps_one_working_copy_idempotently(
    db_session, source_project, runtime_recognition
) -> None:
    first = run_inventory_task(source_project, runtime_recognition)
    second = run_inventory_task(source_project, runtime_recognition)
    assert first == second
    raw = db_session.scalar(
        select(AutomaticResult).where(
            AutomaticResult.project_id == source_project.project.id
        )
    )
    copies = list(
        db_session.scalars(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == source_project.project.id
            )
        )
    )
    assert len(copies) == 1
    assert copies[0].raw_result_id == raw.id
    assert db_session.get(Project, source_project.project.id).state == "editing"
```

The OCR unit tests must implement these exact cases:

1. `test_vector_page_with_complete_native_text_makes_zero_ocr_calls` compares the returned native observations byte-for-byte with the original inventory and asserts the fake Provider call list is empty.
2. `test_hybrid_image_region_appends_separate_coordinate_safe_ocr_observation` asserts native observations are unchanged, exactly one `source_type="ocr"` observation is appended, `bbox_pdf` matches the crop-to-PDF conversion within `0.5`, and normalized coordinates remain in `[0, 1]`.
3. `test_ocr_never_receives_whole_page_when_only_one_image_region_is_missing` records the fake Provider image dimensions and proves they equal the clipped image rectangle rather than the rendered page.
4. `test_pure_scanned_page_stays_unsupported_without_ocr_promotion` asserts the page remains `support_level="unsupported"`, no Provider call occurs, and `InventoryPipeline` retains the existing `unsupported_input` Veto.

- [ ] **Step 2: Run RED**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/integration/test_processing_entry_task.py -q
```

Expected: FAIL because runtime recognition and processing-to-review bridge do not exist.

- [ ] **Step 3: Add a server-only OCR provider factory**

`backend/app/providers/runtime.py` imports `tencentcloud.common.credential` as `tencent_credential` and `tencentcloud.ocr.v20181119.ocr_client`, then constructs `TencentOcrProvider` from existing `Settings.tencent_secret_id`, `tencent_secret_key`, and `tencent_region`. It raises `CapabilityUnavailable("ocr_provider_unavailable", "OCR Provider configuration is unavailable")` on absent configuration and never logs or returns credential values.

The factory is dependency-injectable:

```python
OcrProviderFactory = Callable[[Settings], OcrProvider]


def build_ocr_provider(settings: Settings) -> OcrProvider:
    secret_id = (settings.tencent_secret_id or "").strip()
    secret_key = (settings.tencent_secret_key or "").strip()
    if not secret_id or not secret_key:
        raise CapabilityUnavailable(
            "ocr_provider_unavailable",
            "OCR Provider configuration is unavailable",
        )
    cloud_credential = tencent_credential.Credential(secret_id, secret_key)
    client = ocr_client.OcrClient(cloud_credential, settings.tencent_region)
    return TencentOcrProvider(client)
```

Tests use a fake factory; focused/offline tests make zero network calls. This task does not add a live Provider command.

- [ ] **Step 4: Implement bounded missing-region OCR callbacks**

`RuntimeRecognition` owns two callbacks already supported by `InventoryPipeline`:

```python
class RuntimeRecognition:
    def build_inventory(self, pdf_path: Path) -> tuple[PageInventory, ...]:
        native_pages = build_inventory(pdf_path)
        return self._append_missing_region_ocr(pdf_path, native_pages)

    def build_candidate_snapshot(
        self,
        pages: tuple[PageInventory, ...],
    ) -> CandidateSnapshot:
        snapshot = candidate_snapshot_from_inventory(pages)
        return replace(
            snapshot,
            provider_call_ids=tuple(self.provider_call_ids),
        )
```

Rules:

1. call existing `build_inventory()` first;
2. make zero OCR calls for `processing_route=native`;
3. keep `support_level=unsupported` pure-scanned pages unsupported;
4. for `processing_route="hybrid"` pages, including `support_level="review_required"`, enumerate clipped image rectangles and select only regions not already covered by authoritative native observations;
5. render only those local crops, up to the frozen P0 bound of 16 OCR calls per page;
6. convert Provider crop pixels back to PDF coordinates, then call the public OCR observation helper in `backend/app/pdf/inventory.py`;
7. append OCR observations through `append_ocr_observations()`; never mutate or replace native observations;
8. retain sanitized request ID/call record references in `provider_call_ids`;
9. do not write base64, Authorization, credentials, whole-page bytes or host paths to logs/call records;
10. let candidate generation consume the combined observations through the existing `candidate_snapshot_from_inventory()` Owner.

The existing qwen adapter and frozen JSON Schema remain unchanged and contract-tested. This successor does not invent a second LLM semantic Owner or call qwen merely to satisfy a UI state.

- [ ] **Step 5: Bridge the canonical task to the existing Review service**

Keep the task name, decorator, signature and return contract. After constructing the existing settings/session/storage/preflight dependencies, construct one `RuntimeRecognition` and replace only the callback seam:

```python
result_ref = InventoryPipeline(
    session,
    storage,
    preflight,
    inventory_builder=recognition.build_inventory,
    candidate_snapshot_builder=recognition.build_candidate_snapshot,
).run(project_id, source_ref, logical_task_key)
raw_id = uuid.UUID(result_ref.removeprefix("automatic-result://"))
ReviewService(session, storage=storage).create_from_raw(raw_id)
return result_ref
```

`create_from_raw()` is already idempotent. If working-copy bootstrap fails after raw success, roll back the failed review transaction, write one sanitized blocking `review_bootstrap_failed` ErrorRecord with `cause_category=processing_defect`, and re-raise; do not fabricate `editing`, duplicate the raw result, or mutate the successful processing job. Task 1 status tests must prove this ErrorRecord projects to terminal `failed`.

- [ ] **Step 6: Run GREEN, Provider contracts and state regressions**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/contract/test_tencent_ocr_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_processing_preflight.py \
  backend/tests/integration/test_processing_state.py \
  backend/tests/integration/test_error_records.py \
  backend/tests/integration/test_result_layers.py -q
```

Expected: PASS with fixture/fake Providers and zero paid calls.

- [ ] **Step 7: Commit Task 2**

```bash
git add \
  backend/app/processing/runtime_recognition.py \
  backend/app/providers/runtime.py \
  backend/app/pdf/inventory.py \
  backend/app/processing/tasks.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_processing_state.py \
  backend/tests/integration/test_error_records.py
git diff --cached --check
git commit -m "feat: connect processing to review"
```

Rollback: `git revert <task-2-commit>`。若实际 rollback，第一项验证是：

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_processing_state.py \
  backend/tests/integration/test_result_layers.py -q
```

## Task 3: Build The Bare-Root Chinese Upload Application Shell

**Allowed paths:**

- Modify: `frontend/index.html`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/app/QualityInspectionApp.tsx`
- Create: `frontend/src/app/QualityInspectionApp.test.tsx`
- Create: `frontend/src/app/localContext.ts`
- Create: `frontend/src/app/localContext.test.ts`
- Create: `frontend/src/features/projects/api.ts`
- Create: `frontend/src/features/projects/api.test.ts`
- Create: `frontend/src/copy/zhCN.ts`
- Create: `frontend/src/styles/app.css`
- Modify: `design-qa.md`

**Do not modify:** Workbench/review/balloon behavior in this task; Task 4 owns their visible copy and recovery wiring.

- [ ] **Step 1: Lock the Section 10 visual source and run the required Product Design workflow**

Invoke `product-design:index`, then `product-design:image-to-code`, against the user-confirmed reference screenshot and the existing Workbench direction recorded in `design-qa.md`. Append one successor section to `design-qa.md` recording the selected source identity, root-upload design decisions, `1565x796` comparison viewport, implementation capture and built-in design-QA result; preserve the predecessor section verbatim.

The product shell must remain the same React application and route. Do not create a standalone prototype, second frontend, visual-only mock, or screenshot-derived business logic. If the confirmed source screenshot is unavailable, stop Task 3 at this step and request it; Tasks 1–2 remain valid and committed.

- [ ] **Step 2: Write RED root-entry and context tests**

```tsx
test("裸根地址显示中文 PDF 上传入口且不要求内部 ID", () => {
  window.history.replaceState({}, "", "/");
  render(<QualityInspectionApp api={fakeApi} />);
  expect(screen.getByRole("heading", { name: "工程图纸智能检验" })).not.toBeNull();
  expect(screen.getByLabelText("选择工程 PDF")).not.toBeNull();
  expect(screen.queryByText(/project_id|operator_id/i)).toBeNull();
  expect(window.location.search).toBe("");
});
```

In the same test file, add:

- `上传后显示处理进度并自动进入现有工作台`: fake `createProject` returns `queued`, successive status calls return `processing` then `ready_for_review`; upload with `userEvent.upload`, click `上传并开始识别`, assert `正在解析图纸并识别检验项`, then `识别完成，已进入审核` and the `检验项目审核` heading; URL remains exactly `/`.
- `fatal failure 显示中文错误并可重新处理`: fake status returns `failed/unsupported_input`; assert the alert is `当前 PDF 暂不支持`, the `重新处理` button is enabled, and no backend English message is rendered.
- `状态请求失败保留项目并允许重新获取`: reject one status call with `ApiError`, assert `重新获取状态`, click it, then resolve `ready_for_review` without creating a second Project.

`localContext.test.ts` proves one generated operator ID is stable in `localStorage`, current Project is in `sessionStorage`, neither is appended to URL, and both values are absent from rendered text.

- [ ] **Step 3: Run RED**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/app/QualityInspectionApp.test.tsx \
  src/app/localContext.test.ts \
  src/features/projects/api.test.ts
```

Expected: FAIL because the root shell, context helper and project API client do not exist.

- [ ] **Step 4: Add typed multipart/status client methods**

Extend the client without changing existing JSON methods:

```ts
export const postForm = async <Result>(path: string, body: FormData): Promise<Result> => {
  return json<Result>(await fetch(path, { method: "POST", body }));
};


export function createProject(file: File): Promise<ProjectStatus> {
  const body = new FormData();
  body.set("file", file);
  return postForm<ProjectStatus>("/api/v1/projects", body);
}


export function getProjectStatus(projectId: string): Promise<ProjectStatus> {
  return getJson<ProjectStatus>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/status`,
  );
}
```

Do not set a manual multipart `Content-Type`; the browser owns the boundary.

- [ ] **Step 5: Implement app-owned identity and project context**

`localContext.ts` must expose:

```ts
export function getOrCreateLocalOperatorId(storage = window.localStorage): string;
export function getCurrentProjectId(storage = window.sessionStorage): string | undefined;
export function setCurrentProjectId(projectId: string, storage = window.sessionStorage): void;
export function clearCurrentProjectId(storage = window.sessionStorage): void;
```

The helper validates stored UUID syntax before reuse. Invalid stored values are replaced, not rendered.

- [ ] **Step 6: Implement the root state machine**

`QualityInspectionApp` holds:

```ts
type ProductScreen =
  | { kind: "idle" }
  | { kind: "uploading"; file: File }
  | { kind: "processing"; file?: File; projectId: string; phase: "queued" | "processing" }
  | { kind: "fatal"; file?: File; code: string; retryable: boolean }
  | { kind: "ready"; projectId: string };
```

Behavior:

1. `/` with no session Project renders a Chinese upload/drop area and disabled submit until one PDF is selected;
2. upload button disables during request and displays progress copy;
3. accepted create response stores Project in session storage;
4. poll every 1.5 seconds; abort timer/fetch on unmount or Project replacement;
5. status network failure pauses polling and exposes “重新获取状态”;
6. backend `failed` maps stable error code through `zhCN.ts`, never shows `ApiError.message`;
7. retry with an in-memory File calls create again; without it clears context and returns to file selection;
8. `ready_for_review` first announces `识别完成，已进入审核`, then renders the existing `ProjectWorkbenchApp` with app-generated operator ID;
9. “处理另一份 PDF” clears only session Project and returns to idle;
10. URL remains exactly `/`.

- [ ] **Step 7: Preserve the run-only compatibility branch**

`main.tsx` selects the deep link only when both query values are non-blank:

```tsx
const projectId = parameters.get("project_id")?.trim();
const operatorId = parameters.get("operator_id")?.trim();

createRoot(root).render(
  projectId && operatorId
    ? <ProjectWorkbenchApp projectId={projectId} operatorId={operatorId} />
    : <QualityInspectionApp />,
);
```

A missing or partial query never produces an error and falls back to the product root. Do not expose a link that teaches users to construct the compatibility URL.

- [ ] **Step 8: Run GREEN, production build and design QA**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/app/QualityInspectionApp.test.tsx \
  src/app/localContext.test.ts \
  src/features/projects/api.test.ts
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: PASS; built root title and upload screen are Chinese.

Use the Product Design workflow's browser/design-QA steps at `1565x796` to verify upload idle、selected、uploading、processing、success、fatal、retry and Workbench transition states. Update `design-qa.md` only with the current successor capture/result; do not rewrite historical receipt evidence.

- [ ] **Step 9: Commit Task 3**

```bash
git add \
  frontend/index.html \
  frontend/src/main.tsx \
  frontend/src/api/client.ts \
  frontend/src/api/types.ts \
  frontend/src/app/QualityInspectionApp.tsx \
  frontend/src/app/QualityInspectionApp.test.tsx \
  frontend/src/app/localContext.ts \
  frontend/src/app/localContext.test.ts \
  frontend/src/features/projects/api.ts \
  frontend/src/features/projects/api.test.ts \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/app.css \
  design-qa.md
git diff --cached --check
git commit -m "feat: add Chinese PDF upload entry"
```

Rollback: `git revert <task-3-commit>`。若实际 rollback，第一项验证是：

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
```

## Task 4: Localize And Restore The Existing Review Workbench

**Allowed backend paths:**

- Modify: `backend/app/projects/router.py`
- Modify: `backend/app/exports/service.py`
- Modify: `backend/tests/integration/test_project_workbench_api.py`
- Modify: `backend/tests/integration/test_export_atomicity.py`

**Allowed frontend implementation paths:**

- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/RecognitionSummary.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/FreezeReviewButton.tsx`
- Modify: `frontend/src/components/workbench/ExportPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.tsx`
- Modify: `frontend/src/components/pdf/OverlayLayer.tsx`
- Modify: `frontend/src/components/balloons/BalloonOverlay.tsx`
- Modify: `frontend/src/components/balloons/BalloonToolbar.tsx`

**Allowed frontend test paths:**

- Create: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/RecognitionSummary.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/workbench/FreezeReviewButton.test.tsx`
- Modify: `frontend/src/components/workbench/ExportPanel.test.tsx`
- Modify: `frontend/src/components/workbench/selection.test.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- Modify: `frontend/src/components/pdf/OverlayLayer.test.tsx`
- Modify: `frontend/src/components/balloons/BalloonOverlay.test.tsx`
- Modify: `frontend/e2e/p0-workbench.spec.ts`

**Do not modify:** review/balloon/export business commands, geometry, collision validation, template assets or export generation.

- [ ] **Step 1: Write RED recovery projection tests**

Extend `test_project_workbench_api.py` so an existing reviewed/exported project returns:

```python
assert payload["reviewed_result_id"] == str(context.reviewed_result.id)
latest = payload["latest_export"]
assert latest["id"] == str(export.id)
assert latest["project_id"] == str(context.project.id)
assert latest["reviewed_result_id"] == str(context.reviewed_result.id)
assert latest["status"] == "success"
assert latest["error_id"] is None
assert [artifact["kind"] for artifact in latest["artifacts"]] == [
    "ballooned_pdf",
    "sip_excel",
    "manifest",
]
for artifact in latest["artifacts"]:
    expected = context.export_artifacts[artifact["kind"]]
    assert artifact["sha256"] == expected.sha256
    assert artifact["size_bytes"] == expected.size_bytes
    assert artifact["reviewed_result_id"] == str(context.reviewed_result.id)
    assert artifact["downloadable"] is True
```

For editing projects both fields are `null`. The projection must not create an export or change Project state.

- [ ] **Step 2: Write RED Chinese-copy component tests**

Tests must assert the rendered user surface, not only constants:

```tsx
expect(screen.getByRole("heading", { name: "检验项目审核" })).not.toBeNull();
expect(screen.getByRole("button", { name: "保存审核修改" })).not.toBeNull();
expect(screen.getByRole("button", { name: "冻结检验项" })).not.toBeNull();
expect(screen.getByRole("button", { name: "生成气泡" })).not.toBeNull();
expect(screen.getByRole("button", { name: "确认审核结果" })).not.toBeNull();
expect(screen.queryByText(/Operator|Project [a-f0-9-]{36}/i)).toBeNull();
```

Add a table-driven visible-copy test for loading、empty、review blocker、fatal error、exporting、export failed and three download labels. Known `ApiError.code` must map to Chinese; an unknown code renders `操作失败，请重试。`.

- [ ] **Step 3: Run RED**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_export_atomicity.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
```

Expected: backend recovery fields are absent and frontend tests still find English copy.

- [ ] **Step 4: Add read-only reviewed/export recovery**

Add `ExportService.latest_for_project(project_id)`:

```python
def latest_for_project(self, project_id: uuid.UUID) -> ExportJob | None:
    return self.session.scalar(
        select(ExportJob)
        .where(ExportJob.project_id == project_id)
        .order_by(ExportJob.created_at.desc(), ExportJob.id.desc())
        .limit(1)
    )
```

`_workbench_payload()` reads the existing `ReviewedResult` and latest ExportJob, serializes artifacts with the same export payload contract, and adds:

```json
{
  "reviewed_result_id": "uuid-or-null",
  "latest_export": {
    "status": "success",
    "artifacts": []
  }
}
```

This is a read projection only. It does not retry exports, publish artifacts, or become an Export Owner.

`ProjectWorkbenchApp.refresh()` initializes `reviewedResultId` from the projection. `ExportPanel` accepts `initialExport`, validates all three downloadable kinds before showing links, and continues to use canonical download endpoints.

- [ ] **Step 5: Centralize all Chinese product copy**

`zhCN.ts` contains typed `app`、`processing`、`projectState`、`workbench`、`review`、`balloons`、`export` and `errors` groups. At minimum, pin these high-risk state strings in tests:

```ts
const requiredCopy = {
  queued: "项目已创建，等待处理",
  processing: "正在解析图纸并识别检验项",
  ready: "识别完成，已进入审核",
  fatalFallback: "处理失败，请重新选择 PDF",
  retryStatus: "重新获取状态",
  retryProcess: "重新处理",
  createExport: "生成正式文件",
  creatingExport: "正在生成 PDF 和 SIP Excel",
  downloadPdf: "下载带气泡 PDF",
  downloadExcel: "下载 SIP Excel",
  downloadManifest: "下载校验清单",
} as const;
```

No locale negotiation, translation loader, package, fallback locale or second language file is added.

- [ ] **Step 6: Replace every user-visible English string**

The implementation must cover:

- document title, headings, buttons, status and retry copy;
- all `aria-label` values used by keyboard/screen-reader interaction;
- page/zoom/pan controls and PDF render error;
- review field labels, option values' visible labels, keep/exclude/edit/merge/split/add actions;
- summary chips, table headers, empty state, geometry/collision labels;
- SIP metadata/detail confirmation labels;
- freeze/generate/confirm and balloon command labels;
- export state and download links;
- raw Project state display;
- unknown error fallback.

Do not translate raw engineering text, drawing content, SIP field values, formal numbers, API keys, enum wire values, filenames or internal test IDs.

Remove visible item UUIDs from ReviewPanel labels. Keep stable `data-item-id` attributes and internal relation keys for selection/evidence, but name controls with visible raw text/formal number so the operator does not have to interpret an internal ID.

- [ ] **Step 7: Prevent raw error and identity leakage**

`ProjectWorkbenchApp` must:

1. render neither `projectId` nor `operatorId`;
2. map Project state to `zhCN.projectState`;
3. map `ApiError.code` to Chinese and never render `ApiError.message`;
4. use Chinese fallback for non-API exceptions;
5. keep lock renewal failure explicit and mutation controls disabled;
6. show loading, empty and fatal workbench states in Chinese.

- [ ] **Step 8: Keep the existing run-bound Playwright regression valid**

Update `frontend/e2e/p0-workbench.spec.ts` selectors to the new Chinese accessible names while retaining its input contract (`QI_P0_PROJECT_URL`, two phases and run evidence files). Do not change geometry, item-number, download hash or no-console-error assertions.

- [ ] **Step 9: Run GREEN and full frontend gate**

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_export_atomicity.py \
  backend/tests/integration/test_export_consistency.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list
```

Expected: PASS; list includes the existing P0 Workbench test. The new bare-root test is added only in Task 5.

- [ ] **Step 10: Commit Task 4**

```bash
git add \
  backend/app/projects/router.py \
  backend/app/exports/service.py \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_export_atomicity.py \
  frontend/src/api/types.ts \
  frontend/src/copy/zhCN.ts \
  frontend/src/components/workbench/ProjectWorkbenchApp.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/RecognitionSummary.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/FreezeReviewButton.tsx \
  frontend/src/components/workbench/ExportPanel.tsx \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/pdf/PdfWorkspace.tsx \
  frontend/src/components/pdf/OverlayLayer.tsx \
  frontend/src/components/balloons/BalloonOverlay.tsx \
  frontend/src/components/balloons/BalloonToolbar.tsx \
  frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/RecognitionSummary.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/FreezeReviewButton.test.tsx \
  frontend/src/components/workbench/ExportPanel.test.tsx \
  frontend/src/components/workbench/selection.test.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/components/pdf/PdfWorkspace.test.tsx \
  frontend/src/components/pdf/OverlayLayer.test.tsx \
  frontend/src/components/balloons/BalloonOverlay.test.tsx \
  frontend/e2e/p0-workbench.spec.ts
git diff --cached --check
git commit -m "feat: localize review workbench"
```

Rollback: `git revert <task-4-commit>`。若实际 rollback，第一项验证是：

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
```

## Task 5: Prove The Bare-Root Browser Closure

**Allowed paths:**

- Create: `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`
- Modify: `frontend/playwright.config.ts`

**Runtime-only inputs/artifacts:**

- Read-only input: `$QI_MVP_E2E_PDF`
- Playwright output: `frontend/test-results/` or an explicitly configured temporary report directory
- Downloaded PDF/Excel in Playwright temporary download storage

Do not stage source PDFs, generated exports, screenshots, credentials, `.agent/harness/runs/`, `__pycache__/` or `.gstack/`.

- [ ] **Step 1: Run the RED discovery guard before the product smoke exists**

```bash
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list \
  | rg '裸根地址可完成 PDF 上传、审核和双格式下载'
```

Expected: exit `1` because no bare-root product smoke is registered yet. The existing run-bound P0 Workbench test remains listed.

- [ ] **Step 2: Write the bare-root Playwright test**

Inside `test("裸根地址可完成 PDF 上传、审核和双格式下载", async ({ page }) => {`, begin with these exact setup and entry actions:

```ts
const sourcePdf = process.env.QI_MVP_E2E_PDF;
if (!sourcePdf) throw new Error("QI_MVP_E2E_PDF is required");

await page.goto("/", { waitUntil: "networkidle" });
await expect(page).toHaveURL(/\/$/);
await expect(page.getByRole("heading", { name: "工程图纸智能检验" })).toBeVisible();
await page.getByLabel("选择工程 PDF").setInputFiles(sourcePdf);
await page.getByRole("button", { name: "上传并开始识别" }).click();
await expect(page.getByText("正在解析图纸并识别检验项")).toBeVisible();
await expect(page.getByText("识别完成，已进入审核"))
  .toBeVisible({ timeout: 10 * 60_000 });
await expect(page.getByRole("heading", { name: "检验项目审核" })).toBeVisible();
expect(new URL(page.url()).search).toBe("");
```

Continue and close that same test only through visible browser controls:

1. assert detected item count is greater than zero and drawing canvas is visible;
2. resolve required confirmations and set balloon requirement through Review controls;
3. confirm each active item's fixed SIP detail fields and save each explicit command;
4. confirm drawing/SIP metadata and save;
5. freeze items;
6. generate balloons;
7. exercise one row↔balloon selection and one drag adjustment;
8. assert no balloon blockers, hard collisions or unresolved `manual_required`;
9. Confirm Reviewed Result;
10. create formal export;
11. use Playwright `download` events to download `带气泡 PDF` and `SIP Excel`;
12. assert both downloads have non-zero bytes and expected content types/extensions;
13. assert the manifest link also exists;
14. assert page text/URL contains neither Project UUID nor operator UUID;
15. assert no console error, failed API response or silent formal success.

The browser test may use a deliberately small supported vector engineering PDF for deterministic automation, but it must go through the real upload/API/worker/database/storage/frontend stack with no route mocking. Its result is labelled product smoke, never current-four receipt evidence.

- [ ] **Step 3: Configure the same real Chrome surface**

Keep one worker, no retries, and set:

```ts
use: {
  baseURL: process.env.QI_MVP_BASE_URL ?? "http://localhost:3000",
  channel: "chrome",
  viewport: { width: 1565, height: 796 },
  locale: "zh-CN",
  timezoneId: "Asia/Hong_Kong",
  trace: "retain-on-failure",
}
```

Do not add a second Playwright config or browser-only product route.

- [ ] **Step 4: Run full static and focused prechecks**

```bash
python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_intake_api.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_project_workbench_api.py \
  backend/tests/integration/test_export_consistency.py \
  backend/tests/integration/test_export_atomicity.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list
```

Expected: all pass/list clean; no Harness or traceability drift.

- [ ] **Step 5: Start the real local stack without printing secrets**

```bash
test -f "$QI_MVP_E2E_PDF"
docker compose up -d --build postgres redis api worker frontend
micromamba run -n qi-p0 alembic -c backend/alembic.ini current | rg '0006'
curl --fail --silent http://localhost:8000/api/v1/health
curl --fail --silent http://localhost:3000/ >/dev/null
```

Run the `alembic current` command only from the existing approved local runtime shell where `QI_DATABASE_URL` is already injected; this successor adds no migration and must not print that value. If the current revision is not `0006`, stop instead of silently upgrading an unknown database. Provider configuration, when needed, comes only from the existing server-side environment. Do not echo it, write it to the repository, or pass it through browser query parameters. A vector smoke PDF must produce zero paid OCR calls; a hybrid manual acceptance may call OCR only for eligible local crops.

- [ ] **Step 6: Run the automated bare-root browser gate**

```bash
micromamba run -n qi-p0 npm --prefix frontend run e2e -- \
  e2e/chinese-pdf-upload-mvp.spec.ts
```

Expected: PASS from `/` upload to visible recognition result and actual PDF/Excel downloads, with no manually constructed internal URL.

- [ ] **Step 7: Perform one real engineering-PDF browser acceptance**

Using one approved supported engineering PDF through the same naked `/` UI:

1. select the file with the browser chooser;
2. verify upload, queued/processing and any OCR state are Chinese;
3. verify automatic candidates/source overlays appear in Workbench;
4. review every page and resolve every active/freeze blocker;
5. freeze item set, generate and adjust balloons;
6. confirm the immutable reviewed result;
7. create formal export;
8. download and open the ballooned PDF;
9. download and open the fixed SIP Excel;
10. verify the manifest link exists and all visible counts/numbers agree;
11. verify URL remains `/`, internal IDs are not shown, and browser console/network have no unexplained errors.

This is the final product acceptance. A prepared Harness project, API-only replay, deep link, HTTP 200, component test or old receipt cannot substitute for it.

- [ ] **Step 8: Run complete regression and independent review**

```bash
micromamba run -n qi-p0 pytest backend/tests -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
python .agent/harness/scripts/check-contracts.py
git diff --check
```

Request one read-only reviewer to verify:

- bare `/` is the only user product entry;
- query compatibility is bounded to verified internal consumers;
- no visible/internal-ID leakage;
- status cannot hang on a failed LogicalJob;
- native/OCR authority remains correct;
- frontend does not create formal review/balloon/export truth;
- freeze→generate→confirm→export order remains intact;
- all user-visible copy and errors are Chinese;
- browser acceptance really uploads and downloads through the product.

Any blocking review issue is fixed before rerunning the focused and browser gates.

- [ ] **Step 9: Commit Task 5**

```bash
git add \
  frontend/e2e/chinese-pdf-upload-mvp.spec.ts \
  frontend/playwright.config.ts
git diff --cached --check
git commit -m "test: prove Chinese upload MVP"
```

Rollback: `git revert <task-5-commit>`。若实际 rollback，第一项验证是：

```bash
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list
```

## Final Acceptance Gate

Implementation is complete only when all of the following are fresh on the same successor HEAD:

- `python .agent/harness/scripts/check-contracts.py` passes with no generated contract edits;
- backend full suite passes;
- frontend full Vitest suite passes;
- frontend production build passes;
- existing P0 Workbench browser test remains discoverable with Chinese selectors;
- new bare-root Playwright test passes;
- one approved engineering PDF completes the manual real-browser flow;
- the page shows detected/reviewed result data before export;
- actual ballooned PDF and SIP Excel downloads both open successfully;
- manifest link exists;
- no raw Project/operator ID appears in URL or visible UI;
- no paid Provider was called outside an explicit eligible runtime path;
- no credential, source PDF, generated export, run evidence, `__pycache__/` or `.gstack/` is staged;
- independent review has no blocking issue.

Historical receipt `20260723T042259807705Z-4e3e5f85` remains untouched and is reported only as predecessor evidence. The successor release claim is based on the fresh checks above.

## Commit And Stop Boundaries

Expected implementation commits, in order:

1. `feat: add PDF project intake API`
2. `feat: connect processing to review`
3. `feat: add Chinese PDF upload entry`
4. `feat: localize review workbench`
5. `test: prove Chinese upload MVP`

Each task stages only its listed paths. Execution stops after Task 5 verification/review/commit; it does not start project dashboards, user management, production auth, general template management or any P1/P2 work.

## Plan Self-Review

- Section 10 scope: preserved vector/hybrid support, pure-scan unsupported boundary, review/result layers, freeze/balloon/export gates and three-artifact atomic publication.
- Product target: covers naked `/`, PDF upload, real Project, processing, necessary OCR seam, automatic candidate display, Chinese progress/error/retry, existing Workbench, balloon adjustment and PDF/Excel downloads.
- Reuse: keeps the passed processing/review/balloon/export Owners; only adds intake/status/orchestration/UI entry and active OCR wiring.
- No parallel plan: this file is the only successor plan and does not modify the sealed predecessor.
- Harness: no new Harness Owner, phase, receipt or current-four claim.
- Identity: operator/project context is application-managed and never user-entered or visibly rendered.
- TDD: every task starts with explicit RED, runs a focused GREEN gate, then commits exact paths.
- Rollback: every task has a task-local revert and first post-rollback verification.
- Execution detail: every required state, endpoint, file group, command, failure behavior and final browser action is specified.
