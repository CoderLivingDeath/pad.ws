# Spec Delta

## ADDED Requirements

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
