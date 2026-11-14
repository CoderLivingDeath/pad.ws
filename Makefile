.PHONY: test-unit test-integration test-proxy test-e2e test-security test-deploy test-all test-env \
  test-coverage check-traceability

test-unit:
	@pytest tests/unit -v || { echo "Unit tests not yet implemented or pytest unavailable"; exit 1; }

test-integration:
	@bash scripts/test-integration.sh

test-proxy:
	@pytest tests/proxy -m proxy -v || { echo "Proxy tests require Caddy (make test-env)"; exit 1; }

test-e2e:
	@cd tests/e2e && npm exec playwright test || { echo "E2E tests require Playwright deps and a running test environment"; exit 1; }

test-security:
	@pytest tests/security -m security -v || { echo "Security tests require a running test environment (make test-env)"; exit 1; }

test-deploy:
	@bash tests/deploy/run-checks.sh || { echo "Deploy checks require docker compose and a running or staging environment"; exit 1; }

test-env:
	@bash scripts/test-env.sh up

test-all: test-unit test-integration test-proxy test-e2e test-security test-deploy

test-coverage:
	@bash scripts/run-coverage.sh

check-traceability:
	@python3 scripts/check-traceability.py
