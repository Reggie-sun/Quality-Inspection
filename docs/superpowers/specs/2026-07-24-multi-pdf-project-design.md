# Multi-PDF Project Design

**Status:** Approved in conversation on 2026-07-24; pending written-spec review

## Problem Statement

当前系统把一个 `Project` 固定绑定到一份 `source.pdf`。左侧缩略图因此只能表示
该 PDF 的内部页，顶部“处理另一份图纸”则会清空当前项目并返回上传入口。

目标产品语义不同：

- 一个检验项目可以包含多份 PDF；
- 左侧每张卡片代表一份 PDF 文件，而不是一页；
- “增加 PDF”把新文件加入当前项目，不创建无关联项目；
- 选中 PDF 后，现有页码控件只浏览该 PDF 的内部页；
- 审核、冻结、编号和正式导出仍是项目级闭环。

这不是按钮改名，而是从“单项目单文档”迁移到“单项目多文档”。它会改变稳定
schema、API、处理归属和正式导出结构，因此选择 `Heavy` lane。

## Plan Relationship

本设计是当前七天 P0 之后的 successor capability。它不静默替换
`docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`，也不把多 PDF
能力解释为现有 Section 10 P0 已交付内容。

只有用户复核本 spec、批准对应 implementation plan 并明确切换 current plan 后，
才能开始实现。现有 P0 receipt、run evidence 和 immutable result 不得被本设计反向
改写。

## Confirmed Product Decisions

- 左侧一张卡片代表一份 PDF 文件。
- 每份 PDF 可以包含多页；选中文档后在工具栏内部翻页。
- 只允许在项目冻结前增加 PDF。
- 多 PDF 项目正式输出为：
  - 每份源 PDF 一份对应的带气泡 PDF；
  - 一份项目级汇总 SIP Excel；
  - 一份项目级 manifest。
- 气泡编号按 PDF 上传顺序、再按 PDF 内部页序全项目连续且唯一。
- 产品名称、图号、版本、材质等 SIP 基本信息按 PDF 独立保存。
- 冻结前允许删除误加 PDF，但必须二次确认并删除它的派生业务状态。

## Goals

1. 为项目建立一等 PDF 文档集合，保持稳定上传顺序和文档身份。
2. 支持在当前项目内增加、选择、重试和冻结前移除 PDF。
3. 独立处理每份 PDF，同时把候选项合入同一个项目 working copy。
4. 为检验项、来源、气泡和页坐标建立明确的 `document_id` 归属。
5. 保留现有人工审核修改，不因另一份 PDF 处理完成而覆盖。
6. 在整个项目内生成连续且唯一的正式气泡编号。
7. 从同一个 immutable reviewed result 原子发布 N 份带气泡 PDF、SIP Excel 和
   manifest。
8. 将现有单 PDF 项目无损迁移为仅含第一份文档的多 PDF 项目。

## Non-Goals

- 不允许在冻结、确认或正式导出后追加或删除 PDF。
- 不实现跨项目合并，也不把每份 PDF 建成独立 `Project`。
- 不把多份 PDF 预合并成一个 synthetic source PDF。
- 不提供用户可选的编号策略。
- 不为每份 PDF 生成独立 SIP Excel 或独立 manifest。
- 不改变 native parse、OCR、Vision Advisor、coverage、review command 或碰撞判断
  的既有 Owner。
- 不修改、覆盖或重新解释已经存在的 immutable automatic result、reviewed result
  和正式导出。
- 不新增第二套 workflow、项目集合 Owner 或 frontend 持久化真相。

## Selected Architecture

### Project And Document Ownership

`Project` 继续拥有一次完整检验任务，包括：

- 编辑锁；
- 项目级 working copy；
- freeze gate；
- 全局气泡编号；
- immutable reviewed result；
- 原子正式导出。

新增 `ProjectDocument`，拥有项目内一份 PDF 的稳定事实：

- `document_id`；
- `project_id`；
- source stored file；
- 原始显示文件名；
- 上传顺序；
- 处理状态和安全错误码；
- 文档版本；
- 创建时间。

每份 PDF 的页清单、automatic result 和 SIP metadata 都必须能追溯到唯一
`ProjectDocument`。Frontend 只消费后端 projection，不拥有文档顺序、处理状态或
冻结资格。

### Canonical Data Flow

```text
Project
→ add ProjectDocument
→ validate and persist source PDF
→ document-scoped parse / OCR / candidate processing
→ immutable document AutomaticResult
→ append document candidates into project ReviewWorkingCopy
→ review all documents
→ freeze complete document set
→ project-wide balloon numbering
→ immutable ReviewedResult with document snapshots
→ N ballooned PDFs + one SIP Excel + one manifest
```

增加 PDF 不重建现有 working copy。新的 automatic result 进入后，backend 在项目行
锁和 working-copy 行锁下只追加该文档的候选项、coverage 和 SIP 初始值，并递增
working version。已有人工命令结果不得被重新投影覆盖。

## Data Model

### Project Documents

新增 `project_documents`：

| Field | Contract |
| --- | --- |
| `id` | PDF 文档稳定 UUID |
| `project_id` | 所属项目 |
| `source_file_id` | 唯一 source `StoredFile` |
| `display_name` | 经过安全处理的原文件名，仅用于界面和下载名 |
| `sort_order` | 项目内不可复用的上传顺序 |
| `state` | `processing / ready / failed / removed` |
| `error_code` | 可选安全错误码，不保存原始 provider message |
| `version` | 乐观并发版本 |
| `created_at` | 上传时间 |

同一项目内 active 文档的 source SHA-256 重复时返回 `document_duplicate`，不创建
第二张卡片。`removed` 是逻辑删除；文档不再参与审核和导出，物理文件清理由独立
retention policy 负责。

### Automatic Results

`automatic_results` 增加不可为空的 `document_id`。一个文档可以因显式重试产生多个
immutable automatic result，但只有最新成功且被 working copy 引用的结果是 active
输入。

所有 candidate、coverage entry 和 source location 的稳定身份必须包含
`document_id`。不同 PDF 中相同文字、坐标或页码不得发生 identity collision。

### Working Copy

项目仍只有一个 `ReviewWorkingCopy`。新增
`review_working_copy_documents` 关联：

| Field | Contract |
| --- | --- |
| `working_copy_id` | 项目 working copy |
| `document_id` | active PDF |
| `automatic_result_id` | 当前采用的 immutable automatic result |
| `sip_metadata` | 该 PDF 独立 SIP 基本信息 |

`ReviewWorkingCopy.items` 和 `coverage` 中每条业务记录都携带 `document_id`。
现有单一 `raw_result_id` 和项目级 `sip_metadata` 在迁移完成后退出 active schema，
不得与新关联并存为第二 Owner。

### Balloons

`balloons` 增加不可为空的 `document_id`。`page_index` 只表示该 PDF 内部页码。

正式编号唯一性仍以项目为范围：

```text
project_id + formal_number
```

确定性排序为：

```text
document.sort_order
→ page_index
→ existing within-page item ordering
→ stable item identity
```

删除文档时，该文档 active balloons 被删除，working copy 的
`numbering_stale=true`，再次生成时全项目重新建立连续编号。

### Reviewed Results

immutable reviewed result 必须封存：

- 文档 ID、上传顺序、显示名、source SHA-256 和页数；
- 每份文档的 SIP metadata；
- 带 `document_id` 的 items、coverage 和 balloons；
- working-copy version 和 schema version。

使用独立 `reviewed_result_documents` snapshot 表保存文档级冻结事实。迁移可以为旧
reviewed result 回填一条文档 snapshot，而不建立永久 legacy readthrough。

### Export Artifacts

`ExportArtifact` 的 `ballooned_pdf` 允许多条，并增加 `document_id`：

- `ballooned_pdf`：`document_id` 必填；
- `sip_excel`：`document_id` 为空且每个 export 唯一；
- `manifest`：`document_id` 为空且每个 export 唯一。

唯一性由 `export_id + kind + document_id` 的明确 partial indexes 保证，不依赖
nullable-column 的隐式行为。

## API Design

保留 `POST /api/v1/projects`，但它内部创建项目及第一份 `ProjectDocument`。

新增：

```text
POST   /api/v1/projects/{project_id}/documents
GET    /api/v1/projects/{project_id}/documents/{document_id}/source-pdf
POST   /api/v1/projects/{project_id}/documents/{document_id}/retry
DELETE /api/v1/projects/{project_id}/documents/{document_id}
```

Mutation 必须携带当前 operator identity、项目编辑锁和 expected version。增加与删除
在以下状态返回稳定错误：

- `project_documents_frozen`：items 已冻结；
- `project_reviewed`：已有 immutable reviewed result；
- `document_duplicate`：同项目 active source SHA 重复；
- `document_processing`：对未完成文档执行不允许的操作；
- `document_not_found`；
- `document_version_conflict`。

Workbench projection 增加：

```text
documents[]
  id
  display_name
  sort_order
  state
  page_count
  source_pdf_url
  pages[]
    page_index
    width
    height
    pdf_to_render_matrix
    render_to_pdf_matrix
  version
  sip_metadata
```

当前选中文档属于 frontend 本地视图状态，不写入业务数据库。Workbench 中的
candidate、source、balloon 和 page projection 都携带 `document_id`。

### Old Path Retirement

现有：

```text
GET /api/v1/projects/{project_id}/source-pdf
```

当前 verified real consumer 只有 `ProjectWorkbenchApp`。新 frontend 在同一变更中
迁移到 document endpoint，旧入口执行 `remove`，不保留 fallback、readthrough、
shadow endpoint 或第二 source owner。

## UI And Interaction Design

### Product Header

“处理另一份图纸”替换为“增加 PDF”：

- 每次选择一份 PDF；
- 成功后留在当前工作台；
- processing 期间禁止重复提交同一文件；
- items 冻结后按钮禁用，并显示“项目已冻结，不能增加 PDF”。

返回全新项目上传入口不再由该按钮承担。若未来需要项目切换，应另行设计，不在本
spec 内复用“增加 PDF”。

### PDF Document Rail

当前 `.pdf-thumbnails` 页缩略图栏改为 PDF 文档栏。每张卡片显示：

- 首页缩略图；
- “图纸 1 / 图纸 2 …”；
- 截断后的文件名，完整值通过 title/accessible description 提供；
- 总页数；
- `处理中 / 可审核 / 处理失败` 状态。

卡片 accessible name 示例：

```text
图纸 2，base-plate.pdf，共 3 页，可审核
```

卡片不再使用“第1页/第2页”表示文件。选中文档后，工具栏已有
`上一页 / 当前页 / 总页数 / 下一页` 只控制该 PDF 的内部页。

### Adding, Retry And Removal

增加 PDF 后立即插入 processing 卡片。其他 ready 文档仍可查看和编辑，但 freeze
始终禁用，直到所有 active 文档 ready 且通过既有 blocker gates。

失败卡片显示安全中文原因，并提供：

- “重试处理”；
- “移除 PDF”。

processing 文档可以取消并移除；后台任务即使稍后返回，也必须因 document state/version
不匹配而丢弃结果。ready 文档在冻结前也可以移除，但必须确认：

```text
移除此 PDF 将删除它的检验项和气泡，并重新生成项目编号。是否继续？
```

确认后只清除该 `document_id` 的派生状态，不重置其他文档。

### SIP And Formal Files

辅助面板中的 SIP 基本信息跟随当前选中 PDF。正式文件区域保持项目级：

- 每份 PDF 一条带气泡 PDF 下载；
- 一条汇总 SIP Excel；
- 一条 manifest；
- 全部不可用时不显示任何部分成功下载。

## Export Contract

导出只消费同一个 immutable reviewed result。流程为：

```text
reviewed document snapshots
→ render one ballooned PDF per document
→ build project SIP Excel
→ build project manifest
→ validate every artifact
→ atomically publish N + 2 artifacts
```

SIP Excel 每行至少包含：

- source PDF display name；
- document sort order；
- PDF 内部页码；
- project-wide formal balloon number；
- inspection item、value/tolerance、method、standard、role；
- 文档级 SIP metadata。

Manifest 记录文档顺序、source SHA-256、页数、每个 artifact SHA-256、reviewed result
identity 和 mapping/renderer/template versions。

任一 PDF 渲染、Excel mapping 或 manifest 校验失败时，export job 为 failed，不发布
任何下载。

## Concurrency And Failure Handling

- Add/remove/retry 使用项目编辑锁和 expected version。
- Background document completion 使用 database row lock，把新文档结果幂等合入
  最新 working copy。
- 相同 `document_id + automatic_result_id` 只能应用一次。
- 用户编辑与文档处理完成并发时，只追加新文档状态，不重算或覆盖其他文档 items。
- 删除与后台完成竞态由 document version/state gate 阻断；removed 文档结果不得重新
  进入 working copy。
- 单文档失败不把整个项目变成 fatal；项目保持可打开，freeze gate 明确列出失败文档。
- 错误文案不得显示内部 UUID、storage ref、provider message 或 stack trace。

## Migration

迁移步骤必须在 implementation plan 中拆分并逐层验证：

1. 添加 document、working-copy document、reviewed-result document 和 artifact
   identity schema。
2. 为 ready/reviewed 项目从 working copy 当前引用的
   `AutomaticResult.source_file_id` 和 inventory 回填第一份 `ProjectDocument`；为仍在
   processing/failed 的项目从 canonical stored resource 和 logical job identity
   回填。任何无法唯一关联的项目都阻断 migration。
3. 为 working items、coverage、balloons 和 reviewed snapshots 回填
   `document_id`。
4. 验证每个现有项目恰好有可追溯 active 文档，且 source SHA、页数和导出保持一致。
5. 迁移 producer 和 consumer。
6. 删除单一 `source-pdf` endpoint 及单一 raw-result/SIP active ownership。
7. 收紧 non-null、foreign key 和 unique constraints。

迁移不得修改 immutable 业务内容，只补充可由当前 source/result 证明的文档身份。

## Rollback

- 在任何多 PDF 数据产生前，可以回滚应用版本；新增 schema 保持 additive，不要求破坏性
  downgrade。
- 一旦生产中创建了多 PDF 项目，不允许回滚到只理解单 PDF 的旧 binary。此时唯一安全
  回退是关闭“增加 PDF”入口、保留已有数据并 roll forward 修复。
- migration preflight、backfill count、orphan count、document/source hash 对账和旧项目
  smoke 任一失败时，不启用新 endpoint。
- 不使用长期 feature flag、dual write 或 legacy source readthrough 隐藏迁移失败。

## Verification

### Schema And Migration

- 现有单 PDF 项目回填为一份 document。
- working items、balloons、reviewed snapshots 和 artifacts 无 orphan。
- document identity、source file 和 inventory 一一可追溯。
- migration 前后旧项目的 source SHA、页数、item 数和正式下载 hash 语义一致。

### Backend

- 新建项目自动创建第一份 document。
- 冻结前增加 PDF 成功；重复 PDF 被拒绝。
- 文档失败可重试或移除，其他文档状态不丢失。
- 文档完成并发于人工保存时保留既有修改。
- 冻结后 add/delete/retry mutation 被拒绝。
- 相同页码或文字在不同 PDF 中不发生 stable-ID collision。
- 全局 formal number 连续且项目内唯一。
- N 份 ballooned PDF、SIP Excel 和 manifest 同一 reviewed result 原子发布。
- 任一 artifact 失败时零下载发布。

### Frontend

- 上传一份两页 PDF 时，左侧只有一张 PDF 卡片，工具栏显示内部 `1 / 2`。
- 增加第二份 PDF 后，左侧出现第二张文件卡片且当前项目不重置。
- 切换 PDF 后 canvas、候选、气泡、页码和 SIP metadata 同步切换。
- processing/failed/ready 状态和 freeze gate 中文准确。
- 删除确认只移除目标 PDF。
- 冻结后“增加 PDF”禁用。
- 正式文件区按 PDF 显示 N 条气泡 PDF，并显示唯一 SIP Excel 与 manifest。

### Live Browser Smoke

使用真实两份工程 PDF，其中至少一份为多页：

```text
create project with PDF A
→ add PDF B
→ review document-scoped items and SIP metadata
→ freeze all documents
→ generate globally numbered balloons
→ confirm reviewed result
→ export and download N + 2 artifacts
```

验证：

- 左侧卡片数等于 PDF 文件数，不等于总页数；
- 每份 PDF 内部翻页正确；
- 无可见内部 ID；
- 无页面级横向溢出；
- console errors、unexpected request failures 和 HTTP `>= 400` 为 0；
- 每份输出 PDF 只包含对应 source document 的页面与气泡；
- SIP Excel 与 manifest 能追溯全部 PDF 和全局编号。

## Risks

- 当前 working copy 直接绑定单一 raw result，迁移需要明确退出旧 Owner，不能只在 JSON
  中叠加第二套来源。
- 文档处理完成与人工编辑并发时，错误的全量重建会丢失用户修改；必须使用幂等 append
  merge。
- 多 `ballooned_pdf` artifact 会改变当前“恰好三份下载”P0 contract；implementation
  plan 必须先更新长期 contract matrix 和 traceability，不得沿用旧 artifact count。
- immutable historical rows 的 document backfill 必须经过 migration 专用路径，不得在
  runtime 静默修补。
- 多 PDF 数据产生后不能安全回滚到旧 binary，因此 activation gate 必须晚于完整迁移和
  live smoke。

## Acceptance Criteria

- 一个项目可以包含至少两份 PDF，且其中任一 PDF 可以多页。
- 左侧一张卡片严格对应一份 PDF。
- 顶部操作为“增加 PDF”，不会清空当前项目。
- 冻结前可增加、重试、移除；冻结后全部被稳定 gate 阻断。
- 文档级 SIP、页、检验项和气泡归属无歧义。
- 正式编号全项目连续且唯一。
- 正式导出为 N 份对应气泡 PDF、一份汇总 SIP Excel 和一份 manifest，并原子发布。
- 旧单 PDF 项目迁移后行为和正式结果保持可验证一致。
