# Public QA Development Deployment Design

**Status:** Approved by user for implementation

**Date:** 2026-07-23

**Repository:** `Quality_Inspection`

## Context

当前 `main` 位于 `0843472`，但正在运行的 `quality-inspection` API、Worker 和 frontend 均来自 `.worktrees/d1-t1-contract-harness` 的 `94c5131`，因此不能把当前端口状态当作 `main` 的 QA 运行证据。现有 frontend 源码热更新容器只挂载 `frontend/src`、`index.html` 和 `vite.config.ts`，后端没有源码挂载。

主机的 `80/443` 已由 RAGFlow 占用，不能由本项目绑定或替换。已存在的 Cloudflare tunnel 是共享资源；它当前只包含其他 hostname 的入口配置。`qa.srj666.com` 在本机经过 Mihomo TUN fake-IP 解析为 `198.18.0.104`，该本机解析和 TLS 结果不能用作公网 DNS 或公网可达性的结论。

用户已选择：通过 Cloudflare Tunnel 将 `qa.srj666.com` 作为受访问门禁保护的开发测试入口公开。

## Goal

提供一个与现有 P0 runtime 和 RAGFlow 隔离的、以当前 `main` 为唯一源码事实的 QA 开发运行时。前端和后端源码变更可在该运行时内被观察，公网访问只经 `qa.srj666.com`、Cloudflare Tunnel 和 Cloudflare Access（或已确认的等效门禁）进入。

## Non-goals

- 不替换、重建或修改 RAGFlow 的 `80/443` default ingress。
- 不公开 Docker 的 `3000`、`8000`，也不公开 PostgreSQL 或 Redis。
- 不引入应用级账号、RBAC、SSO 或生产发布平台。
- 不改变 PDF、review、balloon、export 或 Provider 的业务契约。
- 不在仓库、日志、plan、receipt 或聊天中读取、写入或输出 Cloudflare、Provider、数据库等 credential。
- 不把本机 Mihomo fake-IP 解析视为公网 DNS 验证。

## Architecture

```text
Internet browser
  -> Cloudflare Access policy
  -> qa.srj666.com
  -> existing Cloudflare Tunnel (host-owned ingress rule)
  -> 127.0.0.1:<qa-frontend-port>
  -> source-mounted Vite frontend
  -> /api Vite proxy on the isolated Compose network
  -> source-mounted FastAPI API + isolated Worker
  -> isolated PostgreSQL / Redis / storage volumes
```

运行时由 `docker compose -p quality-inspection-qa -f compose.yaml -f compose.qa-dev.yaml` 唯一拥有。overlay 必须覆盖 base Compose 的 host ports 和 named volumes，避免与当前 `quality-inspection` runtime 共用端口、容器名、PostgreSQL 数据或 FileStorage。

frontend 运行 Vite dev server，并保持项目既有 `/api -> http://api:8000` proxy；Cloudflare 只把同一 hostname 转到 frontend loopback port，因此浏览器 API 请求保持 same-origin。API 使用 `uvicorn --reload` 和 `backend/app` bind mount；Worker 使用同一 bind mount，但其代码刷新由明确的 worker restart 操作完成，不能声称自动 reload。

## Security And Ownership Contract

- `compose.qa-dev.yaml` 只能将 QA frontend/API 发布到 `127.0.0.1`；数据库、Redis、Worker 不得有 host port。
- `qa.srj666.com` 的 DNS record、Tunnel ingress rule、Tunnel lifecycle 和 Cloudflare Access policy 属于主机/Cloudflare owner，不成为 repository secret 或 application owner。
- Access policy 必须在 hostname 生效前验证为 unauthenticated request 被拒绝、authenticated request 可访问；没有该验证时不得把应用称为公网 QA ready。
- 对共享 tunnel 的修改只能添加精确的 `qa.srj666.com -> 127.0.0.1:<qa-frontend-port>` ingress rule，不重排、删除或改写既有 hostname。任何重启失败时，先恢复该单行变更并验证既有 ingress origin 仍可用。
- 当前 `main` checkout 的 `AGENTS.md` 修改和 `.local/` 内容属于其他工作，不得 stage、commit、覆盖或作为 QA runtime 输入。

## Acceptance Criteria

1. `docker compose ... config` 显示 QA 的 API/frontend 仅绑定 loopback，QA volumes 有独立名称。
2. QA API `GET /api/v1/health` 和 QA frontend `/` 在 loopback 返回成功；frontend 经 `/api/v1/health` 代理也成功。
3. 改动 `frontend/src` 后，QA frontend 提供新资源；改动 `backend/app` 后，QA API reload 并反映新代码。Worker restart 操作可验证其重新载入 bind-mounted代码。
4. Cloudflare Tunnel 配置中只有精确新增的 QA hostname route，且该 route 的 origin 为 QA frontend loopback port。
5. Cloudflare Access 的匿名拒绝与已认证可达都以外部路径实际验证；通过后，`https://qa.srj666.com/api/v1/health` 返回 Quality Inspection health payload。
6. 任何失败均不会把 `3000`、`8000`、数据库、Redis 或 RAGFlow default ingress 暴露为替代方案。

## Rollback

停止并移除仅由 `quality-inspection-qa` Compose project 创建的容器和 volumes；恢复 host-owned tunnel config 中新增的单一 QA ingress rule；删除/停用 QA hostname 的 Access/DNS route。不得删除现有 `quality-inspection`、RAGFlow 或其他项目的 containers、volumes、tunnels、DNS records 或 host routes。rollback 后先验证现有 tunnel origin 和 `main` working copy 未被改变。
