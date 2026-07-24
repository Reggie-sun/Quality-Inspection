# Frontend QA Remaining Risks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Qwen Vision runtime 通过独立验证后，修复已确认的 processing stage、审核备注、真实 PDF 缩略图、fit-to-container、终止错误文案和高密度图纸可读性风险。

**Architecture:** 后端只增加向后兼容的真实 processing-stage projection 和 review-item optional remarks，不改变 phase、review、freeze 或 export Owner。前端消费这些事实，并在现有 `PdfWorkspace` 与 `InspectionItemTable` 内做局部交互修复；不增加路由、依赖、虚假状态或第二套工作台。

**Tech Stack:** Python 3.11、Alembic、SQLAlchemy、FastAPI、React 19、TypeScript、PDF.js、Vitest、Testing Library、Playwright、Chrome

---

## Problem Boundary

- Single Owners:
  - `LogicalJob.processing_stage` 是未完成 processing 子阶段的后端事实；
  - `ReviewService` 继续拥有 item detail save/freeze/reviewed-result；
  - `PdfWorkspace` 继续拥有 PDF page rendering、thumbnail 和 fit interaction。
- Old paths to replace:
  - frontend 把所有 processing 显示为同一句“正在解析图纸并识别检验项”；
  - `set_sip_detail_fields` 无 optional `remarks`；
  - 页码按钮只有静态页码卡片；
  - “适合页面”写死 `scale=1`；
  - fatal guidance 仅按 `retryable` 二分；
  - 非选中候选在高密度图纸上与选中项同等抢眼。
- Unchanged contracts:
  - 后端没有精确百分比，前端只显示阶段和 indeterminate progress；
  - remarks 不进入固定 SIP Excel mapping，也不是 freeze blocker；
  - 保存不等于冻结，冻结不等于确认；
  - balloon geometry、编号、collision 和 export 语义不变；
  - 无新依赖、无 `frontend/package.json` 修改。
- Focused verification:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_result_layers.py -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/app/QualityInspectionApp.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx
```

## File Structure

- Create `backend/alembic/versions/0007_processing_stage.py`: 单列、可回滚 stage migration。
- Modify `backend/app/jobs/idempotency.py`: stage enum/value validation 与 transition helper。
- Modify `backend/app/projects/schemas.py` and `service.py`: optional sanitized stage projection。
- Modify `backend/app/processing/pipeline.py`: parsing/recognizing/preparing_review transitions。
- Modify `backend/app/review/schemas.py` and `service.py`: optional remarks persistence。
- Modify `frontend/src/api/types.ts`: stage 和 remarks 类型。
- Modify `frontend/src/app/QualityInspectionApp.tsx`: 真阶段显示和类别化 fatal guidance。
- Modify `frontend/src/copy/zhCN.ts`: 中文阶段、备注和下一步文案。
- Modify `frontend/src/components/workbench/InspectionItemTable.tsx`: remarks explicit save/cancel。
- Modify `frontend/src/components/pdf/PdfWorkspace.tsx`: page thumbnails 和 fit。
- Modify `frontend/src/components/pdf/OverlayLayer.tsx` and `frontend/src/styles/workbench.css`: 不改变布局语义的密度强调。
- Modify existing focused tests and append current evidence to `design-qa.md`.

### Task 1: Persist And Project Real Processing Stages

**Files:**
- Create: `backend/alembic/versions/0007_processing_stage.py`
- Modify: `backend/app/jobs/idempotency.py`
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/tests/integration/test_schema.py`
- Modify: `backend/tests/integration/test_project_status_api.py`
- Modify: `backend/tests/integration/test_processing_entry_task.py`

- [ ] **Step 1: Write failing schema/status/transition tests**

在 `test_schema.py` 把 `logical_jobs` 精确列集合扩展为：

```python
{
    "id",
    "project_id",
    "logical_task_key",
    "status",
    "result_ref",
    "processing_stage",
}
```

在 status fixture 允许传入 `processing_stage`，并新增：

```python
@pytest.mark.parametrize(
    (
        "project_state",
        "job_status",
        "has_working_copy",
        "processing_stage",
        "expected_phase",
        "expected_stage",
    ),
    [
        ("processing", None, False, None, "queued", "queued"),
        ("processing", "processing", False, "parsing", "processing", "parsing"),
        (
            "processing",
            "processing",
            False,
            "recognizing",
            "processing",
            "recognizing",
        ),
        (
            "ready_for_edit",
            "succeeded",
            False,
            "preparing_review",
            "processing",
            "preparing_review",
        ),
        (
            "editing",
            "succeeded",
            True,
            "preparing_review",
            "ready_for_review",
            None,
        ),
        (
            "processing_failed",
            "failed",
            False,
            "recognizing",
            "failed",
            None,
        ),
    ],
)
def test_status_projects_only_active_processing_stage(
    status_context: StatusContext,
    project_state: str,
    job_status: str | None,
    has_working_copy: bool,
    processing_stage: str | None,
    expected_phase: str,
    expected_stage: str | None,
) -> None:
    project_id = _seed_project_status(
        status_context.session,
        project_state=project_state,
        job_status=job_status,
        has_working_copy=has_working_copy,
        processing_stage=processing_stage,
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json()["phase"] == expected_phase
    assert response.json().get("stage") == expected_stage
```

在 canonical task test 用 recording candidate builder 观察数据库：

```python
assert observed_stages == ["recognizing"]
assert completed_job.processing_stage == "preparing_review"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_schema.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_processing_entry_task.py -q
```

Expected: FAIL because migration/model/stage response do not exist.

- [ ] **Step 3: Add migration and model transition helper**

`0007_processing_stage.py`：

```python
"""Add logical processing stage projection.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "logical_jobs",
        sa.Column(
            "processing_stage",
            sa.String(length=32),
            server_default="queued",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_logical_jobs_processing_stage",
        "logical_jobs",
        "processing_stage IN "
        "('queued','parsing','recognizing','preparing_review')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_logical_jobs_processing_stage",
        "logical_jobs",
        type_="check",
    )
    op.drop_column("logical_jobs", "processing_stage")
```

在 `LogicalJob` 增加：

```python
processing_stage: Mapped[str] = mapped_column(
    String(32),
    default="queued",
    nullable=False,
)
```

并定义：

```python
PROCESSING_STAGES = {
    "queued",
    "parsing",
    "recognizing",
    "preparing_review",
}


def set_processing_stage(
    session: Session,
    *,
    job_id: uuid.UUID,
    stage: str,
) -> None:
    if stage not in PROCESSING_STAGES:
        raise ValueError("unknown processing stage")
    outcome = session.execute(
        update(LogicalJob)
        .where(
            LogicalJob.id == job_id,
            LogicalJob.result_ref.is_(None),
            LogicalJob.status.in_(("pending", "processing")),
        )
        .values(status="processing", processing_stage=stage)
    )
    if outcome.rowcount != 1:
        session.rollback()
        raise LogicalJobStateError("logical job cannot change processing stage")
    session.commit()
```

- [ ] **Step 4: Record stages at real transaction boundaries**

在 `InventoryPipeline.run()`：

```python
set_processing_stage(self._session, job_id=job.id, stage="parsing")
self._preflight.check()
source_path = self._storage.resolve_resource_ref(source_ref)
pages = tuple(self._inventory_builder(source_path))
inventory_ref = self._store_inventory(project_id, job, pages)
set_processing_stage(self._session, job_id=job.id, stage="recognizing")
```

在 `build_automatic_result()` 提交同一 formal result transaction 前：

```python
job.processing_stage = "preparing_review"
job.status = "succeeded"
job.result_ref = automatic_result_ref(result)
```

这样 `preparing_review` 不是 frontend 推断，也没有独立假进度。

- [ ] **Step 5: Add backward-compatible response projection**

在 `projects/schemas.py`：

```python
class ProcessingStage(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    RECOGNIZING = "recognizing"
    PREPARING_REVIEW = "preparing_review"


class ProjectStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID | None = None
    phase: ProjectPhase
    workbench_ready: bool
    retryable: bool
    error: ProjectError | None
    stage: ProcessingStage | None = None
```

`ProjectIntakeService.status()` 规则：

- working copy/failed 返回 `stage=None`；
- job 不存在的 queued phase 返回 `stage=queued`；
- processing phase 返回 DB `processing_stage`；
- `ready_for_edit + succeeded + no working` 保持 phase processing，返回
  `preparing_review`。

- [ ] **Step 6: Upgrade the test database and verify GREEN**

Run:

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_schema.py \
  backend/tests/integration/test_project_status_api.py \
  backend/tests/integration/test_processing_entry_task.py -q
```

Expected: migration head is `0007`; all selected tests PASS.

### Task 2: Optional Review Remarks Without SIP Drift

**Files:**
- Modify: `backend/app/review/schemas.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/contract/test_review_schema.py`
- Modify: `backend/tests/integration/test_review_operations.py`
- Modify: `backend/tests/integration/test_review_freeze.py`
- Modify: `backend/tests/integration/test_result_layers.py`
- Modify: `backend/tests/unit/exports/test_excel_mapping.py`

- [ ] **Step 1: Write failing command/persistence/export tests**

新增测试：

```python
def test_sip_detail_remarks_are_optional_and_bounded() -> None:
    command = {
        "type": "set_sip_detail_fields",
        "item_id": "item-1",
        "inspection_item": "直径",
        "inspection_standard": "按图纸",
        "inspection_method": "卡尺",
        "key_dimension": "是",
        "inspection_role": "IPQC",
        "source_page": 1,
    }
    parsed = parse_review_command(command)
    assert parsed.remarks == ""

    with pytest.raises(ValidationError):
        parse_review_command({**command, "remarks": "注" * 2001})
```

Integration test 保存 `"现场复核量具"` 后断言：

```python
assert saved.items[0]["remarks"] == "现场复核量具"
assert reviewed.items[0]["remarks"] == "现场复核量具"
assert raw.candidates[0]["payload"].get("remarks") is None
```

Freeze test 使用 `remarks=""` 并保持无新增 blocker。Excel mapping test 断言
existing fixed detail output 不包含 remarks。

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_review_schema.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_review_freeze.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/unit/exports/test_excel_mapping.py -q
```

Expected: FAIL because command rejects `remarks` and reviewed item cannot persist it.

- [ ] **Step 3: Implement optional remarks**

在 `review/schemas.py`：

```python
SIP_OPTIONAL_DETAIL_FIELDS = ("remarks",)


class SetSipDetailFields(CommandBase):
    type: Literal["set_sip_detail_fields"]
    item_id: str = Field(min_length=1)
    inspection_item: NonBlankText
    inspection_standard: NonBlankText
    inspection_method: NonBlankText
    key_dimension: NonBlankText
    inspection_role: NonBlankText
    source_page: int = Field(ge=1, strict=True)
    remarks: str = Field(default="", max_length=2000)
```

在 `ReviewService._apply_command()`：

```python
for field in (*SIP_DETAIL_FIELDS, *SIP_OPTIONAL_DETAIL_FIELDS):
    item[field] = values[field]
```

在 `_clear_sip_detail_fields()` 同时清除 optional fields。保持
`_sip_confirmation_blockers()` 只遍历现有 required `SIP_DETAIL_FIELDS`。
`confirm()` 已 deep-copy active working items，因此 remarks 自然进入 immutable
reviewed result；不要修改 Excel mapping。

- [ ] **Step 4: Run tests and verify GREEN**

Run Task 2 的同一 pytest command。

Expected: all selected tests PASS; empty remarks 不阻止 freeze。

### Task 3: Frontend Stage Truth And Terminal Guidance

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/app/QualityInspectionApp.tsx`
- Modify: `frontend/src/app/QualityInspectionApp.test.tsx`

- [ ] **Step 1: Write failing UI tests**

扩展 `status()` fixture 支持 `stage`，新增：

```tsx
test.each([
  ["parsing", "正在解析工程图纸"],
  ["recognizing", "正在识别检验项"],
  ["preparing_review", "正在准备审核"],
] as const)("显示真实后端阶段 %s", async (stage, label) => {
  const getProjectStatus = vi.fn().mockResolvedValue(
    status("processing", { stage }),
  );
  render(<QualityInspectionApp api={fakeApi(undefined, getProjectStatus)} />);

  expect(await screen.findByText(label)).not.toBeNull();
  expect(screen.queryByText(/%/)).toBeNull();
});


test("非重试配置错误不把有效 PDF 说成无效", async () => {
  const getProjectStatus = vi.fn().mockResolvedValue(
    status("failed", {
      retryable: false,
      error: {
        code: "vision_provider_unavailable",
        stage: "preflight",
      },
    }),
  );
  render(<QualityInspectionApp api={fakeApi(undefined, getProjectStatus)} />);

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("若文件有效，请联系管理员检查服务配置");
  expect(alert.textContent).not.toContain("有效的工程 PDF");
  expect(screen.queryByRole("button", { name: "重新处理" })).toBeNull();
});
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/app/QualityInspectionApp.test.tsx
```

Expected: FAIL because `stage` is absent and fatal guidance still uses retryable-only copy.

- [ ] **Step 3: Implement typed stage mapping**

在 `api/types.ts`：

```ts
export type ProcessingStage =
  | "queued"
  | "parsing"
  | "recognizing"
  | "preparing_review";

export type ProjectStatus = {
  project_id?: string;
  phase: ProjectPhase;
  workbench_ready: boolean;
  retryable: boolean;
  error: {
    code: string;
    stage: string;
  } | null;
  stage?: ProcessingStage;
};
```

将 `ProductScreen.processing.phase` 改为同一四值 union，并增加：

```ts
function processingPhase(result: ProjectStatus): ProcessingStage {
  if (result.stage !== undefined) return result.stage;
  return result.phase === "queued" ? "queued" : "recognizing";
}
```

`statusText()` 精确映射：

```ts
if (screen.phase === "queued") return zhCN.status.queued;
if (screen.phase === "parsing") return zhCN.status.parsing;
if (screen.phase === "recognizing") return zhCN.status.recognizing;
return zhCN.status.preparing;
```

`activeStage()` 只有 `preparing_review` 进入审核准备 rail；其余 processing 保持识别阶段。

- [ ] **Step 4: Implement category-based fatal guidance**

在 `zhCN.ts` 增加：

```ts
export function projectErrorGuidance(
  code: string,
  retryable: boolean,
): string {
  if (code === "invalid_pdf" || code === "unsupported_input") {
    return "未生成正式检验结果，请重新选择符合支持范围的工程 PDF。";
  }
  if (retryable) {
    return "未生成正式检验结果，请重新处理或选择其他文件。";
  }
  return "未生成正式检验结果，请重新选择 PDF；若文件有效，请联系管理员检查服务配置。";
}
```

增加 `vision_provider_call_failed` 中文错误；fatal alert 使用
`projectErrorGuidance(screen.code, screen.retryable)`。`retryable` 只控制“重新处理”
button，不再单独生成语义。

- [ ] **Step 5: Run tests and verify GREEN**

Run Task 3 的同一 Vitest command。

Expected: all selected tests PASS; DOM 不含百分比。

### Task 4: Frontend Remarks Explicit Save And Cancel

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`

- [ ] **Step 1: Write failing remarks tests**

新增：

```tsx
test("备注可以为空并随显式保存提交", () => {
  const onCommand = vi.fn();
  const onDraftChange = vi.fn();
  render(
    <InspectionItemTable
      items={[{
        item_id: "item-1",
        raw_text: "M6",
        item_type: "thread",
        inspection_item: "螺纹",
        inspection_standard: "按图纸",
        inspection_method: "螺纹规",
        key_dimension: "是",
        inspection_role: "IPQC",
        source_page: 1,
        remarks: "",
        active: true,
      }]}
      balloons={[]}
      filter="all"
      selectedItemId="item-1"
      onSelectItem={vi.fn()}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.change(screen.getByLabelText("备注（可选）：M6"), {
    target: { value: "首件需复核" },
  });
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "确认所选 SIP 字段" }));

  expect(onCommand).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "set_sip_detail_fields",
      remarks: "首件需复核",
    }),
  );
});


test("取消备注修改恢复服务端 baseline", () => {
  const onDraftChange = vi.fn();
  render(
    <InspectionItemTable
      items={[{
        item_id: "item-1",
        raw_text: "M6",
        item_type: "thread",
        inspection_item: "螺纹",
        inspection_standard: "按图纸",
        inspection_method: "螺纹规",
        key_dimension: "是",
        inspection_role: "IPQC",
        source_page: 1,
        remarks: "原备注",
        active: true,
      }]}
      balloons={[]}
      filter="all"
      selectedItemId="item-1"
      onSelectItem={vi.fn()}
      onCommand={vi.fn()}
      onDraftChange={onDraftChange}
    />,
  );
  const remarks = screen.getByLabelText(
    "备注（可选）：M6",
  ) as HTMLTextAreaElement;
  fireEvent.change(remarks, { target: { value: "本地修改" } });
  fireEvent.click(screen.getByRole("button", { name: "取消 SIP 字段修改" }));

  expect(remarks.value).toBe("原备注");
  expect(onDraftChange).toHaveBeenLastCalledWith(false);
});
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/workbench/InspectionItemTable.test.tsx
```

Expected: FAIL because remarks field/type is absent.

- [ ] **Step 3: Implement optional draft field**

在 `ReviewItem` 和 `set_sip_detail_fields` command 增加 `remarks?: string` /
`remarks: string`。`DetailDraft` 增加 `remarks`，baseline 使用
`item?.remarks ?? ""`。

在 required input map 后增加：

```tsx
<label>
  {zhCN.inspection.remarks}
  <textarea
    aria-label={`${zhCN.inspection.remarks}：${selected.raw_text}`}
    maxLength={2000}
    rows={3}
    value={draft.remarks}
    onChange={(event) => updateDraft({ remarks: event.target.value })}
  />
</label>
```

保存 button 只检查五个 required text fields 和 `sourcePage`，不把空 remarks
当 blocker；command payload 明确包含 `remarks: draft.remarks`。

- [ ] **Step 4: Run tests and verify GREEN**

Run Task 4 的同一 Vitest command。

Expected: all selected tests PASS; dirty/save/cancel 状态保持 explicit。

### Task 5: Real PDF Thumbnails And Fit-To-Container

**Files:**
- Modify: `frontend/src/components/pdf/PdfWorkspace.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- Modify: `frontend/src/styles/workbench.css`

- [ ] **Step 1: Write failing thumbnail and fit tests**

新增：

```tsx
test("每个页码按钮渲染独立真实缩略图", async () => {
  const pdfDocument = documentFixture();
  render(
    <PdfWorkspace
      pdfDocument={pdfDocument}
      candidates={[]}
      sources={[]}
      balloons={[]}
    />,
  );

  await waitFor(() => {
    expect(screen.getByTestId("pdf-thumbnail-1").hasAttribute("hidden")).toBe(false);
    expect(screen.getByTestId("pdf-thumbnail-2").hasAttribute("hidden")).toBe(false);
  });
  expect(pdfDocument.getPage).toHaveBeenCalledWith(1);
  expect(pdfDocument.getPage).toHaveBeenCalledWith(2);
});


test("单页缩略图失败只显示中文页码 fallback", async () => {
  const pdfDocument: PdfDocumentLike = {
    numPages: 2,
    getPage: vi.fn(async (pageNumber: number) => {
      if (pageNumber === 2) throw new Error("thumbnail failed");
      return {
        getViewport: ({ scale }: { scale: number }) => ({
          width: 100 * scale,
          height: 200 * scale,
        }),
        render: vi.fn(() => ({
          promise: Promise.resolve(),
          cancel: vi.fn(),
        })),
      };
    }),
  };
  render(
    <PdfWorkspace
      pdfDocument={pdfDocument}
      candidates={[]}
      sources={[]}
      balloons={[]}
    />,
  );

  expect(await screen.findByText("第 2 页预览不可用")).not.toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});


test("适合页面使用容器尺寸并清零 pan", async () => {
  render(
    <PdfWorkspace
      pdfDocument={rotatedDocumentFixture()}
      candidates={[]}
      sources={[]}
      balloons={[]}
    />,
  );
  const frame = screen.getByTestId("pdf-scroll-frame");
  Object.defineProperties(frame, {
    clientWidth: { configurable: true, value: 424 },
    clientHeight: { configurable: true, value: 224 },
  });
  fireEvent.click(screen.getByRole("button", { name: "向右平移" }));
  fireEvent.click(screen.getByRole("button", { name: "适合页面" }));

  expect(screen.getByLabelText("缩放比例").textContent).toBe("200%");
  expect(screen.getByTestId("pdf-page-layer").getAttribute("style")).toContain(
    "transform: translate(0px, 0px)",
  );
});
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/pdf/PdfWorkspace.test.tsx
```

Expected: FAIL because thumbnails are static spans and fit returns 100%.

- [ ] **Step 3: Add isolated thumbnail renderer**

在同一文件内增加 `PdfThumbnail`，不创建第二个 PDF document：

```tsx
function PdfThumbnail({
  pdfDocument,
  pageIndex,
}: {
  pdfDocument: PdfDocumentLike | null;
  pageIndex: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    setAvailable(false);
    if (pdfDocument === null) return;
    let cancelled = false;
    let task: PdfRenderTaskLike | undefined;
    void (async () => {
      try {
        const page = await pdfDocument.getPage(pageIndex + 1);
        const base = page.getViewport({ scale: 1 });
        const thumbnailScale = Math.min(48 / base.width, 52 / base.height);
        const viewport = page.getViewport({ scale: thumbnailScale });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (cancelled || canvas === null || context == null) return;
        canvas.width = Math.max(1, Math.round(viewport.width));
        canvas.height = Math.max(1, Math.round(viewport.height));
        task = page.render({ canvasContext: context, viewport });
        await task.promise;
        if (!cancelled) setAvailable(true);
      } catch (error) {
        if (
          !cancelled
          && !(error instanceof Error
            && error.name === "RenderingCancelledException")
        ) {
          setAvailable(false);
        }
      }
    })();
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pageIndex, pdfDocument]);

  return (
    <>
      <canvas
        ref={canvasRef}
        data-testid={`pdf-thumbnail-${pageIndex + 1}`}
        hidden={!available}
        aria-hidden="true"
      />
      {available ? null : (
        <span>{zhCN.pdf.thumbnailUnavailable(pageIndex + 1)}</span>
      )}
    </>
  );
}
```

页码 button 保留 `aria-current` 和中文 accessible name，内部改用
`<PdfThumbnail />`。

- [ ] **Step 4: Implement actual fit**

给 `.pdf-scroll-frame` 增加 `scrollFrameRef` 和 `data-testid`。Click handler：

```ts
const frame = scrollFrameRef.current;
if (
  frame === null
  || frame.clientWidth <= 24
  || frame.clientHeight <= 24
  || pageSize.width <= 0
  || pageSize.height <= 0
) return;
const fitted = Math.min(
  (frame.clientWidth - 24) / pageSize.width,
  (frame.clientHeight - 24) / pageSize.height,
);
setScale(Math.min(4, Math.max(0.1, fitted)));
setPan({ x: 0, y: 0 });
```

如果尺寸不可测，不修改 scale/pan。CSS 将 thumbnail column 调整为能容纳 48px
canvas，保持 PDF 主区域仍为最大区域。

- [ ] **Step 5: Run tests and verify GREEN**

Run Task 5 的同一 Vitest command。

Expected: all selected tests PASS; cancellation 不产生 unhandled rejection。

### Task 6: Dense Drawing Visual Hierarchy

**Files:**
- Modify: `frontend/src/components/pdf/OverlayLayer.tsx`
- Modify: `frontend/src/components/pdf/OverlayLayer.test.tsx`
- Modify: `frontend/src/styles/workbench.css`

- [ ] **Step 1: Write a failing semantic-class test**

新增：

```tsx
test("非选中候选与来源提供可聚焦的密度层级 class", () => {
  render(
    <OverlayLayer
      pageWidth={100}
      pageHeight={100}
      scale={1}
      candidates={[{
        id: "c1",
        itemId: "item-1",
        candidateNumber: 1,
        bbox: [10, 10, 30, 30],
      }]}
      sources={[{
        id: "s1",
        itemId: "item-1",
        bbox: [10, 10, 30, 30],
      }]}
      balloons={[]}
      onSelectItem={vi.fn()}
    />,
  );

  expect(screen.getByTestId("candidate-c1").classList.contains(
    "pdf-overlay-candidate",
  )).toBe(true);
  expect(screen.getByTestId("source-s1").classList.contains(
    "pdf-overlay-source",
  )).toBe(true);
  const marker = screen.getByTestId("candidate-number-c1");
  expect(marker.classList.contains("pdf-overlay-candidate-marker")).toBe(true);
  expect(marker.getAttribute("data-selected")).toBe("false");
});
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/pdf/OverlayLayer.test.tsx
```

Expected: FAIL because semantic classes do not exist.

- [ ] **Step 3: Add presentation-only density hierarchy**

增加 className，不改变 marker selection/placement：

```tsx
className="pdf-overlay-candidate"
className="pdf-overlay-source"
className="pdf-overlay-candidate-leader"
className="pdf-overlay-candidate-marker"
```

CSS：

```css
.pdf-overlay-candidate,
.pdf-overlay-source,
.pdf-overlay-candidate-leader,
.pdf-overlay-candidate-marker {
  opacity: 0.58;
}

.pdf-overlay-candidate[data-selected="true"],
.pdf-overlay-source[data-selected="true"],
.pdf-overlay-candidate-marker[data-selected="true"],
.pdf-overlay-candidate:hover,
.pdf-overlay-source:hover,
.pdf-overlay-candidate-marker:hover,
.pdf-overlay-candidate-marker:focus-visible {
  opacity: 1;
}

.pdf-overlay-candidate-marker:focus-visible {
  outline: none;
}

.pdf-overlay-candidate-marker:focus-visible circle {
  stroke-width: 3;
}
```

正式红色 balloon 不降 opacity；collision/manual_required 语义不改。现有
`prefers-reduced-motion` 规则继续适用，不新增 animation。

- [ ] **Step 4: Run overlay/PDF tests**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run \
  src/components/pdf/OverlayLayer.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
```

Expected: all selected tests PASS.

### Task 7: Full Regression, Chrome QA And Evidence

**Files:**
- Append only: `design-qa.md`
- Runtime-only, never stage: `.local/design-qa/*.png`
- Do not modify: `frontend/package.json`, sealed plans/receipts, `.agent/harness/runs/`.

- [ ] **Step 1: Run mandatory static/backend/frontend gates**

Run:

```bash
python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest backend/tests -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list
```

Expected: all commands exit 0; existing P0 Workbench Playwright specs remain listed.

- [ ] **Step 2: Rebuild and health-check the current stack**

Run:

```bash
docker compose up -d --build postgres redis api worker frontend
curl --fail --silent http://localhost:8000/api/v1/health
curl --fail --silent http://localhost:3001/ >/dev/null
```

Expected: health checks pass. Do not alter current uncommitted `compose.yaml`.

- [ ] **Step 3: Run the real upload E2E when configured**

Check presence only:

```bash
test -n "${QI_MVP_E2E_PDF:-}"
```

If exit 0:

```bash
micromamba run -n qi-p0 npm --prefix frontend run e2e -- \
  e2e/chinese-pdf-upload-mvp.spec.ts
```

If absent, record exactly “未运行：`QI_MVP_E2E_PDF` 未配置”，不得 invent a path.

- [ ] **Step 4: Chrome QA at all required viewports**

Use real Chrome with locale `zh-CN`, timezone `Asia/Hong_Kong`, device scale 1:

```text
1565×796
1366×768
1180×800
```

Verify with browser accessibility tree plus keyboard interaction:

- parsing、recognizing、preparing_review use real stage and `aria-live`；
- no percentage；
- real page thumbnails render and page buttons remain keyboard reachable；
- fit changes scale from measured container and resets pan；
- remarks save/cancel and frozen disable state；
- nonretry Provider/config error guidance does not accuse the PDF；
- selected candidate/source remains visually dominant；
- PDF remains the largest visual area；
- no UUID/Provider/path/raw error appears；
- no unexplained console or network error。

- [ ] **Step 5: Capture current screenshots and hashes**

Store under untracked `.local/design-qa/`:

```text
13-processing-parsing.png
14-processing-recognizing.png
15-real-thumbnails-fit.png
16-item-remarks.png
17-dense-overlay-focus.png
18-workbench-1180.png
```

Compute:

```bash
sha256sum .local/design-qa/1{3,4,5,6,7,8}-*.png
```

Do not add screenshots, PDFs, Excel files, downloads or Playwright artifacts to Git.

- [ ] **Step 6: Append a new evidence section**

先运行 `git rev-parse HEAD`，再用 `apply_patch` append（never rewrite history）
`## 2026-07-24 Qwen Runtime And Remaining-Risk Closure`。章节必须直接写入该命令
实际返回的完整 commit SHA，并逐项写入：

- user-confirmed manufacturing workbench reference identity；
- 1565×796、1366×768、1180×800；
- count-only live Qwen evidence；
- 每张 screenshot path 和实际 SHA-256；
- console/network 的实际错误数和解释；
- keyboard、focus-visible、aria-live、alert、busy、labels 结果；
- six approved initial risks、exact fixed file mapping、evidenced remainder；
- final pass/blocked verdict。

### Task 8: Independent Review And Final Commit

**Files:**
- All files changed by both implementation plans.
- Reviewer authority: read-only; no nested delegation.

- [ ] **Step 1: Run final pre-review checks**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Confirm `frontend/package.json`, package lockfiles, `.env`, `.env.example`,
`compose.yaml`, `.agent/harness/runs/`, screenshots and downloads are not staged.

- [ ] **Step 2: Invoke one read-only Reviewer**

Reviewer must inspect current worktree and verify:

- Qwen is a bounded Advisor and deterministic Owner remains unchanged；
- real production task calls it only for eligible local crops；
- no credential/raw body/internal refs leak；
- no fake request IDs, fake logs or fake progress remain；
- PDF remains largest workspace；
- thumbnails/fit/stage/remarks/error guidance are truthful and accessible；
- save → freeze → balloon → confirm → export sequence is unchanged；
- no dependency or business Owner was added；
- tests/screenshots match current source state。

Required output: verdict, blocking findings, non-blocking concerns, file/test
evidence and minimal follow-up. Reviewer must not edit files or dispatch agents.

- [ ] **Step 3: Fix and reverify blocking findings**

For each verified blocker, add a failing focused test, observe RED, make the
smallest in-scope correction, rerun the focused test, then rerun every affected
gate from Task 7. Do not address unrelated P2 cleanup.

- [ ] **Step 4: Run the final fresh verification**

Run:

```bash
python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest backend/tests -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
git diff --check
```

Expected: all pass, P0 count is zero, reviewer blocking count is zero, and
console/network have no unexplained errors.

- [ ] **Step 5: Stage only owned files and commit**

Use explicit `git add` paths for the two new implementation plans, product code,
tests and appended `design-qa.md`. Never use `git add .`.

Run:

```bash
git commit -m "fix: close Chinese MVP design QA issues"
```

Expected: commit succeeds; unrelated pre-existing dirty files remain unstaged.

- [ ] **Step 6: Verify commit identity and artifact exclusion**

Run:

```bash
git show --stat --oneline --decorate HEAD
git status --short
git ls-tree -r --name-only HEAD | rg \
  '(^\\.local/design-qa/|frontend/test-results|playwright-report|\\.pdf$|\\.xlsx$)' \
  && exit 1 || true
```

Expected: commit includes no runtime screenshots/downloads/test artifacts and
working tree still shows only preserved unrelated user changes/untracked caches.
