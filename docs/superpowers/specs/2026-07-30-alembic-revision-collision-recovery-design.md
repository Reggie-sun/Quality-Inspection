# Alembic Revision Collision Recovery Design

## Problem Statement

当前 live PostgreSQL 的 `alembic_version` 为 `0008`，但该 revision 来自
feature-only technical-requirements 开发线：`automatic_results` 与
`review_working_copies` 已有 `technical_requirements`，而 `projects` 没有 integrated
symbol-routing `0008` 声明的 `recognition_mode` 和
`recognition_router_version`。

integrated migration graph 已把 technical-requirements migration 顺延为 `0010`，
但它当前无条件添加两个已经存在的 technical columns。直接 `upgrade head` 会先跳过
symbol `0008`，执行 `0009`，再在 `0010` 因 duplicate columns 失败；即使只把
technical columns 改成幂等，也仍会留下缺失的 symbol fields。

## Goals

- 让 integrated `0010_technical_requirements.py` 成为 feature-only `0008` 与
  canonical `0008/0009/0010` 之间唯一 schema convergence point。
- 保留现有 project/job/error、technical requirements 和 symbol evidence 数据。
- 保持 fresh database 的 canonical schema 与 downgrade contract。
- 以真实 PostgreSQL DDL test 覆盖 feature-only `0008` upgrade path。
- 备份并升级当前 dev DB，再用同一 project 证明 status contract 恢复。

## Non-Goals

- 不修改、删除或手工回填业务数据。
- 不在 status endpoint、ORM model 或 service 中增加缺列 fallback。
- 不手改或 `stamp` `alembic_version`。
- 不创建第二个 revision `0010`、第二个 schema Owner 或平行 migration branch。
- 不重跑失败 project、Provider call、Harness live run 或 formal export。

## Chosen Design

保留 integrated linear graph：

```text
0008_symbol_routing_mode
→ 0009_symbol_routing_evidence
→ 0010_technical_requirements
```

扩展 `0010.upgrade()`，用当前 connection 的 SQLAlchemy Inspector 做 add-missing-only
reconciliation：

1. 缺少 `projects.recognition_mode` 时，按 canonical `0008` 的 type、default 和
   non-null contract 添加。
2. 缺少 `projects.recognition_router_version` 时，按 canonical `0008` contract
   添加。
3. 缺少 `ck_projects_recognition_mode` 时，创建 canonical allowlist。
4. 缺少任一 `technical_requirements` column 时，按原 `0010` JSONB contract 添加。
5. 已存在的 column、constraint、table 和数据不修改。

`0010.downgrade()` 继续只拥有 technical-requirements columns，并保留既有
nonempty-data refusal。symbol fields 仍由 canonical `0008.downgrade()` 唯一删除，
因此不建立第二个 schema Owner。

该设计借鉴 Alembic 官方 branch reconciliation 的 DAG/mergepoint原则、Apache
Superset repair migration 的 Inspector/add-only/no-duplicate 模式，以及 OpenStack
Neutron 的 Inspector-driven conditional migration。只融合结构与测试思路，不复制
外部代码，不增加依赖。

## Test Contract

`backend/tests/integration/test_migration_reconciliation.py` 在随机 PostgreSQL schema
中建立 feature-only `0008` shape：

- `projects` 只有 `id/state/version`；
- `automatic_results` 与 `review_working_copies` 已有
  `technical_requirements` sentinel columns；
- 用 `ScriptDirectory` 锁定 `0008 → 0009 → 0010`，再通过真实 Alembic
  `MigrationContext` / `Operations` 顺序执行 integrated `0009.upgrade()`、
  `0010.upgrade()`，并重复执行 `0010`；
- 断言 symbol fields、defaults、nullable contract 和 check constraint 被补齐；
- 断言 `0009` evidence tables、既有 project backfill、technical columns 和 sentinel
  rows 均正确；
- transaction rollback 后不污染 `public`。

production change 如果重新变成 unconditional add、删除无关列、漏建 constraint、改变
allowlist 或破坏 second-upgrade idempotency，该测试必须失败。

## Runtime Upgrade And Rollback

升级前在 `/tmp/qi-alembic-recovery/` 创建 custom-format `pg_dump` 并验证非空；不读取、
输出或提交 backup 内容。

PostgreSQL transactional DDL 负责 migration exception 的原子回滚。如果升级完成但
runtime proof 失败，停止后续写入，以备份为唯一恢复来源；不得删除 technical columns、
修改 version table 或给 status route 加 fallback。

rollback 后第一项验证：

```bash
curl --noproxy 127.0.0.1 -fsS \
  http://127.0.0.1:8000/api/v1/projects/688a3ebf-42e3-4ae4-a940-2bcbab4c376d/status
```

## Acceptance Criteria

- Alembic graph 只有 `0010` 一个 head。
- isolated-schema RED 先证明原 `0010` 对 feature-only `0008` 会 duplicate-column
  failure。
- GREEN 后 reconciliation test、canonical schema tests 和 project status tests
  通过。
- live DB 升级到 `0010`，symbol fields/constraint 存在，technical columns 与数据保留。
- 同一 project status 从 500 恢复为 sanitized `200 failed`。
- independent reviewer 接受 migration ownership、data preservation、idempotency、
  downgrade boundary 和 runtime evidence。
