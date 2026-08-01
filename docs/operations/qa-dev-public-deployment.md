# Public QA Development Deployment

## Scope

This SOP exposes the local development runtime through the public QA hostname and exposes the host-run frontend to the LAN. It does not expose Docker service ports beyond loopback or modify the RAGFlow `80/443` ingress.

## Runtime Invariants

```text
Local API origin:    http://127.0.0.1:8000
Frontend listener:   http://0.0.0.0:5173
Tunnel origin:       http://127.0.0.1:5173
LAN frontend URL:    http://<host-lan-ip>:5173
Public hostname:    https://qa.srj666.com
Tunnel route:       qa.srj666.com -> http://127.0.0.1:5173
Public access:      anonymous direct access
```

Start the API and frontend from the `main` checkout in two terminals:

```bash
make dev-local-api
make dev-local-frontend
```

The API uses `compose.dev-local.yaml` for bind mounts and Uvicorn reload. The frontend runs Vite directly from the checkout, listens on `0.0.0.0:5173`, and proxies `/api` to `127.0.0.1:8000`. The wildcard frontend listener accepts both the loopback Tunnel origin and direct LAN requests.

## Cloudflare Handoff

The hostname rule, DNS route, and connector lifecycle are host/Cloudflare-owned configuration. Configure them outside this repository.

1. Confirm `curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:8000/api/v1/health` passes, `http://127.0.0.1:5173/` loads, and `http://<host-lan-ip>:5173/` loads from the LAN.
2. Add exactly one hostname rule for `qa.srj666.com` pointing to `http://127.0.0.1:5173` in the authorized named tunnel configuration. Preserve all existing rules.
3. Route the hostname to that tunnel in the authorized Cloudflare zone.
4. Confirm no Cloudflare Access application targets `qa.srj666.com`.
5. Reload or restart the connector using its established owner lifecycle command.

Do not use host `80`, `443`, `3000`, or `8000` as the tunnel origin. The API is published loopback-only on `8000`; the Tunnel continues to use frontend loopback port `5173`, while the same frontend listener is intentionally reachable on the host LAN IP at port `5173`.

## LAN Verification

From another device on a routed LAN, run:

```bash
curl --noproxy '*' -fsS http://<host-lan-ip>:5173/
curl --noproxy '*' -fsS http://<host-lan-ip>:5173/api/v1/health
```

Expected: the first request returns the frontend application and the second returns the same health payload as the loopback and public paths. If the LAN device is on another VLAN, the router must permit that VLAN to reach the host LAN IP on TCP `5173`.

## Public Verification

Run the anonymous checks from an external network:

```bash
curl -fsS https://qa.srj666.com/
curl -fsS https://qa.srj666.com/api/v1/health
```

Expected: the first request returns the frontend application and the second returns:

```json
{"status":"ok","app_name":"quality-inspection"}
```

In a fresh browser context with no cookies, load the root page and verify that the same hostname can call `/api/v1/health`. Make one reversible frontend source edit and one reversible backend source edit, verify the public route reflects each change, restore both files, then rerun the exact health request.

Do not save, print, commit, or attach Cloudflare credentials, API keys, passwords, authentication cookies, service identity values, Provider secrets, or database connection secrets.

## Rollback

1. Remove only the `qa.srj666.com` hostname rule from the host-owned tunnel configuration.
2. Reload or restart that connector, then verify its pre-existing routes remain available to their origins.
3. Disable the QA hostname DNS route outside the repository.
4. Stop the local development processes with `Ctrl-C` in their terminals. If the old isolated QA stack is still running, stop it with:

```bash
make qa-dev-down
```

Do not remove any non-QA container, volume, tunnel, DNS record, or RAGFlow route. QA-only volumes are named `quality_inspection_*_qa_dev`; remove them only when their data is intentionally disposable.

To roll back only the LAN exposure, restore the `dev-local-frontend` Vite host flag in `Makefile` to `127.0.0.1`, restart the target, verify the loopback root and `/api/v1/health`, then confirm the host LAN IP no longer listens on port `5173`.
