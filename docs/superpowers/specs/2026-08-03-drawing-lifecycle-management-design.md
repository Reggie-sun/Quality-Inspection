# Drawing Lifecycle Management Design

**Status:** Proposed for user review on 2026-08-03

## Goal

在服务端图纸列表的每一行提供“重新识别”和“删除图纸”两个生命周期操作：

- “重新识别”使用当前服务端识别配置重新处理同一份原始 PDF；新结果成功前，当前可用版本保持不变。
- “删除图纸”将图纸从产品列表、深链和业务 API 中永久移除；内部数据仅为审计、引用完整性和运维留痕保留，不提供用户恢复能力。

## Decision Record

- Selected lane: `Heavy`，因为本功能新增稳定 API、Project schema migration、破坏性用户操作和跨 processing/review/export 的 data-integrity boundary。
- Selected plan: 待本 spec 批准后创建 `docs/superpowers/plans/2026-08-03-drawing-lifecycle-management.md`；不改变当前 PDF auto-balloon implementation plan。
- Selection evidence: 用户确认 Chrome MCP 原型中的列表行 `⋯` 入口、重新识别确认框和删除确认框方向。
- Validation action: `replan -> implement -> independent review -> Chrome MCP smoke`。
- Writer ownership: spec 阶段只允许父 agent 写本文档；业务代码在 spec 批准前保持不变。
- Next verification: spec 批准后，先写 lifecycle migration/service 的失败测试，再开始实现。

## Product Contract

### Placement

`DrawingListScreen` 每行保留现有主操作“继续处理”，并在其右侧增加 `⋯` 次级操作按钮。菜单项顺序固定为：

1. `重新识别`
2. `删除图纸`（destructive style）

只允许同时打开一个行菜单。按钮必须具备可访问名称，例如 `打开 <file_name> 的更多操作`；菜单支持点击外部或 `Escape` 关闭，操作执行期间禁用重复提交。

### Reprocess Confirmation

标题：`重新识别这张图纸？`

正文：`系统将使用当前识别能力重新处理原始 PDF。新结果成功前，当前版本仍可继续使用；成功后将切换到新版本。`

主按钮：`开始重新识别`。取消按钮：`取消`。

确认成功后，frontend 使用返回的 `project_id` 进入现有 processing/status 页面。原列表行在切换成功前仍指向旧 `project_id`。本任务不新增历史版本浏览或恢复 UI。

### Delete Confirmation

标题：`删除这张图纸？`

正文：`删除后，这张图纸将从图纸列表和工作区永久移除，无法恢复。系统仅按审计和数据完整性要求保留内部记录。`

主按钮：`删除图纸`（destructive style）。取消按钮：`取消`。

删除成功后关闭确认框并重新读取 server catalog。失败时保留当前行和确认框，显示安全错误；不得先在客户端乐观移除。

## Lifecycle Owner

新增 `backend/app/projects/lifecycle.py::ProjectLifecycleService`，它是 catalog lifecycle、版本 lineage、重新识别 promotion 和产品侧删除的唯一 Owner。

其他模块只能调用该 service，不得自行修改 lifecycle columns：

- `ProjectCatalogService` 只投影 `active` 项目。
- `ProjectIntakeService` 继续拥有全新 PDF intake；它创建的 catalog 项目初始为 `active`。
- `inventory_project` 在 working copy 建立后调用 lifecycle Owner 完成 promotion；在任务失败时调用 lifecycle Owner 标记新版本失败。
- review、balloon、export 和 project routes 通过 lifecycle guard 判断项目是否仍可从产品侧访问，不自行解释状态。

旧上传路径保持不变。上传失败页中基于浏览器内存 `File` 的“重试”仍只处理首次 intake dispatch failure，不替代本功能，也不作为重新识别入口。

## Data Model

Alembic migration `0014_project_lifecycle.py` 在 `projects` 增加：

- `lifecycle_status VARCHAR(32) NOT NULL`
  - `unlisted`: 既有、没有 `source_filename` 的历史项目。
  - `active`: 当前 catalog 可见版本。
  - `reprocessing`: 已创建并正在识别的隐藏 successor。
  - `reprocess_failed`: 重新识别失败的隐藏 successor。
  - `superseded`: 已被成功 successor 替代的旧版本。
  - `deleted`: 已从产品侧永久移除的版本。
- `predecessor_project_id UUID NULL REFERENCES projects(id)`: 重新识别版本指向直接 predecessor；全新上传为 `NULL`。
- `deleted_at TIMESTAMPTZ NULL`: 仅 `deleted` 非空。

Migration backfill：`source_filename IS NULL` 的既有项目设为 `unlisted`，其余设为 `active`。不得把当前隐藏历史项目加入 catalog。

数据库约束：

- `deleted` 与 `deleted_at IS NOT NULL` 必须一致；其他状态的 `deleted_at` 必须为 `NULL`。
- successor 不得指向自身。
- PostgreSQL partial unique index 保证每个 predecessor 同时至多存在一个 `reprocessing` successor。
- `predecessor_project_id` 使用默认 restrict/no-action 语义；本功能不物理删除 Project row。

`Project.state` 继续拥有 processing workflow phase，`lifecycle_status` 只拥有产品可见性与版本关系；不得把两套状态合并或互相推导成第二个 processing Owner。

## Reprocess Flow

`ProjectLifecycleService.start_reprocess(project_id)` 在一个事务内：

1. `SELECT ... FOR UPDATE` 锁定 predecessor。
2. 要求 predecessor 为 `active` 且仍有可解析的 source `StoredFile`；否则 fail closed。
3. 检查不存在 `reprocessing` successor；并发重复请求返回 conflict。
4. 创建新的 `Project`：新 UUID、`state=processing`、`lifecycle_status=reprocessing`、相同安全文件名和 source ref、`predecessor_project_id=旧 ID`，识别 mode/router identity 取当前 server settings。
5. 提交 DB 后，用新 project ID、新 logical task key `product-process:<new_project_id>` 和同一个 immutable source resource ref 派发既有 `inventory_project`。

不复制或重置 predecessor 的 working copy、review decisions、balloons、reviewed results 或 exports。新 Project 复用 immutable source `StoredFile` 引用，但 processing 结果、preview、working copy、balloon 和 export 都继续按新 project ID 隔离。

若 dispatch 失败，lifecycle Owner 将新 Project 标记为 `reprocess_failed`；旧 Project 保持 `active`。API 返回稳定错误，不伪装为启动成功；该失败 successor 仅作为内部诊断记录保留。

`inventory_project` 在以下两个成功分支都必须调用 `promote_reprocessed_project(new_project_id)`：

- 命中 existing successful result 后成功建立/确认 working copy。
- 新 pipeline 成功且 `ReviewService.create_from_raw` 建立 working copy。

Promotion 在一个事务内锁定 successor 与 predecessor，并验证 successor 为 `reprocessing`、predecessor 仍为 `active`、successor 已有 working copy，然后将 successor 改为 `active`、predecessor 改为 `superseded`。事务失败时不得隐藏 predecessor；重试同一 Celery task 可以幂等完成 promotion。

任何 terminal processing/review-bootstrap exception 都调用 `mark_reprocess_failed(new_project_id)`。该操作只允许 `reprocessing -> reprocess_failed`，不修改 predecessor。失败 successor 不出现在 catalog；用户可从仍 active 的旧版本重新发起一次新识别。

## Delete Flow

`ProjectLifecycleService.delete_project(project_id)` 在一个事务内锁定项目并执行产品侧 tombstone：

1. 仅允许删除 `active` 项目；其他 lifecycle 状态按产品不可见处理。
2. 若存在 `reprocessing` successor，返回 `409 project_reprocess_in_progress`，防止 promotion 与删除竞争。
3. 若存在未过期 review lock，返回 `409 project_locked`；过期 lock 按既有 stale-lock 语义处理后再继续。
4. 设置 `lifecycle_status=deleted`、`deleted_at=server time`，并提交。

删除不执行以下动作：

- 不物理删除 `Project`、`StoredFile`、source PDF、AutomaticResult、working copy、reviewed result、balloon、export、error 或 audit row。
- 不复用已删除 ID，不提供 undelete endpoint，不自动删除 lineage 中其他版本。
- 不把内部保留描述成用户可恢复的“回收站”。

该策略保证 foreign key、sealed receipt、export artifact 和 audit trail 保持可验证，同时满足产品侧永久不可访问。

## Product Access Guard

新增 projects lifecycle guard，并由所有带 `project_id` 的正式业务 route 使用统一语义：

- `active`: 允许现有读写能力。
- `reprocessing`: 只允许 status、source/preview 等现有 processing progress 所需的只读能力；禁止 review mutation、balloon、confirm 和 export。
- `reprocess_failed`: 只允许 status 读取，便于显示失败；其余能力拒绝。
- `unlisted`: 保持既有内部/历史 compatibility，不因本 migration 自动进入 catalog；既有明确 ID API contract 不在本任务中扩大或收紧。
- `superseded`、`deleted`: 所有产品入口返回 `404 project_not_found`，避免深链、旧 tab 或直接 API 继续读写。

Guard 的 route coverage 至少包括 `projects/router.py`、`review/router.py`、`balloons/router.py` 和 `exports/router.py`。不得只在 frontend 隐藏按钮，也不得只过滤 list API。

异步任务只接受 `reprocessing` successor 或正常 active intake 项目。若项目已变为 `deleted`/`superseded`，task 必须 fail closed，不生成新的正式结果。

## API Contract

### `POST /api/v1/projects/{project_id}/reprocess`

Operation ID: `QI-API-PRJ-008`。

Request body: 无。服务端使用当前 deployment 的 frozen recognition mode/router identity，不接受客户端指定 model 或 router version。

成功返回 `202`：

```json
{
  "project_id": "NEW_UUID",
  "predecessor_project_id": "OLD_UUID",
  "phase": "processing",
  "lifecycle_status": "reprocessing"
}
```

错误：

- `404 project_not_found`: 项目不存在或不是产品侧 active 项目。
- `409 project_reprocess_in_progress`: 已有正在运行的 successor。
- `409 project_source_pdf_unavailable`: 无法解析 immutable source PDF。
- `503 project_dispatch_failed`: DB 已记录 `reprocess_failed` successor，但任务未成功派发。

### `DELETE /api/v1/projects/{project_id}`

Operation ID: `QI-API-PRJ-009`。

成功返回 `204`，无 response body。

错误：

- `404 project_not_found`: 项目不存在或不是产品侧 active 项目。
- `409 project_reprocess_in_progress`: 当前存在正在运行的 successor。
- `409 project_locked`: 当前存在有效 review lock。
- `500 project_delete_failed`: tombstone transaction 未提交；项目保持原状态。

OpenAPI snapshot、generated TypeScript types 和 API surface index 必须随两个 operation 同步更新；frontend 只通过 typed `ProjectApi.reprocessProject()` 与 `ProjectApi.deleteProject()` 调用。

## Concurrency And Failure Boundaries

- 重复点击：frontend pending state 禁用按钮；backend row lock + partial unique index 是最终防线。
- 两个客户端同时重识别：一个创建 successor，另一个得到 `409`。
- 重识别与删除竞争：锁顺序固定为 predecessor 再 successor；任一侧观察到对方 active operation 都 fail closed。
- 新识别失败：旧 active 版本继续出现在列表并可打开；失败版本仅能通过返回的新 ID 查看 status。
- Promotion 重试：若 successor 已 active 且 predecessor 已 superseded，视为幂等成功；不得生成第三个版本。
- 删除事务失败：frontend 不移除列表行，backend 不产生部分 tombstone。
- 旧 tab 在删除或 promotion 后发 mutation：lifecycle guard 返回 `404 project_not_found`，不得继续修改内部保留数据。

## Excluded

- 历史版本列表、diff、restore、rollback-to-version 或回收站 UI。
- 重新上传替换原始 PDF；本功能只重用同一 immutable source。
- 批量删除、批量重识别、定时重识别和自动模型升级重跑。
- 物理对象清理、retention scheduler、审计数据清除或 storage garbage collection。
- 账号、角色、部门权限和 delete authorization；当前仍是既有 anonymous shared QA workspace contract。
- 修改 review、freeze、numbering、balloon 或 export 的业务语义。

## Migration And Rollback

Upgrade 后先验证：

1. 既有 `source_filename IS NOT NULL` 项目全部为 `active`，列表数量与 migration 前一致。
2. 既有 `source_filename IS NULL` 项目全部为 `unlisted`。
3. lifecycle constraints 与 partial unique index 生效。

Code rollback 可以停止暴露新 endpoints，但只要数据库中存在 `reprocessing`、`reprocess_failed`、`superseded`、`deleted` 或非空 `predecessor_project_id`，migration downgrade 必须 fail closed，不能丢弃 lifecycle truth。只有在显式审计证明所有 row 都可无损回到 migration 前语义时，才允许 downgrade `0014 -> 0013`。

不得通过把 `superseded`/`deleted` 强制改回 `active` 来完成 rollback；这会恢复用户已永久删除的数据或同时暴露多个版本。

## Validation

### Backend

- Migration upgrade/backfill/constraint/downgrade guard tests。
- Lifecycle service tests：start、并发 conflict、dispatch failure、promotion、promotion retry、processing failure、delete、active lock、reprocessing conflict。
- Integration API tests：两个新 operation 的 success/error envelopes，catalog visibility，旧版本在成功前可用、成功后不可访问，deleted deep-link/API rejection。
- Processing task tests：existing-result 与 fresh-pipeline 两条成功路径都触发 promotion，exception 路径只标记 successor failed。
- Contract gates：OpenAPI operation map、snapshot、API surface index、generated TypeScript drift。

### Frontend

- `DrawingListScreen` tests：菜单位置/关闭、accessible labels、reprocess/delete confirmation、pending disable、cancel、success navigation/list refresh 和 safe error。
- `QualityInspectionApp` tests：调用正确 project ID；reprocess 进入新 project status；delete 成功重新 list，失败保留项目。
- 现有 list/open/upload/retry tests 保持通过。

### Browser

使用 Chrome MCP 在 headed runtime 验证：

1. 每行 `⋯` 与现有“继续处理”并存，不挤压文件名和状态。
2. 两个确认框的文案、焦点、`Escape` 和 destructive styling。
3. 发起 reprocess 后进入新 processing 页面，返回列表时旧版本在成功前仍可见。
4. 新识别成功后列表只显示新 active 版本；旧 deep-link 返回产品侧 not-found。
5. 删除成功后列表行消失，刷新、旧 deep-link 和直接 API 都无法恢复访问。
6. Browser console 无新增 error；network 中只出现预期 API 调用且无重复提交。

## Acceptance Criteria

1. 图纸列表每行提供可访问的次级菜单，包含“重新识别”和“删除图纸”。
2. 重新识别固定复用同一 immutable source，并使用当前服务端识别 identity 创建隔离的新 Project。
3. 新 working copy 成功前旧版本保持 active；成功 promotion 原子切换；任意失败不破坏旧版本。
4. 产品侧删除使用 tombstone：列表、刷新、深链和正式业务 API 都不可再访问，内部引用完整性不被破坏。
5. 同一 lifecycle Owner 处理 start、promotion、failure、delete 和 access guard；其他模块不直接解释或改写 lifecycle 状态。
6. 并发 reprocess、reprocess/delete race、review lock 和 stale tab 均 fail closed。
7. migration、backend/frontend tests、contract gates、independent review 和 Chrome MCP headed smoke 全部通过后，才允许声明功能完成。
