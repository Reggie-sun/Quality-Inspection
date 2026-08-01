# Compose Worktree Runtime Isolation Design

## Problem

仓库根 `compose.yaml` 固定声明 `name: quality-inspection`，因此主工作区与所有
Git worktree 在未显式传入 `-p` 时都会写入同一个 Compose project。任一 worktree
执行 `docker compose up --build api` 都会替换公网 QA 正在使用的 `api`，并可同时
替换 `worker`、network 与其他 project-scoped resource。

2026-08-01 的现场证据显示，
`.worktrees/structured-geometric-tolerance-recognition` 创建的容器带有
`com.docker.compose.project=quality-inspection`，随后公网
`GET /api/v1/projects` 从 `200` 回退为旧镜像的 `405`。

## Goal

让每个 Git worktree 默认拥有独立的 Compose project、container、network、PostgreSQL
volume 和 storage volume，同时保持主工作区的开发数据与公网 QA 入口不变。

## Scope

- `compose.yaml`：拥有默认 project 与基础 volume 命名合同。
- `compose.qa-dev.yaml`：拥有 QA-dev 专用 volume 命名合同。
- `Makefile`：拥有主工作区和 QA-dev 的命令行 project-name 选择。
- `backend/tests/integration/test_runtime_topology.py`：拥有隔离回归覆盖。
- `docs/operations/qa-dev-public-deployment.md`：记录 operator entrypoint 与隔离规则。

不修改业务 API/schema、数据库内容、Cloudflare hostname、Tunnel origin、Vite `5173`
监听合同或用户现有未提交功能改动。

## Ownership

Compose project identity 的唯一 Owner 是 checkout/worktree 根目录名。`Makefile` 只把该
identity 显式传给标准入口，不再提交一个全仓固定 project name。

Project-scoped volume identity 由 `${COMPOSE_PROJECT_NAME}` 派生：

```text
<project>_postgres_dev
<project>_storage_dev
<project>_postgres_qa_dev
<project>_storage_qa_dev
<project>_frontend_node_modules_qa_dev
```

## Old Path

删除固定 `name: quality-inspection` Owner，并替换固定基础/QA-dev volume 名。历史文档中
的命令示例保持历史事实，不作为 active runtime Owner。

删除 `dev-local-api` 与 `dev-local-frontend` 的 `fuser -k` repair 路径。隔离后，端口
冲突必须 fail closed，不能由另一个 worktree 清理当前 listener 后接管公网 QA。

## Invariants

- 主工作区默认 project 为其规范化目录名 `quality_inspection`。
- 主工作区继续复用现有 `quality_inspection_postgres_dev` 与
  `quality_inspection_storage_dev`，不迁移、不复制、不删除数据。
- feature worktree 的 project、network 和 volume 名必须与主工作区不同。
- `make dev-local-api` 仍绑定 `127.0.0.1:8000` 并挂载主工作区源码。
- `make dev-local-frontend` 保持当前 checkout 已批准的 listener contract；本 isolation 计划不改变其 host binding。
- `qa.srj666.com` 仍转发到 `http://127.0.0.1:5173`。

## Failure Boundaries

- 两个隔离 runtime 仍不能同时发布相同 host port；worktree runtime 必须通过 override
  或 QA-dev 端口运行。第二个 runtime 必须启动失败且保持现有 listener 不变。
- 用户显式传入相同 `-p`/`COMPOSE_PROJECT_NAME` 仍可主动合并 namespace；标准入口与
  默认直接 `docker compose` 不再这样做。
- 迁移 runtime 时只停止旧 `quality-inspection` containers，不删除 volume。

## Verification

1. Compose config regression tests：固定 top-level name 已删除，两个显式 project
   产生不同 network/volume identity。
2. Main config smoke：主工作区解析为 `quality_inspection`，并继续指向现有数据 volume。
3. Worktree config smoke：feature worktree 解析为独立 project 与 volume。
4. Runtime migration：记录迁移前 project identity set；新主 namespace 的 health、
   project list 和该集合全部 workbench 均为 `200`，identity set 不变。
5. Public Chrome smoke：`qa.srj666.com` 显示与迁移前相同的图纸集合，列表/状态请求均为
   `200`，console 无错误。

## Rollback

仅回退本 spec 列出的文件；停止新的 `quality_inspection` containers，不带 `--volumes`，
再用旧配置启动 `quality-inspection`。Rollback 后第一项验证是
`GET http://127.0.0.1:8000/api/v1/projects` 返回 `200` 且 project identity set 与迁移前一致。
