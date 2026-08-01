# Server-Backed Drawing List Design

**Status:** Approved by user on 2026-08-01

## Goal

让 `http://127.0.0.1:5173/`、`http://192.168.10.69:5173/`、`https://qa.srj666.com/` 以及其他浏览器从同一 PostgreSQL catalog 读取相同图纸列表。浏览器 origin 不再拥有项目目录事实。

## Decision Record

- Selected lane: `Heavy`，因为新增稳定 API、Project schema migration 和跨模块 data-integrity boundary。
- Selected plan: `docs/superpowers/plans/2026-08-01-server-backed-drawing-list.md`。
- Selection evidence: 用户在看到本地 4 条、公网 0 条后明确选择方案 A：永久服务端项目列表。
- Validation action: `replan -> implement -> review`。
- Writer ownership: 隔离 worktree `feat/server-backed-drawing-list` 内仅父 agent 写入；main 上既有 workbench/SIP dirty files 不进入本任务。
- Next verification: 先写并运行缺少 `GET /api/v1/projects` 的失败 integration test。

## Current Root Cause

旧列表由 `frontend/src/app/localDrawingRegistry.ts` 写入 `localStorage` key `qi.drawing-list.v1`。Web Storage 按 origin 隔离，所以 loopback、LAN IP 和 public hostname 即使使用同一 Vite 源码，也不会共享项目目录。PostgreSQL 中已有 129 个历史、测试和真实项目；直接列出所有 `projects` 会把无意加入目录的历史运行暴露给 UI。

## Server Catalog Contract

### Owner

`Project` aggregate 是 catalog metadata 的唯一 Owner：

- `ProjectCatalogService` 只依赖数据库 session，拥有 list/open activity 操作，避免目录读取耦合上传存储和任务派发。

- `source_filename`: 上传文件的安全 basename；`NULL` 表示历史项目未加入 catalog。
- `created_at`: server authoritative project creation time。
- `last_opened_at`: anonymous shared QA workspace 的全局最近打开时间。

`localStorage` registry active path 选择 `remove`。浏览器中遗留 key 不主动删除，以保留 rollback 能力，但 production code 不再读取、写入或合并它。

### Visibility

`GET /api/v1/projects` 只返回 `source_filename IS NOT NULL` 的项目，按 `last_opened_at DESC, id DESC` 排序。这样新上传自动可见，而现有 129 个没有 catalog metadata 的历史/测试项目保持不可见。

当前 QA 没有账号认证或项目归属模型。用户选择的“多电脑一致”在本阶段定义为：同一 PostgreSQL 数据库内的匿名全局 catalog。不得把该 contract 描述为用户级权限隔离。

### Filename Safety

intake 必须把 multipart filename 规范化为 basename：先把 `\\` 转为 `/`，再取最后一个非空 path segment，trim 后限制为 255 字符；空值回退为 `未命名图纸.pdf`。resource ref 继续固定为 `asset://projects/{project_id}/source.pdf`，不得包含用户文件名。

## API Contract

### `GET /api/v1/projects`

Operation ID: `QI-API-PRJ-006`。

返回：

```json
{
  "items": [
    {
      "project_id": "UUID",
      "file_name": "drawing.pdf",
      "created_at": "ISO-8601",
      "last_opened_at": "ISO-8601"
    }
  ],
  "count": 1
}
```

列表 metadata 不重复 status projection；`DrawingListScreen` 继续逐行调用既有 `GET /{project_id}/status`，保留单行故障隔离。

### `POST /api/v1/projects/{project_id}/open`

Operation ID: `QI-API-PRJ-007`。服务器将 catalog 项目的 `last_opened_at` 设置为当前 server time 并返回更新后的 item。不存在或未加入 catalog 的项目返回 `404 project_not_found`。重复调用是允许的 last-write-wins activity update。

## Existing Four-Project Backfill

Alembic migration 只增加通用 schema，不硬编码机器数据。部署 migration 后，在一个显式事务中回填当前浏览器目录的 4 个已核对项目：

| Project ID | File Name | Last Opened (+08:00) | Evidence |
| --- | --- | --- | --- |
| `266e00ec-b97f-43a8-9f46-9af753374b01` | `BK20101401-09L1000#引拔梁(400W)#C1.PDF` | `2026-08-01T10:52:00+08:00` | local PDF SHA-256 matched latest stored source |
| `fb0572f9-4401-4d05-95ae-fde26b28d1d3` | `未命名图纸.pdf` | `2026-08-01T09:46:00+08:00` | existing deep-link project plus visible local-list row |
| `6943d223-70d1-444d-adab-93cef6a48fc6` | `JS20123103-10-033#手臂拖链支架上改#A2.pdf` | `2026-08-01T08:06:00+08:00` | local PDF SHA-256 matched latest stored source |
| `b3d4d9ba-4bcb-475b-9fa2-c559a201c7f3` | `JS20102801-02-018#手指头#A1.pdf` | `2026-07-31T16:41:00+08:00` | local PDF SHA-256 matched latest stored source |

事务必须确认恰好更新 4 行且 list API 恰好返回这 4 条；否则 rollback，不猜测或扩大 backfill。

## Frontend Contract

- `QualityInspectionApp` 在 list screen 激活时调用 `listProjects()`，不读取 `localStorage` registry。
- 上传成功不再写浏览器目录；server intake 已原子持久化 catalog metadata。
- 点击“继续处理”调用 `markProjectOpened()`，成功后更新本地 projection；activity update 失败不阻断项目打开，但返回列表时重新读取 server catalog。
- list request 失败显示安全的网络错误，不把失败伪装为空列表。
- `DrawingListScreen` 继续使用正式 status endpoint 显示每行状态。
- 旧深链和 `sessionStorage` current project compatibility 保持不变。

## Excluded

- 账号、部门或用户级 project ownership。
- 项目删除、归档、重命名、搜索、分页和批量操作。
- 将 129 个历史/测试项目自动加入 catalog。
- 修改 review、freeze、balloon、confirm 或 export 语义。

## Failure Boundaries

- list query 失败：返回统一 `project_list_failed` envelope；frontend 显示安全错误。
- open activity 更新失败：返回统一错误；frontend 仍允许打开已知项目。
- intake DB commit 失败：Project、StoredFile 和 catalog metadata 一起 rollback，storage cleanup 保持原 contract。
- filename 含路径或为空：只存安全 basename 或占位名，绝不进入 storage resource ref。
- migration/backfill 行数不等于预期：事务 rollback，runtime 不切换。

## Rollback

1. 在代码层恢复 2026-07-30 browser-local implementation。
2. 运行 `alembic downgrade 0012` 删除三个 catalog columns；浏览器遗留 `qi.drawing-list.v1` 未被清除，可恢复旧列表。
3. rollback 后第一项验证：既有 `GET /api/v1/projects/{project_id}/status` 对已知项目返回成功。
4. 随后验证 loopback 根页面恢复本机 4 条，public hostname 按旧 origin-local contract 独立显示。

## Acceptance Criteria

1. 新项目 intake 保存安全 filename 和 server timestamps。
2. list API 仅返回 catalog 项目，顺序稳定，count 正确。
3. open API 更新 server `last_opened_at` 并改变列表顺序。
4. frontend 不再读取或写入 `qi.drawing-list.v1`，旧 module/tests 被删除。
5. 现有 4 条完成受控 backfill，loopback、LAN 和 public 三个 origin 显示相同 4 条及名称。
6. API snapshot、generated TypeScript、API surface index、migration upgrade/downgrade、backend/frontend tests 和 browser smoke 全部通过。
