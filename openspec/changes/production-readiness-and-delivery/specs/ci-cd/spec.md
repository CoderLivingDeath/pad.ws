# Spec Delta

## Purpose

Every change is verified by required CI checks, coverage is visible, and staging or production deployment and rollback are automated through protected environments.

## ADDED Requirements

### Requirement: Required CI checks

Pull requests SHALL require config, unit, integration, proxy, security, E2E, coverage and deployment checks. A failing required check SHALL block merge.

#### Scenario: All checks pass

- **WHEN** a pull request changes backend, frontend, Caddy, compose, scripts or tests
- **THEN** every required check runs and the merge is allowed only when all pass

#### Scenario: Required check fails

- **WHEN** one required check fails
- **THEN** the pull request cannot be merged

### Requirement: Path-aware CI triggers

CI SHALL run the relevant suites for changed areas and SHALL skip expensive stacks for documentation-only changes. A change to Caddy, compose or deployment scripts SHALL always run config, proxy and deployment checks.

#### Scenario: Edge change runs edge checks

- **WHEN** a pull request changes `deploy/**`, `docker-compose*.yml` or `scripts/**`
- **THEN** config, proxy, security and deploy checks run

#### Scenario: Documentation-only change is lightweight

- **WHEN** a pull request changes only documentation
- **THEN** expensive stack and E2E jobs are skipped while required lightweight checks still run

### Requirement: Image build and publication

CI SHALL build the Pad image for pull requests and SHALL publish immutable digest-pinned images on `main` and release tags. Actions and images SHALL be pinned.

#### Scenario: Pull request builds without pushing

- **WHEN** a pull request is opened
- **THEN** the image builds and the digest is recorded without publishing to the registry

#### Scenario: Release image is immutable

- **WHEN** a release tag is pushed
- **THEN** the image is published with recorded digests and can be referenced by rollback

### Requirement: Staging deployment

Merges to `main` SHALL deploy to staging through a protected environment after required checks pass, and SHALL run post-deploy smoke checks.

#### Scenario: Main deploys to staging

- **WHEN** a commit lands on `main` and checks pass
- **THEN** the staging environment deploys the recorded digest and smoke checks pass

#### Scenario: Staging smoke fails

- **WHEN** staging smoke fails
- **THEN** the deployment is marked failed and the previous staging release is restored

### Requirement: Production deployment

Production deployment SHALL require a release tag or manual dispatch, environment approval, a pre-deploy backup and successful smoke checks. It SHALL NOT run automatically on every commit.

#### Scenario: Approved release deploys

- **WHEN** an operator approves a production deployment for a recorded digest
- **THEN** the backup, deployment, migrations and smoke checks complete and the release is recorded

#### Scenario: Unapproved release is blocked

- **WHEN** production deployment is requested without approval
- **THEN** the workflow waits and does not start the deployment

### Requirement: Automated rollback

A failed deployment SHALL support one-command or one-workflow rollback to the previous digests and database backup, followed by smoke verification.

#### Scenario: Rollback restores service

- **WHEN** a deployment fails or is rejected after release
- **THEN** rollback restores the previous digests and backup and smoke checks pass

#### Scenario: Rollback evidence is recorded

- **WHEN** rollback completes
- **THEN** the workflow records the restored digests, backup and verification result

### Requirement: Secrets and permissions

CI/CD SHALL use GitHub Environments or equivalent secret stores, least-privilege workflow permissions and masked values. Secrets SHALL NOT appear in logs or build artifacts.

#### Scenario: Workflow uses protected secrets

- **WHEN** a deployment workflow accesses registry, SSH or application secrets
- **THEN** the values come from a protected environment and are masked

#### Scenario: Secret leakage is blocked

- **WHEN** a workflow would print a secret-bearing command
- **THEN** the step fails or redacts the value

### Requirement: CI/CD visibility

Each run SHALL publish a summary with test results, coverage, image digests, deployment URL and smoke status, and SHALL retain artifacts for the configured period.

#### Scenario: Pull request summary

- **WHEN** CI completes on a pull request
- **THEN** the summary links the test reports, coverage and image digest

#### Scenario: Deployment record

- **WHEN** a staging or production deployment completes
- **THEN** the environment, digests, operator or approver and smoke result are recorded
