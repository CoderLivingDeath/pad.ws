# Spec Delta

## Purpose

Every change is verified by required CI checks for tests, lints, coverage and traceability, and release images are built and recorded for manual deployment.

## ADDED Requirements

### Requirement: Required CI checks

Pull requests SHALL require config, unit, integration, proxy, security, E2E, coverage, traceability and deployment-invariant checks. A failing required check SHALL block merge.

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
- **THEN** config, proxy, security and deploy invariants run

#### Scenario: Documentation-only change is lightweight

- **WHEN** a pull request changes only documentation
- **THEN** stack and E2E jobs are skipped while lightweight checks still run

### Requirement: Image build and release recording

CI SHALL build the Pad image for pull requests without pushing, and SHALL build and publish digest-pinned images for release tags. Actions and base images SHALL be pinned.

#### Scenario: Pull request builds without pushing

- **WHEN** a pull request is opened
- **THEN** the image builds and the digest is recorded without publishing to the registry

#### Scenario: Release image is immutable

- **WHEN** a release tag is pushed
- **THEN** the image is published with recorded digests and can be referenced by the manual rollback procedure

### Requirement: CI secrets and permissions

CI SHALL use least-privilege workflow permissions and masked registry credentials. It SHALL NOT require production SSH keys, application secrets or deployment credentials.

#### Scenario: Pull request has read-only scope

- **WHEN** CI runs for a pull request
- **THEN** it has read access and no registry push or deployment secret

#### Scenario: Release credentials are masked

- **WHEN** a release workflow pushes an image
- **THEN** the registry token is provided by a protected environment or repository secret and never printed

### Requirement: CI visibility

Each run SHALL publish a summary with test results, coverage, image digest and artifact links, and SHALL retain artifacts for the configured period.

#### Scenario: Pull request summary

- **WHEN** CI completes on a pull request
- **THEN** the summary links the test reports, coverage and image digest

#### Scenario: Failing job is diagnosable

- **WHEN** a required job fails
- **THEN** the summary and artifacts identify the failed suite and the failing check

### Requirement: Manual release handoff

CI SHALL NOT deploy to staging or production. It SHALL publish a digest-pinned release manifest, and deployment and rollback SHALL require an explicit operator command.

#### Scenario: CI stops at a release artifact

- **WHEN** CI completes on `main` or a release tag
- **THEN** it publishes test, coverage and image digest evidence but does not connect to a deployment host

#### Scenario: Operator deploys explicitly

- **WHEN** an operator runs the deploy or rollback command with a recorded digest set
- **THEN** the deployment happens outside CI and the operator records the result
