# LAN Frontend Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 canonical host-run Vite frontend 永久绑定到 `0.0.0.0:5173`，允许局域网设备直接访问，同时保持 API 与 Cloudflare Tunnel 的既有边界。

**Architecture:** `Makefile` 继续作为唯一 host-run frontend runtime binding Owner，只把现有 `--host 127.0.0.1` 替换为 `--host 0.0.0.0`，并从通用 npm `dev` script 移除重复的 host producer。`frontend/Dockerfile` 独立拥有 container binding，继续显式绑定 `0.0.0.0:3000`。API proxy target 仍是 `127.0.0.1:8000`，Cloudflare Tunnel origin 仍是 `127.0.0.1:5173`，两者都能命中新的 wildcard listener。

**Tech Stack:** GNU Make, Vite 6, Docker Compose, curl, Linux socket inspection

## Global Constraints

- Selected lane: `Heavy`，因为变更稳定 runtime binding 和 network exposure。
- Selected plan: 本文件；不切换或扩展当前 PDF Auto-Balloon P0 implementation plan。
- Selection evidence: 2026-08-01 用户明确批准永久将当前 `5173` frontend 绑定到 `0.0.0.0`。
- Validation action: `amend -> implement -> review`。
- Single Owner: host-run binding 由 `Makefile` 的 `dev-local-frontend` target 拥有；container binding 由 `frontend/Dockerfile` 拥有。
- Allowed paths: `Makefile`、`frontend/package.json`、`frontend/Dockerfile`、本 plan、public-QA design spec、public-QA SOP。
- Old path action: `replace`；退役 `--host 127.0.0.1` startup，不建立第二 frontend target。
- Unchanged contract: API 保持 `127.0.0.1:8000`；Tunnel 保持 `qa.srj666.com -> http://127.0.0.1:5173`；RAGFlow `80/443` 和业务 API/schema 不变。
- Writer ownership: 当前父 agent 是唯一 writer；不修改其他 dirty artifacts。
- Rollback: 将 frontend host 恢复为 `127.0.0.1`；第一项验证是 loopback root 与同源 `/api/v1/health` 返回成功，随后确认 LAN IP `:5173` 不再监听。

---

### Task 1: Replace The Canonical Frontend Bind Contract

**Files:**
- Modify: `Makefile`
- Modify: `frontend/package.json`
- Modify: `frontend/Dockerfile`
- Modify: `docs/operations/qa-dev-public-deployment.md`
- Modify: `docs/superpowers/specs/2026-07-23-public-qa-development-deployment-design.md`
- Create: `docs/superpowers/plans/2026-08-01-lan-frontend-binding.md`

**Interfaces:**
- Consumes: `LOCAL_FRONTEND_PORT`, `LOCAL_API_PORT`, Vite `--host` and `--port` flags.
- Produces: one canonical `make dev-local-frontend` command that listens on every host interface while proxying `/api` to the loopback API.

- [x] **Step 1: Record the design amendment**

Update the public-QA design so the active frontend binding is `0.0.0.0:5173`, the LAN consumer is explicit, and API/Tunnel boundaries remain unchanged.

- [x] **Step 2: Verify the pre-change command contract**

Run:

```bash
make -n dev-local-frontend
```

Expected before implementation: output contains `--host 127.0.0.1 --port 5173 --strictPort`.

- [x] **Step 3: Replace the Makefile host binding**

Change only the frontend Vite host flag:

```make
QI_API_PROXY_TARGET=http://127.0.0.1:$(LOCAL_API_PORT) npm --prefix frontend run dev -- --host 0.0.0.0 --port $(LOCAL_FRONTEND_PORT) --strictPort
```

Remove the pre-existing `--host 0.0.0.0` from `frontend/package.json` so the canonical Make target is the single binding producer and the live process receives exactly one `--host` flag.

Keep the separate Docker consumer reachable by adding `--host 0.0.0.0` to `frontend/Dockerfile`'s `CMD`; the Dockerfile remains the container binding Owner.

- [x] **Step 4: Update the operator SOP**

Document the active listener as `0.0.0.0:5173`, retain `127.0.0.1:5173` as the Tunnel origin, add `<host-lan-ip>:5173` as the LAN URL, and retain the API loopback-only restriction.

- [x] **Step 5: Verify the static command contract**

Run:

```bash
make -n dev-local-frontend | rg -- '--host 0\.0\.0\.0 --port 5173 --strictPort'
make -n dev-local-frontend | rg 'QI_API_PROXY_TARGET=http://127\.0\.0\.1:8000'
! make -n dev-local-frontend | rg -- '--host 127\.0\.0\.1'
```

Expected: both positive checks match and the retired-host check returns success because no old binding remains.

- [x] **Step 6: Activate the canonical runtime**

Run `make dev-local-frontend` from the repository root. The target owns replacement of the existing `5173` process through its existing `fuser -k` preflight.

- [x] **Step 7: Verify listener and active paths**

Run:

```bash
ss -ltn '( sport = :5173 )'
curl --noproxy '*' -fsS -o /dev/null -w 'loopback HTTP %{http_code}\n' http://127.0.0.1:5173/
curl --noproxy '*' -fsS -o /dev/null -w 'LAN HTTP %{http_code}\n' http://192.168.10.69:5173/
curl --noproxy '*' -fsS http://192.168.10.69:5173/api/v1/health
```

Expected: listener is `0.0.0.0:5173`; both root requests return `200`; health returns `{"status":"ok","app_name":"quality-inspection"}`.

- [x] **Step 8: Run focused UI smoke**

Open `http://192.168.10.69:5173/` in the available browser runtime and confirm the application root renders. If browser automation is unavailable, report that blocker separately while retaining the HTTP/runtime evidence.

- [x] **Step 9: Review and commit**

Run:

```bash
git diff --check
git diff -- Makefile frontend/package.json frontend/Dockerfile docs/operations/qa-dev-public-deployment.md docs/superpowers/specs/2026-07-23-public-qa-development-deployment-design.md docs/superpowers/plans/2026-08-01-lan-frontend-binding.md
git add Makefile frontend/package.json frontend/Dockerfile docs/operations/qa-dev-public-deployment.md docs/superpowers/specs/2026-07-23-public-qa-development-deployment-design.md docs/superpowers/plans/2026-08-01-lan-frontend-binding.md
git diff --cached --check
git commit -m "fix: expose local frontend to LAN"
```

Expected: only the six allowed files are staged and committed.
