# Spec Delta

## Purpose

Operators can deploy, upgrade and roll back the complete stack with one command per profile, while advanced deployments can override every value without editing scripts.

## ADDED Requirements

### Requirement: One-command deployment

A clean checkout SHALL be deployable with one documented command per profile. The command SHALL be idempotent, SHALL generate missing secrets and SHALL NOT require manual service configuration.

#### Scenario: Local deployment from a clean checkout

- **WHEN** an operator runs the local deploy command on a clean checkout
- **THEN** the stack starts on `*.pad.test`, imports the realm, bootstraps Coder and reports the access URLs

#### Scenario: Re-running deployment is safe

- **WHEN** the deploy command is run again on a healthy stack
- **THEN** existing data, secrets and certificates are preserved and the command exits successfully

#### Scenario: Failed deployment stops clearly

- **WHEN** a service fails its healthcheck during deployment
- **THEN** the command exits non-zero and prints the failing service, its health status and recent logs

### Requirement: Deployment profiles

The deployment SHALL provide `local`, `staging` and `production` profiles. The local profile SHALL need no public DNS or ACME. The production profile SHALL require explicit domains, cookie domain and admin allowlist.

#### Scenario: Local profile needs no internet-facing setup

- **WHEN** the `local` profile is selected
- **THEN** Caddy uses its internal CA, the three `*.pad.test` hosts are used and no ACME account is created

#### Scenario: Production refuses incomplete input

- **WHEN** the `production` profile is selected without domains, cookie domain or admin allowlist
- **THEN** deployment fails before any container starts and names the missing setting

### Requirement: Configuration precedence

Resolved configuration SHALL follow a documented precedence: CLI flags, environment, profile file, `.env`, then safe defaults. Every resolved value SHALL be validated before the stack starts.

#### Scenario: CLI overrides a profile value

- **WHEN** the operator passes a domain or allowlist on the command line
- **THEN** it overrides the profile and `.env` values for that run

#### Scenario: Invalid value is rejected

- **WHEN** a resolved value is malformed or still a placeholder
- **THEN** preflight fails with the variable name and does not print its secret value

### Requirement: Keycloak and Coder bootstrap

Deployment SHALL import the realm, create or rotate the Coder API key, select or create the default template and ensure an admin workspace without requiring manual browser setup.

#### Scenario: Fresh install is ready after deploy

- **WHEN** the deploy command completes on a fresh database
- **THEN** the realm exists, the Coder key is valid, the default template exists and the admin workspace is created

#### Scenario: Rerun does not duplicate bootstrap objects

- **WHEN** deployment is rerun
- **THEN** existing realm, template, key and workspace are reused or repaired rather than duplicated

### Requirement: Health and smoke gating

Deployment SHALL wait for service health and run smoke checks before reporting success. A failed check SHALL stop the deployment and SHALL NOT be reported as a successful release.

#### Scenario: Smoke failure marks deployment failed

- **WHEN** the post-deploy smoke check fails
- **THEN** the command exits non-zero and records the failed check and environment

#### Scenario: Successful deployment reports evidence

- **WHEN** all health and smoke checks pass
- **THEN** the command prints the URLs, image digests and a pass summary per check

### Requirement: Upgrade and rollback

Upgrade SHALL back up state, pin the target image digests, apply the new version and verify it. Rollback SHALL restore the previous digests and data through a documented command.

#### Scenario: Upgrade is verified

- **WHEN** an operator deploys a new version
- **THEN** the new image digests are running and the smoke checks pass before the release is recorded

#### Scenario: Rollback restores the previous release

- **WHEN** an upgrade fails verification
- **THEN** the rollback command restores the previous digests and database backup and passes smoke checks

### Requirement: Operator commands

The deployment SHALL expose documented commands for status, logs, backup, restore, rotate-key and destroy. Destroy SHALL require explicit confirmation before deleting data.

#### Scenario: Status is observable

- **WHEN** the operator requests status
- **THEN** the command shows service health, image digests, certificate state and the last smoke result

#### Scenario: Destructive teardown is guarded

- **WHEN** the operator requests destroy without an explicit data-deletion confirmation
- **THEN** the command refuses to delete volumes
