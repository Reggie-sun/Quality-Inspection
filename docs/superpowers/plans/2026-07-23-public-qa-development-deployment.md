# Public QA Development Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 `main` 作为唯一源码事实，以隔离、source-mounted、loopback-only 的 Docker Compose runtime 运行，并通过受 Cloudflare Access 保护的 `https://qa.srj666.com` 提供开发测试入口。

**Architecture:** `compose.qa-dev.yaml` 覆盖 base Compose 的 ports、volumes、API reload command 和 bind mounts；Vite 继续作为唯一 same-origin `/api` proxy。Cloudflare Tunnel 只新增 `qa.srj666.com` 到 QA frontend loopback port 的 hostname rule，不触碰 RAGFlow 的 `80/443`。公网由 Cloudflare Access 作为唯一浏览器入口门禁。

**Tech Stack:** Docker Compose v5、FastAPI/Uvicorn、Celery、React/Vite、PostgreSQL、Redis、Cloudflare Tunnel、Cloudflare Access、Micromamba。

---

## Source Of Truth And Execution Selection

- Selected lane: `Heavy`，因为该工作建立 runtime entry/config、外部 hostname route 和访问控制边界。
- Selected plan: 本文件；它是 `2026-07-21-pdf-auto-balloon-and-excel.md` 之外、经用户于 2026-07-23 明确批准的独立 deployment lane，不改变 P0 的 Day/Task 顺序或业务 scope。
- Selection evidence: 用户指定 `qa.srj666.com`、要求源码挂载开发测试，并选择 “Tunnel + Access”。只读检查证明当前 runtime 不属于 `main`、80/443 已占用且本机 DNS 经 Mihomo fake-IP 污染。
- Problem boundary: 只创建并验证 isolated QA development runtime、受控 public ingress 与 access gate；不变更业务代码、stable API、数据库 schema 或 P0 formal export。
- Single owners: `compose.qa-dev.yaml` 拥有 QA container topology；`Makefile` 拥有 operator entrypoints；host-owned Cloudflare config 拥有 hostname ingress；Cloudflare dashboard/API owner 拥有 DNS 与 Access policy。
- Old path to retire: 当前来自 `.worktrees/d1-t1-contract-harness`、发布 `0.0.0.0:3000/8000` 的 runtime 不再作为 QA proof；它不在本 task 内被删除或改动。
- Unchanged contract: app secrets remain server-side only；frontend remains non-owner of business semantics；P0 reviews/exports remain unchanged；RAGFlow `80/443` remains untouched。
- Validation action: `continue`；先完成 deterministic Compose config gate，再运行 isolated local runtime，再由 external Cloudflare path 验证 Access、HTTPS、API proxy 和 source mount。
- Writer ownership and order: 一个 writer 顺序执行 Task 1 → 4；host config 只在 Task 4 由父 agent 修改，且一次只改一条 ingress rule。reviewer 必须只读检查 final diff 与 runtime evidence。
- Rollback first verification: 恢复 host-owned QA ingress change 后，运行 `docker inspect enterprise-rag-named-tunnel --format '{{.State.Running}}'` 并运行 `make qa-dev-status`；预期 tunnel 仍为 `true`，而已停止的 QA stack 不影响原有 runtime。

## File Map

| File | Responsibility |
| --- | --- |
| `compose.qa-dev.yaml` | QA overlay：独立 volume 名、loopback-only ports、API/Worker/frontend source mounts 和 dev commands。 |
| `Makefile` | `qa-dev-up`、`qa-dev-down`、`qa-dev-status`、`qa-dev-restart-worker`、`qa-dev-config` operator commands。 |
| `docs/operations/qa-dev-public-deployment.md` | 不含 credential 的 host-side route、Access、verification 和 rollback SOP。 |
| `/home/reggie/.cloudflared/enterprise-rag-dev.yml` | Host-owned shared tunnel config；仅在批准后的 Task 4 新增 `qa.srj666.com` route，不进入 Git。 |

## Task 1: Define and statically verify the isolated source-mounted QA runtime

**Files:**
- Create: `compose.qa-dev.yaml`
- Modify: `Makefile`

- [ ] **Step 1: Add the failing topology gate before the overlay exists**

Run:

```bash
docker compose -p quality-inspection-qa -f compose.yaml -f compose.qa-dev.yaml config
```

Expected: FAIL because `compose.qa-dev.yaml` does not yet exist.

- [ ] **Step 2: Create the exact Compose overlay**

Create `compose.qa-dev.yaml` with this topology:

```yaml
services:
  api:
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    ports: !override
      - "127.0.0.1:18000:8000"
    volumes:
      - qi_storage:/data
      - ./backend/app:/app/app
      - ./backend/assets:/app/assets:ro
  worker:
    volumes:
      - qi_storage:/data
      - ./backend/app:/app/app
      - ./backend/assets:/app/assets:ro
  frontend:
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "4173", "--strictPort"]
    ports: !override
      - "127.0.0.1:14173:4173"
    volumes:
      - ./frontend:/app
      - qi_frontend_node_modules:/app/node_modules
volumes:
  qi_postgres:
    name: quality_inspection_postgres_qa_dev
  qi_storage:
    name: quality_inspection_storage_qa_dev
  qi_frontend_node_modules:
    name: quality_inspection_frontend_node_modules_qa_dev
```

Do not add ports to `postgres`, `redis` or `worker`. Do not add `0.0.0.0` host bindings. Preserve the base `api` service name because `frontend/vite.config.ts` owns `http://api:8000` as the internal `/api` proxy target.

- [ ] **Step 3: Add exact Make targets**

Add the following commands to `Makefile`:

```make
QA_DEV_COMPOSE = docker compose -p quality-inspection-qa -f compose.yaml -f compose.qa-dev.yaml

.PHONY: qa-dev-config qa-dev-up qa-dev-down qa-dev-status qa-dev-restart-worker

qa-dev-config:
	$(QA_DEV_COMPOSE) config

qa-dev-up:
	$(QA_DEV_COMPOSE) up -d --build

qa-dev-down:
	$(QA_DEV_COMPOSE) down

qa-dev-status:
	@curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:18000/api/v1/health
	@curl --noproxy 127.0.0.1 -fsS -o /dev/null -w 'frontend HTTP %{http_code}\n' http://127.0.0.1:14173/
	@curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:14173/api/v1/health

qa-dev-restart-worker:
	$(QA_DEV_COMPOSE) restart worker
```

Use `--noproxy 127.0.0.1` so host Mihomo environment variables cannot intercept local health checks.

- [ ] **Step 4: Run the static topology gate**

Run:

```bash
make qa-dev-config > /tmp/quality-inspection-qa-compose.yaml
rg -n '127.0.0.1:18000:8000|127.0.0.1:14173:4173|quality_inspection_(postgres|storage)_qa_dev' /tmp/quality-inspection-qa-compose.yaml
! rg -n '0.0.0.0:(18000|14173)|8000:8000|3000:3000' /tmp/quality-inspection-qa-compose.yaml
```

Expected: both loopback mappings and both isolated volume names are present; no broad API/frontend binding appears.

- [ ] **Step 5: Commit only Task 1 files**

```bash
git add compose.qa-dev.yaml Makefile
git commit -m "feat: add isolated QA development runtime"
```

## Task 2: Start the QA runtime and prove source-mount behavior

**Files:**
- Modify: `compose.qa-dev.yaml` only if Task 1 runtime evidence proves a narrow configuration defect
- Test: `Makefile` targets from Task 1

- [ ] **Step 1: Start the independent runtime**

Run:

```bash
make qa-dev-up
docker compose -p quality-inspection-qa -f compose.yaml -f compose.qa-dev.yaml ps
make qa-dev-status
```

Expected: only the QA API/frontend have loopback host ports; health and same-origin Vite `/api/v1/health` return `200`.

- [ ] **Step 2: Verify frontend source mount without changing application behavior**

Run:

```bash
docker inspect quality-inspection-qa-frontend-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
docker exec quality-inspection-qa-frontend-1 sh -lc 'test -f /app/src/main.tsx && test -d /app/node_modules'
```

Expected: the current checkout `frontend` directory is mounted at `/app`, and Vite dependencies remain available through the named volume.

- [ ] **Step 3: Verify backend source mount and reload**

Run a temporary, reversible marker only in the QA source checkout:

```bash
marker_file=backend/app/_qa_reload_probe.py
printf 'MARKER = "qa-source-mounted"\n' > "$marker_file"
docker exec quality-inspection-qa-api-1 python -c 'from app._qa_reload_probe import MARKER; assert MARKER == "qa-source-mounted"'
rm "$marker_file"
docker exec quality-inspection-qa-api-1 python -c 'import app; print(app.__name__)'
```

Expected: the bind-mounted marker imports in the running QA API container, then is removed without leaving a tracked artifact. The Worker source mount is verified through `docker inspect`; after future Worker code edits, run `make qa-dev-restart-worker` before testing a task.

- [ ] **Step 4: Check runtime isolation against the existing stack**

Run:

```bash
docker inspect quality-inspection-qa-api-1 --format '{{range .Mounts}}{{.Name}} {{.Source}}{{"\n"}}{{end}}'
docker inspect quality-inspection-api-1 --format '{{range .Mounts}}{{.Name}} {{.Source}}{{"\n"}}{{end}}'
ss -ltn '( sport = :18000 or sport = :14173 or sport = :8000 or sport = :3000 )'
```

Expected: QA has `quality_inspection_*_qa_dev` volumes and only `127.0.0.1:18000/14173`; current non-QA ports are observed but not modified.

- [ ] **Step 5: Commit only a necessary Task 2 correction**

If and only if Task 2 changed `compose.qa-dev.yaml`, run:

```bash
git add compose.qa-dev.yaml
git commit -m "fix: make QA source mounts reloadable"
```

Otherwise no commit is created for verification-only work.

## Task 3: Document the host-owned tunnel and access handoff

**Files:**
- Create: `docs/operations/qa-dev-public-deployment.md`

- [ ] **Step 1: Write the non-secret operator SOP**

Document these exact invariants:

```text
QA frontend origin: http://127.0.0.1:14173
QA API origin:      http://127.0.0.1:18000
Public hostname:    https://qa.srj666.com
Tunnel route:       qa.srj666.com -> http://127.0.0.1:14173
Access policy:      require authenticated QA users before origin access
```

Document that Cloudflare credentials, API tokens, policy secrets and provider credentials are not stored in the repository or SOP. Include explicit rollback: remove the one QA ingress rule, restart/reload the tunnel as its owner requires, disable the QA Access/DNS route, and run `make qa-dev-down`.

- [ ] **Step 2: Add the Access validation contract**

Document the two mandatory external checks:

```bash
curl -I https://qa.srj666.com/
curl -fsS https://qa.srj666.com/api/v1/health
```

The first must show an Access challenge/deny for an unauthenticated client. The second is run only with an authenticated browser or approved Access service token and must return `{"status":"ok","app_name":"quality-inspection"}`. Do not place a service token in the command, repository or logs.

- [ ] **Step 3: Review the documentation for secret leakage**

Run:

```bash
rg -n -i 'api[_ -]?key|token|secret|password|credentials-file' docs/operations/qa-dev-public-deployment.md
```

Expected: documentation only states that such values must not be stored or printed; it contains no credential value or credential file path.

- [ ] **Step 4: Commit only Task 3 file**

```bash
git add docs/operations/qa-dev-public-deployment.md
git commit -m "docs: add public QA deployment handoff"
```

## Task 4: Add and validate the controlled public hostname route

**Files:**
- Modify outside repository: `/home/reggie/.cloudflared/enterprise-rag-dev.yml`
- Configure outside repository: Cloudflare DNS and Access policy for `qa.srj666.com`

- [ ] **Step 1: Confirm external prerequisites without exposing credentials**

Run:

```bash
docker inspect enterprise-rag-named-tunnel --format '{{.State.Running}}'
curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:14173/api/v1/health
```

Expected: tunnel is running and QA frontend proxy reaches the QA API. If either fails, do not modify host-owned config.

- [ ] **Step 2: Add exactly one hostname ingress rule**

Use a narrow patch to add the following mapping to the existing `ingress:` list, retaining every existing hostname and rule order:

```yaml
- hostname: qa.srj666.com
  service: http://127.0.0.1:14173
```

Do not print the surrounding credential-bearing config. Do not add `80`, `443`, `3000` or `8000` as an origin. Back up only the config file before the patch, then request the tunnel owner to reload/restart its connector using its established lifecycle command.

- [ ] **Step 3: Configure Cloudflare DNS and Access outside the repository**

In the authorized Cloudflare account, route `qa.srj666.com` to the named tunnel and create an Access application/policy that permits only the approved QA identities. Do not disable Access for convenience and do not store Cloudflare API credentials in `.env`.

- [ ] **Step 4: Verify public, Access and application paths**

Run from an external network or Cloudflare-authenticated browser:

```bash
curl -I https://qa.srj666.com/
curl -fsS https://qa.srj666.com/api/v1/health
```

Expected: anonymous request receives Access challenge/deny; authenticated request reaches the QA frontend and receives the exact API health payload through Vite `/api`. Capture only status codes, response headers needed to prove Access, timestamps and health payload; never capture Access cookies, tokens or credentials.

- [ ] **Step 5: Verify source-mount behavior through the authenticated public path**

In an authenticated browser, load `https://qa.srj666.com`, edit a non-semantic frontend source marker in the QA checkout, confirm Vite reload, then restore the file and confirm the page returns to baseline. For backend, make a reversible local QA route marker, confirm the public Vite `/api` proxy reflects it after Uvicorn reload, restore it, then rerun the exact health check. Do not use a persistent test route or alter P0 semantics.

- [ ] **Step 6: Roll back on failure and record the actual verdict**

If Access, HTTPS, API proxy or source mount replay fails, remove only the QA ingress rule, reload/restart the tunnel, disable the QA route/policy, run `make qa-dev-down`, and report `blocked` with the failing surface. Do not fall back to exposed `3000/8000`.

If all checks pass, commit only repository files changed by this plan and report external host changes separately because they are not Git-tracked.

## Final Verification And Independent Review

- [ ] Run `make qa-dev-config`, `make qa-dev-status`, and the `ss` loopback-port check after the final Compose change.
- [ ] Run `docker compose -p quality-inspection-qa -f compose.yaml -f compose.qa-dev.yaml ps` and confirm no database/Redis/Worker port appears.
- [ ] Run the authenticated browser/public replay from Task 4 and retain redacted evidence only.
- [ ] Dispatch an independent read-only reviewer to inspect the final repository diff, current Compose config, access boundaries, old-path retirement claim and verification evidence.
- [ ] Before final delivery, run `superpowers:verification-before-completion`; report local/runtime/public evidence separately and state any absent Cloudflare Access or external-network proof as a release blocker.
