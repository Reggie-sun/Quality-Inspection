# Public QA Development Deployment Implementation Plan

**Status:** Completed on 2026-07-28

## Goal

将当前 `main` 的本地开发 API 和 frontend 通过 `https://qa.srj666.com` 匿名公开。唯一 operator entrypoints 是 `make dev-local-api` 和 `make dev-local-frontend`。

## Execution Selection

- Selected lane: `Heavy`，因为本计划修改外部 authentication boundary 和 runtime ingress。
- Single owners: `compose.dev-local.yaml` 拥有 API bind mount 和 loopback port；`Makefile` 拥有启动入口；host Cloudflare config 拥有 Tunnel ingress；Cloudflare dashboard 拥有 Access application。
- Removed path: `quality-inspection-qa` 的 `14173/18000` Compose runtime 不再作为公网 origin。
- Unchanged contract: RAGFlow `80/443`、`ssh.srj666.com`、业务 API/schema、数据库数据和其他 Cloudflare application 不变。
- Rollback: 重新创建仅匹配 `qa.srj666.com` 的 Access application；第一项验证是全新无 Cookie 浏览器被拒绝。

## Runtime

1. `make dev-local-api` 使用 `compose.dev-local.yaml`，挂载 `backend/app`，启用 Uvicorn reload，并将 API 绑定到 `127.0.0.1:8000`。
2. `make dev-local-frontend` 从 host 启动 Vite `5173`，并将 `/api` 代理到 `127.0.0.1:8000`。
3. Cloudflare Tunnel 将 `qa.srj666.com` 精确转发到 `http://127.0.0.1:5173`。
4. `Quality Inspection QA` Access application 已删除；不得为该 hostname 保留或重建 Access policy，除非用户再次明确要求。

## Verification

```bash
docker compose -f compose.yaml -f compose.dev-local.yaml config --quiet
curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:8000/api/v1/health
curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:5173/api/v1/health
docker exec enterprise-rag-named-tunnel cloudflared tunnel --config /etc/cloudflared/config.yml ingress rule https://qa.srj666.com/
```

公网验证必须使用全新无 Cookie 浏览器。根页面应直接返回应用，URL 保持 `https://qa.srj666.com/`，同源 `/api/v1/health` 返回 200；不得出现 Cloudflare Access login。

## Current Evidence

- Cloudflare dashboard 已确认删除 `Quality Inspection QA`，其他 application 未修改。
- API listener 为 `127.0.0.1:8000`。
- Tunnel rule 命中 `qa.srj666.com -> http://127.0.0.1:5173`。
- 无 Cookie Chrome 返回 frontend HTTP 200、React app root 和 health HTTP 200。
