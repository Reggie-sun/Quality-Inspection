# Public QA Development Deployment

## Scope

This SOP exposes the isolated QA development runtime only. It does not replace the current local runtime, publish Docker service ports, or modify the RAGFlow `80/443` ingress.

## Runtime Invariants

```text
QA frontend origin: http://127.0.0.1:14173
QA API origin:      http://127.0.0.1:18000
Public hostname:    https://qa.srj666.com
Tunnel route:       qa.srj666.com -> http://127.0.0.1:14173
Access policy:      require authenticated QA users before origin access
```

Start the runtime from the repository checkout whose source is intended for QA:

```bash
make qa-dev-up
make qa-dev-status
```

The Compose project is `quality-inspection-qa`. Its API and frontend are loopback-only; PostgreSQL, Redis, and Worker have no host ports. Frontend and backend application code are bind-mounted. API changes reload through Uvicorn; after a Worker code change, run:

```bash
make qa-dev-restart-worker
```

## Cloudflare Handoff

The hostname rule, DNS route, connector lifecycle, and Access policy are host/Cloudflare-owned configuration. Configure them outside this repository.

1. Confirm `make qa-dev-status` passes.
2. Add exactly one hostname rule for `qa.srj666.com` pointing to `http://127.0.0.1:14173` in the authorized named tunnel configuration. Preserve all existing rules.
3. Route the hostname to that tunnel in the authorized Cloudflare zone.
4. Create an Access application and policy that permits only approved QA users before the origin is reached.
5. Reload or restart the connector using its established owner lifecycle command.

Do not bind this application to host `80`, `443`, `3000`, or `8000`. Do not use exposed local ports as a substitute if the public route fails.

## Access And Public Verification

Run the anonymous check from an external network:

```bash
curl -I https://qa.srj666.com/
```

Expected: Cloudflare Access returns a challenge or deny response. An unauthenticated request must not reach the application.

Use an authenticated browser or an approved Access service identity to verify the application path:

```bash
curl -fsS https://qa.srj666.com/api/v1/health
```

Expected:

```json
{"status":"ok","app_name":"quality-inspection"}
```

In the authenticated browser, load the root page and verify that the same hostname can call `/api/v1/health`. Make one reversible frontend source edit and one reversible backend source edit, verify the public route reflects each change, restore both files, then rerun the exact health request.

Do not save, print, commit, or attach Cloudflare credentials, API keys, passwords, authentication cookies, service identity values, Provider secrets, or database connection secrets.

## Rollback

1. Remove only the `qa.srj666.com` hostname rule from the host-owned tunnel configuration.
2. Reload or restart that connector, then verify its pre-existing routes remain available to their origins.
3. Disable the QA hostname DNS route and its Access application/policy outside the repository.
4. Stop the isolated QA stack:

```bash
make qa-dev-down
```

Do not remove any non-QA container, volume, tunnel, DNS record, or RAGFlow route. QA-only volumes are named `quality_inspection_*_qa_dev`; remove them only when their data is intentionally disposable.
