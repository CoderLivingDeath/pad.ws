# Spec Delta

## Purpose

The change is verifiable against the running deployment: automated suites exercise the stack through Caddy, manual gates cover infrastructure that CI cannot reproduce, and every behavioral scenario is traceable to a check.

## ADDED Requirements

### Requirement: Reproducible acceptance environment

The repository SHALL provide a test environment that starts the production topology locally from a clean checkout without public DNS, ACME or manual service configuration. It SHALL build the Pad image from the working tree, import a Keycloak realm with admin and non-admin users and exact redirect URIs, and bootstrap the Coder API key and template the tests require.

#### Scenario: Clean checkout reaches a testable stack

- **WHEN** a developer runs the documented test bootstrap command on a clean checkout
- **THEN** the stack becomes healthy on `*.pad.test` with the internal CA, the imported realm and test users exist, and no public domain or certificate is required

#### Scenario: Test data is reproducible

- **WHEN** the environment is recreated from scratch
- **THEN** the same realm, users, roles, Pad data and Coder template are available without manual steps

### Requirement: Scenario traceability

Every scenario in the change's behavioral specs SHALL be mapped to at least one automated test or documented manual gate in `docs/testing.md` using stable criterion identifiers. A blocking scenario without a mapped check SHALL fail verification.

#### Scenario: Blocking criterion is mapped

- **WHEN** the traceability matrix is reviewed or validated
- **THEN** every blocking criterion names a test path or manual gate, its type and its status

#### Scenario: Unmapped scenario is detected

- **WHEN** a blocking scenario has no mapped test or gate
- **THEN** the verification step reports it as a failure rather than passing silently

### Requirement: Unit test suite

The backend SHALL have unit tests for security-critical logic that run without PostgreSQL, Redis, Keycloak or Coder. The suite SHALL cover OIDC state generation and one-time validation, redirect destination validation, cookie attributes, CORS origin policy, role and admin derivation, issuer validation and startup configuration guards.

#### Scenario: Unit suite runs in isolation

- **WHEN** the unit suite runs without any external service
- **THEN** all tests pass and no network dependency is required

#### Scenario: Negative cases are covered

- **WHEN** state is missing, mismatched or replayed, or a redirect target is external, scheme-relative or plain HTTP
- **THEN** a unit test asserts rejection

### Requirement: Integration test suite

Pad SHALL be tested against real PostgreSQL, Redis and Keycloak. The suite SHALL cover the login transaction, callback validation, session creation, token refresh, logout, the verify contract and session revocation.

#### Scenario: Login transaction is exercised

- **WHEN** the integration suite completes a login with a valid code and state
- **THEN** a session is created, the cookie is issued and the verify endpoint returns `200` with identity headers

#### Scenario: Revoked session is rejected

- **WHEN** the session is deleted or the refresh token expires
- **THEN** the verify endpoint returns `401` for API clients and the session cannot be refreshed

#### Scenario: Keycloak-issued token is validated

- **WHEN** a token with a different issuer or audience is presented
- **THEN** the integration suite asserts rejection

### Requirement: Edge proxy test suite

Proxy behavior SHALL be tested through Caddy, not against internal service ports. The suite SHALL cover the route protection matrix, content negotiation, public paths, header and cookie isolation, request limits, timeouts, security headers and administrative authorization.

#### Scenario: Tests do not bypass the edge

- **WHEN** the proxy suite runs
- **THEN** every protected request is sent to the Caddy host and direct service ports are used only for negative access tests

#### Scenario: Anonymous behavior matches the contract

- **WHEN** an anonymous browser request, a JSON API request and a static asset request reach a protected host
- **THEN** the suite observes a login redirect, `401` and `200` respectively

#### Scenario: Isolation is enforced

- **WHEN** a request carries forged `X-Pad-*` headers or a `session_id` cookie destined for Coder or Keycloak
- **THEN** the suite asserts the headers do not grant access and the cookie is not forwarded

### Requirement: Browser end-to-end suite

The primary user journeys SHALL be automated in a real browser through Caddy. The suite SHALL cover first login with return to the original path, Pad creation and opening, collaboration WebSocket, logout, user switching, replay of the logged-out cookie and revocation of an active session.

#### Scenario: First login returns to the original path

- **WHEN** an unauthenticated browser opens a Pad URL and completes login
- **THEN** the browser lands on that Pad URL with a valid session

#### Scenario: Coder terminal works after login

- **WHEN** an authenticated user opens Coder and an embedded terminal through Caddy
- **THEN** the terminal WebSocket connects and accepts input; if the environment cannot provide a Coder template, the check is recorded as a blocking staging gate instead of being skipped silently

#### Scenario: Logout ends access

- **WHEN** the user logs out and the browser replays the previous cookie
- **THEN** Pad and Coder reject the request

#### Scenario: Second user does not inherit Coder

- **WHEN** a different Pad user logs in on the same browser
- **THEN** Coder starts a new session and does not show the first user's workspaces

### Requirement: Security regression suite

Negative security checks SHALL be automated and SHALL cover origin policy, CSRF, open redirect, session fixation, session replay, identity-header spoofing, authorization of unprovisioned users, user switching and direct access to internal ports.

#### Scenario: Attack attempts are denied

- **WHEN** the suite sends a foreign CORS origin, a state-changing request without valid origin evidence, an external redirect target, a replayed pre-auth identifier and a forged identity header
- **THEN** each attempt is rejected as specified and no session is created or escalated

#### Scenario: Internal ports are closed

- **WHEN** the suite probes PostgreSQL, Redis, Pad, Keycloak and Coder native ports from outside the host
- **THEN** every connection is refused

### Requirement: Deployment and network verification

Deployment checks SHALL validate compose invariants and operational procedures: private network, no host networking, no published backend ports, healthchecks, limits, log rotation, persistent volumes, backup and restore, and certificate persistence.

#### Scenario: Compose invariants are asserted

- **WHEN** the deployment check runs against the production compose file
- **THEN** it fails if a backend service publishes a port, uses host networking, omits required limits or lacks a healthcheck

#### Scenario: Backup is restorable

- **WHEN** the check creates a dump, restores it into a fresh database and starts Pad
- **THEN** users and pads are present and the restore is reported as successful

#### Scenario: External exposure is measured

- **WHEN** the staging host is scanned from another machine
- **THEN** only SSH and Caddy's HTTP/HTTPS ports are reachable

### Requirement: CI enforcement and manual gates

Blocking automated suites SHALL run in CI on every change to authentication, proxy or deployment configuration. Checks that require public DNS, ACME, a Debian/Ubuntu host or a real Coder workspace SHALL be documented manual staging gates with recorded evidence. Release SHALL require all blocking checks to pass and all blocking gates to be signed off.

#### Scenario: Blocking suite failure stops the change

- **WHEN** a blocking automated suite fails
- **THEN** the change cannot be accepted until it passes

#### Scenario: Manual gate has evidence

- **WHEN** a manual staging gate is executed
- **THEN** the result, date, environment and operator are recorded in the testing document

### Requirement: Test result reporting

The change SHALL include a testing report listing each criterion, its result and the environment used, distinguishing passed, failed and not-run checks.

#### Scenario: Report reflects reality

- **WHEN** acceptance is requested
- **THEN** the report shows no blocking criterion as not-run or failed
