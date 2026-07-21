.PHONY: check-contracts test-backend test-frontend verify-p0-offline verify-p0-live

check-contracts:
	python .agent/harness/scripts/check-contracts.py

test-backend:
	micromamba run -n qi-p0 pytest backend/tests

test-frontend:
	micromamba run -n qi-p0 npm --prefix frontend test

verify-p0-offline:
	@test -n "$(TASK)" || { echo "TASK is required (example: make verify-p0-offline TASK=D1-T2)" >&2; exit 2; }
	python .agent/harness/scripts/run-p0.py fixture --scope task --task "$(TASK)"

verify-p0-live:
	python .agent/harness/scripts/run-p0.py live --scope full-p0
