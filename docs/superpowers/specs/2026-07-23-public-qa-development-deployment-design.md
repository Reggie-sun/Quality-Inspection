# Public QA Development Deployment Design

**Status:** Implemented; anonymous access approved by user on 2026-07-28

**Repository:** `Quality_Inspection`

## Context

主机的 `80/443` 已由 RAGFlow 占用，不能由本项目绑定或替换。`qa.srj666.com` 通过现有共享 Cloudflare Tunnel 进入当前 `main` checkout 的本地开发运行时。

用户最初选择 Tunnel + Access，随后于 2026-07-28 明确要求删除 `Quality Inspection QA` Access application，允许匿名用户直接进入。该决定是当前 security contract。

## Goal

以 `make dev-local-api` 和 `make dev-local-frontend` 为唯一公网 QA 运行入口。前端和后端均使用当前 `main` 源码，公网浏览器通过 `qa.srj666.com` 访问 Vite，并由 Vite same-origin proxy 转发 `/api`。

## Architecture

```text
Internet browser
  -> qa.srj666.com
  -> existing Cloudflare Tunnel
  -> 127.0.0.1:5173
  -> host Vite dev server
  -> /api proxy to 127.0.0.1:8000
  -> source-mounted FastAPI container
  -> PostgreSQL / Redis / storage
```

`make dev-local-frontend` 在 host 上从 `frontend/` 启动 Vite，并将 `/api` 代理到 `127.0.0.1:8000`。`make dev-local-api` 使用 `compose.dev-local.yaml` 将 `backend/app` bind mount 到容器，启用 Uvicorn reload，并只将 API 发布到 `127.0.0.1:8000`。

## Security And Ownership Contract

- `qa.srj666.com` 明确允许匿名直接访问，不得创建匹配该 hostname 的 Cloudflare Access application。
- Tunnel 只将 `qa.srj666.com` 转发到 `127.0.0.1:5173`，不得改写或删除其他 hostname rule。
- API 只能绑定 `127.0.0.1:8000`；PostgreSQL、Redis 和 storage 不得作为公网 origin。
- RAGFlow `80/443`、`ssh.srj666.com` 及其他 Cloudflare application 不在本 scope。
- credential、cookie、token 和 Provider secret 不得进入仓库、日志或验证证据。

## Acceptance Criteria

1. `compose.dev-local.yaml` 将 API 发布为 `127.0.0.1:8000:8000`，并 bind mount `backend/app`。
2. `http://127.0.0.1:8000/api/v1/health`、`http://127.0.0.1:5173/` 和 frontend `/api/v1/health` 均成功。
3. Tunnel ingress rule 精确匹配 `qa.srj666.com -> http://127.0.0.1:5173`。
4. Cloudflare applications 列表不存在匹配 `qa.srj666.com` 的 Access application。
5. 全新无 Cookie 浏览器直接加载 `https://qa.srj666.com/`，且同源 `/api/v1/health` 返回 200。

## Rollback

若要停止公网 QA，删除或禁用 `qa.srj666.com` DNS/Tunnel route，并停止两个本地开发进程。若要恢复身份验证，重新创建唯一匹配 `qa.srj666.com` 的 Access application，再分别验证匿名拒绝和已认证访问。
