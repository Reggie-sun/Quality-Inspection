QI_COMPOSE_PROJECT ?= $(shell _root="$$(git rev-parse --show-toplevel 2>/dev/null || pwd)"; basename "$$_root" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_-]+/-/g; s/^[^a-z0-9]+//')
QI_QA_COMPOSE_PROJECT ?= $(QI_COMPOSE_PROJECT)-qa
BASE_COMPOSE = docker compose -p $(QI_COMPOSE_PROJECT)
QA_DEV_COMPOSE = docker compose -p $(QI_QA_COMPOSE_PROJECT) -f compose.yaml -f compose.qa-dev.yaml
TEST_BACKEND_COMPOSE = docker compose -f compose.test.yaml
LOCAL_API_PORT ?= 8000
LOCAL_FRONTEND_PORT ?= 5173
QI_DEPLOY_HOST ?= lenovo@192.168.10.200
QI_DEPLOY_DIR ?= /home/lenovo/quality-inspection
QI_DEPLOY_PROJECT ?= qi-deploy
QI_DEPLOY_REF ?= main

.PHONY: check-contracts check-api-contracts test-backend test-frontend verify-p0-offline verify-p0-live resume-gdt10e-live qa-dev-config qa-dev-up qa-dev-down qa-dev-down-legacy qa-dev-status qa-dev-restart-worker dev-local-api dev-local-frontend deploy-main

dev-local-api:
	@$(BASE_COMPOSE) stop api >/dev/null 2>&1 || true
	$(BASE_COMPOSE) -f compose.yaml -f compose.dev-local.yaml up --build api

dev-local-frontend:
	QI_API_PROXY_TARGET=http://127.0.0.1:$(LOCAL_API_PORT) npm --prefix frontend run dev -- --host 0.0.0.0 --port $(LOCAL_FRONTEND_PORT) --strictPort

deploy-main:
	@set -eu; \
	deploy_commit="$$(git rev-parse --verify "$(QI_DEPLOY_REF)^{commit}")"; \
	echo "Deploying $(QI_DEPLOY_REF) ($$deploy_commit) to $(QI_DEPLOY_HOST):$(QI_DEPLOY_DIR)"; \
	git archive --format=tar "$$deploy_commit" | \
	ssh "$(QI_DEPLOY_HOST)" 'set -eu; \
		deploy_dir="$(QI_DEPLOY_DIR)"; \
		deploy_project="$(QI_DEPLOY_PROJECT)"; \
		case "$$deploy_dir" in ""|/) echo "Unsafe QI_DEPLOY_DIR: $$deploy_dir" >&2; exit 2 ;; esac; \
		stage_dir=$$(mktemp -d /home/lenovo/.qi-deploy-main.XXXXXX); \
		trap '\''rm -rf -- "$$stage_dir"'\'' EXIT; \
		tar -xf - -C "$$stage_dir"; \
		test -f "$$stage_dir/compose.yaml"; \
		test -f "$$stage_dir/compose.server.yaml"; \
		mkdir -p "$$deploy_dir"; \
		rsync -a --delete \
			--exclude=.env \
			--exclude=backups/ \
			--exclude=compose.deploy.yaml \
			"$$stage_dir/" "$$deploy_dir/"; \
		cd "$$deploy_dir"; \
		build_attempt=1; \
		until docker compose -p "$$deploy_project" -f compose.yaml -f compose.server.yaml build api worker frontend; do \
			if [ "$$build_attempt" -ge 3 ]; then echo "Image build failed after $$build_attempt attempts" >&2; exit 1; fi; \
			build_attempt=$$((build_attempt + 1)); \
			echo "Image build failed; retrying ($$build_attempt/3)" >&2; \
			sleep 2; \
		done; \
		docker compose -p "$$deploy_project" -f compose.yaml -f compose.server.yaml stop api worker frontend; \
		docker compose -p "$$deploy_project" -f compose.yaml -f compose.server.yaml run --rm --no-deps --interactive=false --entrypoint alembic api -c /app/alembic.ini upgrade head; \
		docker compose -p "$$deploy_project" -f compose.yaml -f compose.server.yaml up -d --remove-orphans; \
		attempt=0; \
		until curl -fsS http://127.0.0.1:5173/api/v1/health; do \
			attempt=$$((attempt + 1)); \
			if [ "$$attempt" -ge 30 ]; then echo "Deployment health check failed" >&2; exit 1; fi; \
			sleep 1; \
		done; \
		echo; \
		echo "Deployment complete: http://192.168.10.200:5173/"'

qa-dev-config:
	$(QA_DEV_COMPOSE) config

qa-dev-up:
	$(QA_DEV_COMPOSE) up -d --build

qa-dev-down:
	$(QA_DEV_COMPOSE) down

qa-dev-down-legacy:
	docker compose -p quality-inspection-qa -f compose.yaml -f compose.qa-dev.yaml down --remove-orphans

qa-dev-status:
	@curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:18000/api/v1/health
	@curl --noproxy 127.0.0.1 -fsS -o /dev/null -w 'frontend HTTP %{http_code}\n' http://127.0.0.1:14173/
	@curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:14173/api/v1/health

qa-dev-restart-worker:
	$(QA_DEV_COMPOSE) restart worker

check-contracts:
	python .agent/harness/scripts/check-contracts.py

check-api-contracts:
	@test -n "$(API_CONTRACT_BASE_REF)" || (echo "API_CONTRACT_BASE_REF must name the prior approved Git revision" >&2; exit 2)
	micromamba run -n qi-p0 pytest backend/tests/contract/test_openapi_contract.py backend/tests/contract/test_error_envelope.py backend/tests/contract/test_openapi_breaking_gate.py -q
	cd backend && micromamba run -n qi-p0 python -m app.contracts.openapi --baseline tests/contract/snapshots/api-v1.openapi.json --baseline-ref "$(API_CONTRACT_BASE_REF)"
	npm --prefix frontend run api:check

test-backend:
	@set -eu; \
	test_project="quality-inspection-test-$$$$"; \
	cleanup() { \
		test_status="$$?"; \
		trap - EXIT INT TERM; \
		if $(TEST_BACKEND_COMPOSE) -p "$$test_project" down --volumes --remove-orphans; then \
			cleanup_status=0; \
		else \
			cleanup_status="$$?"; \
		fi; \
		if [ "$$test_status" -ne 0 ]; then \
			exit "$$test_status"; \
		fi; \
		exit "$$cleanup_status"; \
	}; \
	trap cleanup EXIT; \
	trap 'exit 130' INT; \
	trap 'exit 143' TERM; \
	$(TEST_BACKEND_COMPOSE) -p "$$test_project" up -d --wait; \
	test_db_endpoint="$$( \
		$(TEST_BACKEND_COMPOSE) -p "$$test_project" port postgres 5432 \
	)"; \
	test_db_port="$${test_db_endpoint##*:}"; \
	case "$$test_db_port" in \
		''|*[!0-9]*) echo "isolated PostgreSQL port is unavailable" >&2; exit 1 ;; \
	esac; \
	test_database_url="postgresql+psycopg://qi@127.0.0.1:$$test_db_port/qi"; \
	( \
		cd backend; \
		PYTHONDONTWRITEBYTECODE=1 QI_DATABASE_URL="$$test_database_url" \
			micromamba run -n qi-p0 alembic -c alembic.ini upgrade head \
	); \
	PYTHONDONTWRITEBYTECODE=1 QI_DATABASE_URL="$$test_database_url" \
		micromamba run -n qi-p0 python -m pytest backend/tests -q

test-frontend:
	micromamba run -n qi-p0 npm --prefix frontend test -- --run

verify-p0-offline: check-contracts
	@test -n "$(TASK)" || { echo "TASK is required (example: make verify-p0-offline TASK=D1-T2)" >&2; exit 2; }
	micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture --scope task --task "$(TASK)"

verify-p0-live:
	@micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py execute-start \
		--authorization "$${QI_LIVE_CYCLE_AUTHORIZATION_REF:?}" \
		--override "$${QI_LIVE_CYCLE_OVERRIDE_REF:?}"

resume-gdt10e-live:
	@micromamba run -n qi-p0 python .agent/harness/scripts/live_cycle_authorization.py execute-resume \
		--authorization "$${QI_LIVE_CYCLE_AUTHORIZATION_REF:?}" \
		--override "$${QI_LIVE_CYCLE_OVERRIDE_REF:?}" \
		--run-id "$${GDT10E_RUN_ID:?}"
