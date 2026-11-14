# production-deployment Specification

## Purpose
The project provides a reproducible, isolated and operable single-VPS deployment that can be exercised locally without public domains and promoted to production with real domains and trusted certificates.

## Requirements

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

### Requirement: Coder credential rotation

The deployment SHALL record the creation time of the Coder API key, SHALL rotate it before its maximum lifetime and SHALL alert when rotation is due. A workspace failure caused by an expired key SHALL be detectable without reading application logs first.

#### Scenario: Rotation is due

- **WHEN** the Coder key approaches its maximum lifetime
- **THEN** the operator receives an alert or the status command reports the due date

#### Scenario: Rotated key is valid

- **WHEN** the rotation command completes
- **THEN** Pad uses the new key, the old key is revoked and `/api/workspace/state` succeeds

### Requirement: Restore drill

The deployment SHALL provide a restore script for all service databases and SHALL support a documented drill that restores into a fresh environment without touching production data.

#### Scenario: Drill restores state

- **WHEN** the restore drill runs against a fresh database volume
- **THEN** Pad users and pads, Keycloak configuration and Coder state are present and the result is recorded

#### Scenario: Drill does not touch production

- **WHEN** the drill is started in staging
- **THEN** it uses isolated volumes and leaves the production database unchanged

### Requirement: Pinned images and rollback set

Every production image SHALL be referenced by an immutable digest. The deployment SHALL record the full digest set for each release so rollback can restore it without guessing tags.

#### Scenario: Release records digests

- **WHEN** a release is deployed
- **THEN** the digests of Caddy, Pad, PostgreSQL, Redis, Keycloak and Coder are recorded

#### Scenario: Rollback uses recorded digests

- **WHEN** rollback runs
- **THEN** every service starts from the recorded digest set

### Requirement: Operational monitoring

The deployment SHALL expose a health and alert baseline for Pad, Keycloak, Coder, TLS certificates, backup age and Coder key expiry. An operator SHALL be able to see a failed component without opening every container.

#### Scenario: Component failure is visible

- **WHEN** Pad, Keycloak or Coder becomes unhealthy
- **THEN** the status command or external probe reports the failing component

#### Scenario: Certificate or backup age is visible

- **WHEN** a certificate is near expiry or the last backup is too old
- **THEN** the operator receives an alert or a failed status check

### Requirement: Compose-wide preflight

Deployment SHALL validate every required environment value across all services before any container starts. Missing placeholders SHALL fail preflight and name the variable without printing its value.

#### Scenario: Placeholder blocks startup

- **WHEN** any required value is empty or still a documented placeholder
- **THEN** no service starts and the preflight names the variable

#### Scenario: All services are covered

- **WHEN** the preflight configuration is reviewed
- **THEN** it covers Pad, Keycloak, Coder, PostgreSQL, Redis and Caddy values, not only Pad

### Requirement: Backup retention and integrity

Production backup SHALL define a retention period and verify dump integrity. A missing, corrupt or unverifiable backup SHALL be treated as a failed operational check. Offsite and encrypted backup are explicitly out of scope for this change and tracked as follow-up.

#### Scenario: Retention is applied

- **WHEN** the backup job completes
- **THEN** dumps older than the retention period are pruned by policy

#### Scenario: Integrity failure is visible

- **WHEN** a dump cannot be listed or restored
- **THEN** the backup check fails and alerts the operator

### Requirement: Residual risk register

Every accepted production risk SHALL be listed in `risk-register.md` with severity, impact, mitigation, owner and a link to the governing requirement. A blocking risk without an entry SHALL fail readiness review.

#### Scenario: Accepted risk is linked

- **WHEN** the risk register is reviewed
- **THEN** every accepted risk names its severity, mitigation, owner and spec requirement

#### Scenario: Unregistered blocker fails review

- **WHEN** a blocking risk has no register entry
- **THEN** production readiness fails and names the missing risk
