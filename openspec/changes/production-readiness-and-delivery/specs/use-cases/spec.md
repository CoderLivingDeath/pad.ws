# Spec Delta

## Purpose

Every primary user and operator journey has a stable Use Case ID, acceptance criteria and an automated or explicitly gated verification path.

## ADDED Requirements

### Requirement: UC-01 First login and return path

A new user SHALL sign in through Keycloak, receive a Pad session and return to the originally requested Pad or Coder URL. Invalid or replayed OIDC state SHALL not create a session.

#### Scenario: Successful first login

- **WHEN** an unauthenticated browser opens a protected Pad URL and completes Keycloak login
- **THEN** it lands on the original URL with a valid Pad session

#### Scenario: Replayed login is rejected

- **WHEN** a previously consumed OIDC state is submitted again
- **THEN** no new session is created and the user receives an authentication error

### Requirement: UC-02 Pad create, edit, switch and persist

An authenticated user SHALL create and edit pads and SHALL retain the latest scene when switching between tabs or reloading. A save checkpoint SHALL run before the active pad changes.

#### Scenario: Changes survive tab switch

- **WHEN** a user edits a pad, switches to another tab and returns
- **THEN** the latest elements are present

#### Scenario: Reload preserves the checkpoint

- **WHEN** the user reloads the pad after editing
- **THEN** the saved scene is loaded from the backend

### Requirement: UC-03 Real-time collaboration

Two authenticated users SHALL edit the same pad concurrently and see each other's changes. A reconnect SHALL resynchronize the scene without losing either user's latest elements.

#### Scenario: Concurrent edits converge

- **WHEN** two users edit the same pad at the same time
- **THEN** both see a reconciled scene and their changes persist

#### Scenario: Reconnect resynchronizes

- **WHEN** a client loses and restores the WebSocket connection
- **THEN** it receives the current scene and continues collaborating

### Requirement: UC-04 Coder workspace and terminal

An authenticated user SHALL receive a Coder workspace automatically and open its terminal through Pad. A new user SHALL get a workspace on first login without manual Coder setup.

#### Scenario: New user gets a workspace

- **WHEN** a provisioned user logs into Pad for the first time
- **THEN** a Coder user and workspace are created and the dashboard reports a running or starting state

#### Scenario: Terminal connects

- **WHEN** the user opens the embedded terminal
- **THEN** the terminal WebSocket connects to the workspace agent and accepts input

### Requirement: UC-05 code-server application

An authenticated user SHALL open the workspace code-server app through Coder without Pad-gate MIME or 401 failures. Coder SHALL enforce access to the app.

#### Scenario: code-server loads

- **WHEN** the user opens the code-server app for a running workspace
- **THEN** the editor loads and its static assets are served with correct MIME types

#### Scenario: Unauthorized Coder session is redirected

- **WHEN** a browser without a Coder session opens the app
- **THEN** Coder redirects to its login instead of returning an asset 401

### Requirement: UC-06 Logout, revocation and user switch

Logout SHALL delete the Pad session, clear the shared cookie and end downstream Coder session state. A different user on the same browser SHALL NOT inherit the previous Coder session.

#### Scenario: Logout denies replay

- **WHEN** the old session cookie is replayed after logout
- **THEN** Pad and Coder deny access

#### Scenario: Second user starts clean

- **WHEN** another provisioned user logs in on the same browser
- **THEN** Coder does not show the first user's session or workspaces

### Requirement: UC-07 Keycloak admin access

Keycloak admin paths SHALL require a Pad admin session, the admin role and an address inside the configured allowlist. A non-admin or out-of-allowlist user SHALL receive 403.

#### Scenario: Admin is allowed

- **WHEN** an admin from an allowed address opens the Keycloak admin console
- **THEN** Caddy proxies the request

#### Scenario: Non-admin is denied

- **WHEN** an authenticated non-admin opens an admin path
- **THEN** Caddy returns 403 before Keycloak is reached

### Requirement: UC-08 One-command deployment

An operator SHALL deploy the selected profile with one command, including realm and Coder bootstrap, and receive a verified running stack or a clear failure.

#### Scenario: Clean deploy succeeds

- **WHEN** the operator runs the profile deploy command on a clean checkout
- **THEN** the stack, realm, template and admin workspace are ready and smoke checks pass

#### Scenario: Deploy failure is actionable

- **WHEN** a service or smoke check fails
- **THEN** the command names the failed component and prints diagnostics

### Requirement: UC-09 Upgrade and rollback

An operator SHALL upgrade to pinned image digests and SHALL roll back to the previous release and database backup when verification fails.

#### Scenario: Upgrade is verified

- **WHEN** the upgrade command completes
- **THEN** the new digests are running and smoke checks pass

#### Scenario: Failed upgrade rolls back

- **WHEN** the upgraded stack fails smoke checks
- **THEN** the rollback command restores the previous digests and data and verifies them

### Requirement: UC-10 Backup and restore

An operator SHALL back up all service databases and SHALL restore them into a fresh environment with users, pads, realm and Coder state preserved.

#### Scenario: Backup is restorable

- **WHEN** a backup is restored into a fresh database volume
- **THEN** Pad users and pads, Keycloak configuration and Coder state are available

#### Scenario: Restore drill is recorded

- **WHEN** the restore drill completes
- **THEN** the result, environment, date and operator are recorded in the testing report

### Requirement: Use Case traceability

Each P0 Use Case SHALL name its automated E2E test or a documented blocking staging gate in `docs/use-cases.md`. Missing or silently skipped P0 coverage SHALL fail verification.

#### Scenario: Matrix is complete

- **WHEN** traceability is checked
- **THEN** every P0 Use Case has a test path, gate type and status

#### Scenario: Missing coverage fails

- **WHEN** a P0 Use Case has no mapped test or approved gate
- **THEN** the check fails and names the Use Case
