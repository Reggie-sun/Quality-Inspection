QA_DEV_COMPOSE = docker compose -p quality-inspection-qa -f compose.yaml -f compose.qa-dev.yaml

.PHONY: check-contracts test-backend test-frontend verify-p0-offline verify-p0-live qa-dev-config qa-dev-up qa-dev-down qa-dev-status qa-dev-restart-worker

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

check-contracts:
	python .agent/harness/scripts/check-contracts.py

test-backend:
	micromamba run -n qi-p0 pytest backend/tests -q

test-frontend:
	micromamba run -n qi-p0 npm --prefix frontend test -- --run

verify-p0-offline: check-contracts
	@test -n "$(TASK)" || { echo "TASK is required (example: make verify-p0-offline TASK=D1-T2)" >&2; exit 2; }
	micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture --scope task --task "$(TASK)"

verify-p0-live: check-contracts
	micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py live --scope full-p0 --input-set current-four
