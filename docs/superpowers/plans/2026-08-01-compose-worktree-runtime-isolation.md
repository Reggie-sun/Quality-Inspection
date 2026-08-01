# Compose Worktree Runtime Isolation Implementation Plan

## Goal

修复固定 Compose project name 导致的跨 worktree 容器覆盖，并把主公网 QA 迁移到默认
worktree-scoped namespace。

## Execution Selection

- Selected lane: `Heavy`，因为本变更修改 runtime entry/config。
- Selected spec:
  `docs/superpowers/specs/2026-08-01-compose-worktree-runtime-isolation-design.md`。
- Single Owner: checkout/worktree 根目录名拥有 Compose project identity；
  `${COMPOSE_PROJECT_NAME}` 拥有 project-scoped volume identity。
- Old path: `remove` 固定 `name: quality-inspection`；`replace` 固定 volume 名。
- Port repair path: `remove` 两个 `fuser -k`，端口冲突改由 bind/`--strictPort`
  fail closed。
- Unchanged contract: 业务 API/schema、主数据、`127.0.0.1:8000`、`0.0.0.0:5173`、
  `qa.srj666.com -> 127.0.0.1:5173`。
- Writer: 当前父 agent；只修改本计划 Allowed Paths，同一 file group 不派第二 writer。

## Allowed Paths

- `compose.yaml`
- `compose.qa-dev.yaml`
- `Makefile`
- `backend/tests/integration/test_runtime_topology.py`
- `docs/operations/qa-dev-public-deployment.md`
- 本 spec 与 plan

## Tasks

1. 删除 base Compose 的固定 top-level name。
2. 用 `${COMPOSE_PROJECT_NAME}` 派生 base 与 QA-dev volume 名。
3. 在 `Makefile` 从 Git worktree root basename 计算规范化 project name；标准入口显式传
   `-p`，QA-dev 使用 `<worktree>-qa`。
4. 删除跨 worktree 强杀 `8000/5173` listener 的 `fuser -k`。
5. 更新 runtime topology tests，覆盖无固定 Owner、两个 project 的 container/network/
   volume 隔离与 Makefile 入口。
6. 更新公网 QA SOP，说明 worktree 隔离、volume 命名、端口 fail-closed 和旧 QA
   project 的非破坏性 cleanup target。
7. 运行 focused tests 与 Compose config checks。
8. 停止旧 `quality-inspection` project（不删除 volume），启动主工作区
   `quality_inspection` dev-local API，并验证数据不变。
9. 验证 feature worktree config identity 不会命中主 namespace；同端口启动必须失败且
   不改变主 runtime identity。
10. 完成独立 review，再提交精确文件。

## Required Checks

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_runtime_topology.py -q
docker compose config --quiet
docker compose -f compose.yaml -f compose.dev-local.yaml config --quiet
make --dry-run dev-local-api
make --dry-run qa-dev-config
```

Runtime checks:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:8000/api/v1/health
curl --noproxy '*' -fsS http://127.0.0.1:8000/api/v1/projects
curl --noproxy '*' -fsS http://127.0.0.1:5173/api/v1/health
```

## Rollout

先通过静态验证，再停止旧 project 的 containers；不使用 `down --volumes`。随后从主工作区
启动新 namespace。确认新容器 label、volume source、迁移前 project identity set 与公网
smoke 后完成切换。

## Rollback

停止新 `quality_inspection` project，不删除 volume；回退 Allowed Paths 后启动旧
`quality-inspection` project。第一项验证是本机项目列表返回 `200` 且 project identity
set 与迁移前一致。

## Completion Contract

- 主工作区与至少一个 feature worktree 的 Compose project/network/volume identity 不同。
- 主公网 QA 不再能被 feature worktree 的默认 `docker compose up` 替换。
- 主数据 project identity set 与迁移前一致。
- focused tests、runtime API smoke、public browser smoke 和 independent review 均有当前证据。
