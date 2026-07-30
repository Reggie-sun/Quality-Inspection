# Alembic Revision Collision Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 integrated `0010_technical_requirements.py` 安全收敛曾执行 feature-only
`0008` 的数据库，恢复 project status 且不丢失 technical-requirements 数据。

**Architecture:** 保持 `0008 → 0009 → 0010` 单线 graph；`0010` 用 Inspector
add-missing-only 补齐被 collided revision 跳过的 symbol schema，并幂等保留或添加
technical columns。canonical `0008` 继续拥有 symbol downgrade，`0010` 只拥有
technical downgrade。

**Tech Stack:** Python 3.11、SQLAlchemy、Alembic、PostgreSQL、pytest、Docker Compose

## Global Constraints

- 本文件是
  `docs/superpowers/plans/2026-07-30-technical-requirement-recognition-and-matching.md`
  的 bounded runtime blocker task contract，不成为第二个 current plan。
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-07-30-technical-requirement-recognition-and-matching.md`
- Selection evidence: live DB/runtime identity、confirmed revision collision、用户明确选择
  “修 technical worktree”并授权保留现有 staged integration、测试、DB upgrade 与提交。
- Validation action: `amend -> continue`
- Writer ownership and order: parent agent 是下列 allowed paths 的唯一 writer；既有
  merge-staged Harness files 不修改。并发执行已将该 merge 完成为 `942b373`，本修复
  以独立后续 commit 提交。
- Next verification: 新增 isolated-schema test，并确认原 `0010` 因 duplicate technical
  column 而 RED。
- Runtime config、API schema、Provider、frontend、Harness business semantics、review、
  balloon 和 export contract 均保持不变。

---

### Task 1: Reproduce The Feature-Only 0008 Upgrade

**Files:**
- Create: `backend/tests/integration/test_migration_reconciliation.py`

**Interfaces:**
- Consumes: integrated `backend/alembic/versions/0010_technical_requirements.py`
- Produces: isolated PostgreSQL regression covering feature-only `0008` shape

- [x] **Step 1: Write the failing migration test**

测试在随机 schema 中创建：

```text
projects=id/state/version
automatic_results=id/technical_requirements
review_working_copies=id/technical_requirements
```

然后锁定 `0008 → 0009 → 0010` graph，用真实 `MigrationContext` / `Operations`
顺序运行 `0009.upgrade()`、`0010.upgrade()`，再重复运行 `0010`；断言 symbol
schema、既有 project backfill 和 technical sentinel 保留。

- [x] **Step 2: Run RED**

```bash
docker compose -f compose.yaml run --rm -T \
  -v "$PWD/backend:/app" -w /app api \
  sh -lc 'pip install -q -e ".[dev]" && pytest tests/integration/test_migration_reconciliation.py -q'
```

Expected: FAIL at the original unconditional technical column add with duplicate-column error。

Observed: 原 `0010.upgrade()` 在 `automatic_results.technical_requirements` 触发
`DuplicateColumn`，证明 feature-only `0008` shape 已被真实复现。

### Task 2: Make Integrated 0010 The Convergence Owner

**Files:**
- Modify: `backend/alembic/versions/0010_technical_requirements.py`
- Test: `backend/tests/integration/test_migration_reconciliation.py`

**Interfaces:**
- Consumes: current database Inspector and canonical `0008` field definitions
- Produces: idempotent `upgrade()`; existing data-safe `downgrade()` contract remains

- [x] **Step 1: Add minimal Inspector-driven reconciliation**

`upgrade()` 精确执行：

```text
add missing project recognition fields
add missing project recognition check constraint
add missing automatic_results technical_requirements
add missing review_working_copies technical_requirements
leave every existing object unchanged
```

- [x] **Step 2: Run GREEN and canonical checks**

```bash
docker compose -f compose.yaml run --rm -T \
  -v "$PWD/backend:/app" -w /app api \
  sh -lc 'pip install -q -e ".[dev]" && pytest \
    tests/integration/test_migration_reconciliation.py \
    tests/integration/test_schema.py \
    tests/integration/test_project_status_api.py -q'
docker compose -f compose.yaml run --rm -T \
  -v "$PWD/backend:/app" -w /app api \
  alembic -c /app/alembic.ini heads
git diff --check
```

Expected: tests PASS；Alembic 只有 `0010 (head)`。

Observed: fresh chain 可升级到 `0010`；focused suite 为 `33 passed`，Alembic 只有
`0010 (head)`。

### Task 3: Upgrade The Current Dev Database

**Files:**
- Runtime backup only: `/tmp/qi-alembic-recovery/<timestamp>-pre-alembic-0008-recovery.dump`

**Interfaces:**
- Consumes: current `quality-inspection-postgres-1` and integrated migrations
- Produces: live DB at `0010` plus same-project runtime proof

- [x] **Step 1: Capture a nonempty local backup**

创建 custom-format `pg_dump`，只验证文件存在且非空，不读取或提交内容。

- [x] **Step 2: Apply the mounted worktree migration graph**

使用绑定当前 technical worktree backend 的 one-off container 执行：

```text
alembic current
alembic heads
alembic upgrade head
```

- [x] **Step 3: Verify live schema and same-project status**

只读验证必须证明：

```text
alembic_version=0010
projects has recognition_mode and recognition_router_version
ck_projects_recognition_mode exists
both technical_requirements columns remain
GET same project status = HTTP 200
phase=failed
error.code=vision_provider_call_failed
```

Observed: backup 为 `7,477,824` bytes；live DB 已从 `0008` 升级至 `0010`；
schema objects 全部存在；同一 project 返回 HTTP 200、`phase=failed` 和
`vision_provider_call_failed`；`/api/v1/health` 返回 HTTP 200。

### Task 4: Review, Close Memory, And Commit The Recovery

**Files:**
- Modify: `.agent/bug-memory.md`
- Create: `docs/superpowers/specs/2026-07-30-alembic-revision-collision-recovery-design.md`
- Create: `docs/superpowers/plans/2026-07-30-alembic-revision-collision-recovery.md`
- Modify: `backend/alembic/versions/0010_technical_requirements.py`
- Create: `backend/tests/integration/test_migration_reconciliation.py`

**Interfaces:**
- Consumes: GREEN tests, runtime proof, independent review
- Produces: closed bug entry and focused recovery commit

- [x] **Step 1: Run required checks**

```bash
python .agent/harness/scripts/check-contracts.py
git diff --check
```

- [x] **Step 2: Request independent read-only review**

reviewer 必须给出 `accept / accept with concerns / reject`，并检查 revision uniqueness、
canonical Owner、feature-only `0008` preservation、idempotency、downgrade ownership、
runtime evidence 和真实 failure-mode coverage。

Observed: 首轮 `accept with concerns` 指出 graph-level path 与 existing project sentinel
缺口；补强测试后复审为 `accept`，无 blocking 或 non-blocking finding。

- [x] **Step 3: Close bug memory and commit**

只有 migration tests、live DB/status 和 reviewer gate 通过后才将 bug memory 改为
`已解决`。并发执行已完成原 current merge；最终创建 focused recovery commit。除本
task files 外，不修改或 stage 现有 unrelated changes。
