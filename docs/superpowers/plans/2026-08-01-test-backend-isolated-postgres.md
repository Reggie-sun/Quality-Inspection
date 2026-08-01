# Test Backend Isolated PostgreSQL Plan

## Goal

修复 `make test-backend` 在宿主机执行时继承 Compose-only 数据库主机名 `postgres`、导致所有数据库测试级联失败的问题。入口必须自行创建隔离 PostgreSQL、迁移到当前 Alembic head、运行原有 backend suite，并在任何退出路径清理隔离资源。

## Boundary

- Selected lane: `Heavy`
- Single owner: `Makefile:test-backend` 拥有测试运行 lifecycle；`compose.test.yaml` 只描述隔离 PostgreSQL dependency。
- Old path to replace: 宿主机 pytest 直接读取根目录 `.env` 并尝试连接默认开发 Compose 数据库。
- Unchanged contract: `backend/tests` 测试集合、production `Settings`、production `compose.yaml`、Alembic graph、开发/QA 数据库和正式 Harness evidence contract 均不变。
- Allowed paths: `Makefile`、`compose.test.yaml`、`backend/tests/integration/test_runtime_topology.py`、本 plan、`.agent/bug-memory.md`。
- Forbidden scope: 不修改 production database config，不复用或迁移开发数据库，不占用固定 host PostgreSQL port，不修改现有 dev/QA Compose lifecycle。

## Design

1. `compose.test.yaml` 仅启动 PostgreSQL 17，数据目录位于 container-local `tmpfs`，host port 由 Docker 动态分配并只绑定 `127.0.0.1`。
2. `make test-backend` 每次使用唯一 Compose project name，等待 healthcheck 后读取动态端口。
3. 只在该命令的 environment 中设置 test database URL，先运行 `alembic upgrade head`，再运行原有 `python -m pytest backend/tests -q`。
4. shell `trap` 在成功、测试失败或中断时对精确 test project/file 执行 `down --volumes --remove-orphans`。

## Verification

1. RED/GREEN: `backend/tests/integration/test_runtime_topology.py` 验证 rendered test topology 与 Make lifecycle。
2. Focused runtime: 新入口启动隔离库、迁移并执行数据库 integration test。
3. Full: `make test-backend`。
4. Cleanup: 验证没有残留 `quality-inspection-test-*` container/network/volume。
5. Independent review: reviewer 检查开发数据库隔离、失败清理、端口冲突和测试结论。

## Rollback

只回退本 plan 的 `Makefile` delta、`compose.test.yaml` 和回归测试；第一项验证恢复为原始失败复现，即宿主机无法解析 `postgres`。任何实现失败都先清理精确 `quality-inspection-test-*` 资源，不接触默认 `quality-inspection` 或 `quality-inspection-qa` project。

## Outcome

- Test runtime entry: `completed`。隔离 PostgreSQL lifecycle、动态 loopback port、Alembic upgrade、pytest 和 failure-safe cleanup 均已运行。
- Focused verification: `backend/tests/integration/test_runtime_topology.py` 为 `4 passed`。
- Full verification: `make test-backend` 为 `1599 passed / 4 failed / 4 warnings`；已消除数据库 DNS/connection 级联失败，但 backend full-suite 不是 GREEN。
- Residual boundary: 4 个失败均位于 `test_symbol_recognition_pipeline.py`，是 source disposition expectation 与当前 producer 语义不一致；本 plan 不修改该业务 Owner 或测试。
- Cleanup proof: pytest 失败后无 `quality-inspection-test-*` container、network 或 volume 残留。
- Independent review: `accept with concerns`，blocking issue 为 0。
