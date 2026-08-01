# Review Lock Lifecycle Design

**Status:** Approved for implementation on 2026-08-01 by the user's request to fix stale test-session locks.

## Goal

保持“同一项目最多一个 active editor”的稳定契约，同时让已返回列表、已关闭页面或进入后台的测试工作台不再无限续租，避免无人实际编辑时阻断后续测试。

## Root Cause

`ProjectWorkbenchApp` 获取 300 秒 review lease 后，每 240 秒无条件续期，并在 window focus 时续期。组件 cleanup 只移除 timer/listener，没有正式 release。自动化测试留下的页面即使无人操作，仍可持续持有 project-scoped lease。

后端当前只有 `acquire_lock()`，没有 release primitive。若只按 `operator_id` 释放，同一 operator 的旧页面延迟 release 可能删除刚由新页面获取或续期的 lease。

## Contract

### Preserved

- `ReviewLock` 继续是 project-scoped 单编辑者 Owner。
- active lease 被其他 operator 持有时，获取锁仍返回 `review_lock_conflict`。
- TTL 保持 300 秒，续期间隔保持 240 秒。
- fatal/blocking lock failure 不降级为 warning 或成功。

### Added

- 新增 `POST /api/v1/projects/{project_id}/review/lock/release`，operation ID 为 `QI-API-REV-006`。
- request body 为最后一次成功 acquire/renew 返回的 `expires_at`。
- release 只在 `project_id`、`operator_id`、`expires_at` 全部匹配当前 row 时删除；这三个值共同构成当前 lease version。
- 缺锁、旧 version 或非 owner 请求均为幂等 no-op，返回 `released: false`，不得删除当前 lease。
- project 不存在返回 `project_not_found`；request/header 非法继续使用统一 validation/error contract。

## Backend Ownership

`backend/app/review/locks.py` 继续是 acquire、require、release 的唯一业务 Owner。`release_lock()` 先锁定 project row，再执行带 owner/version 条件的删除并 commit，避免引入第二套锁状态判断。

Router 只映射 HTTP request/response，不复制 owner 判断。数据库 schema 不变，不新增 migration 或 client token column。

## Frontend Lifecycle

`ProjectWorkbenchApp` 保存每次成功 acquire/renew 返回的最新 `expires_at`：

- 用户从工作台返回图纸列表时，先发送 best-effort release，再继续现有 `onReset`。release 失败不能阻止用户离开；TTL 仍是兜底。
- `pagehide` 时使用 `fetch(..., { method: "POST", keepalive: true })` 发送同一 release contract，不在 React effect cleanup 中发送，避免 StrictMode setup/cleanup 竞态。
- 页面进入 hidden 状态后，240 秒 interval 不再续期；恢复 visible 时立即 renew。
- `pageshow` 触发 renew，以支持 bfcache 恢复。
- acquire/renew 在单个页面内保持 single-flight，避免 focus、pageshow、visibilitychange 和 interval 形成乱序 lease version。
- `pagehide` 或显式返回后进入 leaving 状态，禁止发起新 renew；若已有 renew 在途，则在它 settle 后按实际返回的 `expires_at` 补发 release。若 bfcache 先恢复，`pageshow` 会取消 leaving 状态并保留该 lease。
- 每次发 release 前清空本地 lease ref，避免同一 version 被重复发送；旧 release 到达较晚时由后端 compare-and-release 保护新 version。

## Scope

### Included

- release service、schema、route 和 stable API projection。
- frontend release client、lifecycle wiring 和 focused tests。
- OpenAPI snapshot、generated TypeScript 和 API surface index 同步。
- API/integration/frontend/browser regression proof。

### Excluded

- 不放宽同项目并发编辑。
- 不新增管理员强制解锁、批量清锁或全局 lock dashboard。
- 不缩短 TTL，不删除其他 operator 的 live lock。
- 不修改 test operator identity 或账号权限模型。
- 不新增 page/session identity；同一 operator 同时打开同一项目的多个工作台不属于本次支持范围。
- 不把 frontend、browser 或 test harness 提升为锁语义 Owner。

## Failure Handling And Rollback

- release 失败时前端不阻断离开；服务端 TTL 最迟回收 stale lease。浏览器在 in-flight renew settle 前直接销毁 JS runtime 时，补发 release 仍可能无法执行，但 leaving/hidden 状态不会继续无限续租。
- renew 失败继续显示现有安全中文并暂停修改操作。
- 若 browser lifecycle 行为回归，可回滚 frontend release/visibility wiring，同时保留后端幂等 release API。
- 若 API contract gate 失败，先回滚新增 route、schemas 和 derived artifacts；不得留下未登记的 formal route。

## Verification

- unit/integration：owner+version 可释放；旧 version、非 owner、重复 release 不删除；释放后其他 operator 可 acquire。
- API：新 operation 有稳定 ID、显式 success/error schema、snapshot/index/generated TS 无 drift。
- frontend：返回列表发送正确 version；`pagehide` 使用 keepalive；hidden interval 不 renew；visible/pageshow renew；StrictMode cleanup 不 release；reset/pagehide 与 in-flight renew 竞态保持 single-flight 并补发最新 version release。
- headed browser：真实工作台返回列表后 DB active row 立即消失；重新打开可 acquire；关闭页面触发 release；后台页面不持续延长 expiry。
