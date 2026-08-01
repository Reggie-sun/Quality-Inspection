# Review Lock Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留 project-scoped 单编辑者锁，同时主动回收已离开工作台的 lease，并停止后台页面无限续租。

**Architecture:** `backend/app/review/locks.py` 仍为唯一 Owner；新增以 `project_id + operator_id + expires_at` 为条件的原子 release。`ProjectWorkbenchApp` 以 single-flight renew 记录最新 lease version，在显式返回和 `pagehide` 进入 leaving 状态并发送 best-effort release，已有在途 renew settle 后补发实际 version release；隐藏页面跳过 interval renew，恢复时重新 acquire。

**Tech Stack:** FastAPI、SQLAlchemy 2、PostgreSQL、Pydantic、React 19、TypeScript 5.8、Vitest、Testing Library、OpenAPI snapshot/codegen。

## Global Constraints

- 不改变“一项目一个 active editor”、300 秒 TTL 和 240 秒 renewal interval。
- release 必须同时匹配 project、operator 和最后成功返回的 `expires_at`；旧页面不得释放新 lease。
- 非 owner、旧 version、缺锁均为幂等 no-op，不删除任何 live lease。
- 不新增 migration、管理员强制解锁、批量清锁或权限扩张。
- 不在 React effect cleanup 中发送 release；显式返回失败也不能阻断 `onReset`。
- hidden 页面不做 interval renew；visible/pageshow 恢复时立即 renew。
- renew 必须 single-flight；leaving 后禁止新 renew，并释放已有 in-flight renew 实际返回的 version。
- 不新增 page/session identity；同一 operator 同项目多工作台不属于本次支持范围。
- stable API route 必须同步 contract test、snapshot、API index 和 generated TypeScript。
- parent 是唯一 writer；现有 `code_mapper` 保持只读；实现完成后由独立 `reviewer` 只读审查。
- 只 stage 本计划列出的文件，不 stage `.agent/bug-memory.md` 或现有 `__pycache__` dirty files。

---

### Task 1: Backend Compare-And-Release Contract

**Files:**
- Modify: `backend/tests/integration/test_review_lock.py`
- Modify: `backend/app/review/locks.py`
- Modify: `backend/app/review/schemas.py`
- Modify: `backend/app/review/router.py`

**Interfaces:**

```python
def release_lock(
    session: Session,
    project_id: uuid.UUID,
    operator_id: str,
    *,
    expires_at: datetime,
) -> bool:
    """Delete only the exact current lease version and return whether it was deleted."""
```

```python
class ReleaseLockRequest(CommandBase):
    expires_at: datetime

class ReviewLockReleaseResponse(CommandBase):
    project_id: uuid.UUID
    released: bool
```

- [x] **Step 1:** 写 integration tests，覆盖 exact owner/version release、stale version no-op、other owner no-op、重复 release 和 release 后其他 operator acquire。
- [x] **Step 2:** 运行 `backend/tests/integration/test_review_lock.py`，确认因 `release_lock` 缺失而 RED。
- [x] **Step 3:** 最小实现 `release_lock()`，复用 project row serialization，并用条件 delete 保证 compare-and-release。
- [x] **Step 4:** 写 route/schema focused test，确认新 route 在实现前 RED；再实现 `QI-API-REV-006` route 和统一错误映射。
- [x] **Step 5:** 重跑 focused backend tests，确认 GREEN。

---

### Task 2: Frontend Lease Lifecycle

**Files:**
- Modify: `frontend/src/features/review/api.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`

**Interfaces:**

```ts
export type ReviewLockReleaseResponse = {
  project_id: string;
  released: boolean;
};

export function releaseReviewLock(
  projectId: string,
  operatorId: string,
  expiresAt: string,
): Promise<ReviewLockReleaseResponse>;
```

- [x] **Step 1:** 写 frontend tests，覆盖返回列表 release、`pagehide` keepalive、hidden interval skip、visible/pageshow renew，以及 cleanup 不 release。
- [x] **Step 2:** 运行 focused Vitest，确认缺少 lifecycle 行为而 RED。
- [x] **Step 3:** 实现 release client 与最新 `expires_at` ref；包装工作台 `onReset`，并注册 `pagehide` / `visibilitychange` / `pageshow`。
- [x] **Step 4:** 重跑 focused Vitest，确认 GREEN 且既有 conflict escape 测试不回归。

---

### Task 3: Stable API Projection

**Files:**
- Modify: `backend/tests/contract/test_openapi_contract.py`
- Modify: `backend/tests/contract/snapshots/api-v1.openapi.json`
- Modify: `docs/contracts/API_SURFACE_INDEX.md`
- Modify: `frontend/src/api/generated.ts`

- [x] **Step 1:** 在 `EXPECTED_OPERATIONS` 和 API index 登记 `QI-API-REV-006`，运行 contract test 确认 snapshot drift RED。
- [x] **Step 2:** 用仓库既有 OpenAPI snapshot 生成路径刷新 JSON，再运行 `npm --prefix frontend run api:generate`。
- [x] **Step 3:** 运行 `make check-api-contracts`，确认 breaking gate、snapshot、index 和 TypeScript projection 全部 GREEN。

---

### Task 4: Verification And Review

**Files:**
- Verify only: all files above

- [x] **Step 1:** 运行 focused backend integration/API tests、focused frontend tests、backend suite 与 frontend suite/build。
- [x] **Step 2:** 按 `auto-feature-smoke-test` 用 headed Chrome 验证返回列表、重新进入、关闭页面和 hidden renewal；清理本轮 test page/lease。
- [x] **Step 3:** 检查 `git diff --check`、`git status` 和 exact diff，确保未包含现有 dirty files。
- [x] **Step 4:** 用本地 `reviewer` profile 做只读独立审查；父 agent 核验 blocking claim 并做最小修正。
- [x] **Step 5:** 运行最终 verification，stage 指定文件并提交，报告 runtime truth 与剩余 TTL fallback 风险。
