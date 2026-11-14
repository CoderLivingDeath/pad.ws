# Spec Delta

## Purpose

Test coverage is measured for backend, frontend and Use Cases, and CI rejects changes that drop below agreed thresholds or leave P0 journeys untested.

## ADDED Requirements

### Requirement: Backend coverage gate

The backend test suite SHALL measure line and branch coverage with `pytest-cov`. Overall coverage SHALL be at least 80% lines and 70% branches, and security-critical modules SHALL be at least 85% lines. CI SHALL fail below these thresholds.

#### Scenario: Coverage above threshold passes

- **WHEN** the backend coverage run meets every configured threshold
- **THEN** the coverage check passes and publishes the report

#### Scenario: Coverage below threshold fails

- **WHEN** overall or security-critical coverage is below its threshold
- **THEN** CI fails and names the module and percentage

### Requirement: Frontend coverage gate

Frontend unit and component tests SHALL measure coverage with Vitest coverage. The configured thresholds SHALL be at least 70% statements and lines, 60% branches and 70% functions, with at least 80% for critical auth, session and collaboration modules.

#### Scenario: Frontend coverage is enforced

- **WHEN** the frontend coverage suite runs in CI
- **THEN** the configured thresholds are applied and a failing threshold fails the job

#### Scenario: Critical modules are covered

- **WHEN** coverage is reported for auth, session or collaboration modules
- **THEN** each critical module meets its higher threshold or the check fails

### Requirement: Use Case acceptance coverage

Every P0 Use Case SHALL have at least one automated acceptance test: Playwright for user journeys and the deployment harness for operator journeys. A P0 Use Case without a mapped test SHALL fail verification; a P0 test SHALL NOT be silently skipped.

#### Scenario: P0 Use Case has an automated test

- **WHEN** the traceability check runs
- **THEN** every P0 Use Case names a Playwright or deployment-harness path and a status

#### Scenario: Missing or skipped P0 test fails

- **WHEN** a P0 Use Case has no test or its test is skipped without an approved gate
- **THEN** the coverage and traceability checks fail

### Requirement: Coverage reporting and ratchet

Coverage reports SHALL be published as CI artifacts and summarized on the pull request. Coverage SHALL NOT decrease by more than one percentage point from the recorded baseline without an explicit approval.

#### Scenario: Report is available

- **WHEN** a coverage job completes
- **THEN** the HTML and machine-readable reports are uploaded and linked from the workflow summary

#### Scenario: Regression is blocked

- **WHEN** a change lowers coverage beyond the allowed delta
- **THEN** the check fails and requires an explicit approval or additional tests

### Requirement: Test effectiveness and exclusions

Coverage SHALL exclude generated, vendor and migration files through a documented configuration. Critical negative cases SHALL be counted alongside happy paths, and flaky tests SHALL be fixed or quarantined with an owner.

#### Scenario: Exclusions are documented

- **WHEN** coverage configuration is reviewed
- **THEN** every exclusion is documented with a reason and does not hide security-critical code

#### Scenario: Flaky test is owned

- **WHEN** a test is quarantined for flakiness
- **THEN** it records an owner, a reason and a follow-up issue, and is not counted as a passing P0 gate
