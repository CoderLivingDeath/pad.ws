# Spec Delta

## Purpose

The project provides a reproducible, isolated and operable single-VPS deployment that can be exercised locally without public domains and promoted to production with real domains and trusted certificates.

## ADDED Requirements

### Requirement: Isolated production topology

The production compose stack SHALL run Caddy, Pad, PostgreSQL, Redis, Keycloak and Coder on a private bridge network. It SHALL NOT use host networking, and only Caddy SHALL publish ports to the host.

#### Scenario: Services resolve each other internally

- **WHEN** the production stack is started
- **THEN** Caddy reaches Pad, Keycloak and Coder by service name, and Pad reaches PostgreSQL and Redis by service name

#### Scenario: No service bypasses Caddy

- **WHEN** the host firewall allows only SSH and Caddy's HTTP/HTTPS ports
- **THEN** PostgreSQL, Redis, Keycloak, Coder and Pad cannot be reached directly from the internet

### Requirement: No working default secrets

The production environment template SHALL NOT contain usable passwords, API keys or client secrets. Startup SHALL fail with a clear message when a required value is missing or still set to a documented placeholder.

#### Scenario: Missing secret stops startup

- **WHEN** an operator starts the production stack with an empty database password or Coder API key
- **THEN** the affected service exits with a non-zero status and a message identifying the missing variable

#### Scenario: Template does not grant access

- **WHEN** an operator copies the production template without editing it
- **THEN** the stack does not start with working credentials

### Requirement: Persistent state

PostgreSQL data, Redis data, Caddy certificates and Caddy configuration SHALL be stored in named volumes or bind mounts that survive container recreation. Keycloak and Coder SHALL use the PostgreSQL instance for their state.

#### Scenario: Restart preserves data

- **WHEN** the stack is stopped and started again without removing volumes
- **THEN** users, pads, Keycloak configuration and issued certificates are preserved

#### Scenario: Container recreation preserves data

- **WHEN** a service container is recreated by a compose update
- **THEN** its persistent data remains available through the configured volume

### Requirement: Separate service databases

Pad, Keycloak and Coder SHALL use separate PostgreSQL databases on the shared instance. Services SHALL NOT share a schema or a migration history, and the stack SHALL provision the databases before the services start.

#### Scenario: Migrations are independent

- **WHEN** the stack starts for the first time
- **THEN** each service migrates only its own database and all services become healthy

#### Scenario: Restore is per service

- **WHEN** one service database is restored
- **THEN** the other services remain consistent and do not lose data

### Requirement: Healthchecks and startup ordering

Each long-running service SHALL define a healthcheck where the image supports one. Services that depend on PostgreSQL or Redis SHALL wait for those dependencies to become healthy before starting.

#### Scenario: Pad waits for dependencies

- **WHEN** the stack starts and PostgreSQL is not yet accepting connections
- **THEN** Pad starts only after PostgreSQL and Redis report healthy

#### Scenario: Unhealthy service is visible

- **WHEN** a service fails its healthcheck
- **THEN** `docker compose ps` reports it as unhealthy and the operator can identify it without reading application logs first

### Requirement: Resource and log bounds

The production stack SHALL define memory, CPU and process limits for application services and SHALL rotate container logs so that a single service cannot exhaust host memory or disk.

#### Scenario: Log growth is bounded

- **WHEN** a service writes continuously to stdout
- **THEN** Docker rotates its log file at the configured size and retains only the configured number of files

#### Scenario: Runaway process is contained

- **WHEN** a service exceeds its configured memory limit
- **THEN** the container is constrained or restarted according to the limit instead of exhausting host memory

### Requirement: Backup and restore

The deployment SHALL include a documented and scripted PostgreSQL backup covering every service database and producing restorable dumps, and a documented restore procedure. The backup SHALL exclude live secrets from logs.

#### Scenario: Backup produces dumps for every database

- **WHEN** the backup command runs against a healthy stack
- **THEN** it writes timestamped dumps for the Pad, Keycloak and Coder databases that can be restored into empty databases

#### Scenario: Restore recovers all service state

- **WHEN** the documented restore procedure is applied to a fresh PostgreSQL volume
- **THEN** users, pads, Keycloak configuration and Coder state are available after the services start

### Requirement: Domain-optional local test mode

The stack SHALL support a local mode that uses `*.pad.test` hostnames and Caddy's internal CA, requires no public DNS or ACME account, and exercises the same routing and authentication behavior as production. Production domains SHALL be supplied through environment variables.

#### Scenario: Local stack works without a domain

- **WHEN** an operator maps `pad.pad.test`, `auth.pad.test` and `coder.pad.test` to `127.0.0.1`, trusts the Caddy root CA and sets `CADDY_TLS=internal`
- **THEN** the full login, Pad, Coder and Keycloak-admin flow works over HTTPS

#### Scenario: Production mode uses real domains

- **WHEN** `PAD_DOMAIN`, `AUTH_DOMAIN` and `CODER_DOMAIN` are set to public names and `CADDY_TLS=auto`
- **THEN** Caddy obtains publicly trusted certificates and serves the same behavior

### Requirement: Deployment runbook

The change SHALL include an operator runbook covering DNS, firewall rules, secret generation, first start, OIDC client configuration, smoke tests, backup, restore and rollback.

#### Scenario: Operator can reproduce a deployment

- **WHEN** an operator follows the runbook on a fresh Debian or Ubuntu host with Docker installed
- **THEN** the stack reaches a state where an admin can log in and open a Pad and a Coder terminal

#### Scenario: Rollback is defined

- **WHEN** a deployment fails verification
- **THEN** the runbook identifies how to stop the new stack, restore the previous compose configuration and recover data from backup

### Requirement: Docker socket risk is explicit

The runbook SHALL state that mounting the Docker socket into Coder is equivalent to granting host-level control and SHALL describe the mitigations applied and the residual risk accepted by the operator.

#### Scenario: Operator is warned before enabling Coder

- **WHEN** an operator follows the Coder section of the runbook
- **THEN** the runbook explains the Docker socket privilege, recommends restricting host access and documents that workspace isolation is not a security boundary for the host