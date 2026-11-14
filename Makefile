.PHONY: test-unit test-integration test-proxy test-e2e test-security test-deploy test-all test-env \
  deploy status logs backup restore rollback

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
	@bash tests/deploy/test-config-resolution.sh || { echo "Config resolution checks failed"; exit 1; }
	@bash tests/deploy/test-restore-drill.sh || { echo "Restore drill checks failed"; exit 1; }
	@bash tests/deploy/test-env-merge.sh || { echo ".env merge checks failed"; exit 1; }
	@bash tests/deploy/test-upgrade-rollback-images.sh || { echo "Upgrade/rollback image checks failed"; exit 1; }
	@bash tests/deploy/test-upgrade-rollback-state.sh || { echo "Upgrade/rollback state checks failed"; exit 1; }

test-env:
	@bash scripts/test-env.sh up

test-all: test-unit test-integration test-proxy test-e2e test-security test-deploy

deploy:
	@bash scripts/deploy.sh up $(if $(PROFILE),--profile $(PROFILE)) $(if $(DOMAIN),--domain $(DOMAIN)) $(if $(ALLOWLIST),--allowlist $(ALLOWLIST))

status:
	@bash scripts/deploy.sh status

logs:
	@bash scripts/deploy.sh logs $(if $(FOLLOW),-f)

backup:
	@bash scripts/deploy.sh backup

restore:
	@bash scripts/deploy.sh restore

rollback:
	@bash scripts/deploy.sh rollback
