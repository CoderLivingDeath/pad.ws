# Spec Delta

## ADDED Requirements

### Requirement: Production admin allowlist is mandatory

The production profile SHALL require a non-empty, non-open `ADMIN_ALLOWLIST`. Preflight SHALL reject missing, empty, malformed or `0.0.0.0/0 ::/0` values before Caddy starts. The local profile MAY keep an open allowlist.

#### Scenario: Production open allowlist is rejected

- **WHEN** the production profile resolves `ADMIN_ALLOWLIST` to an open or missing value
- **THEN** preflight fails, names `ADMIN_ALLOWLIST` and starts no services

#### Scenario: Local open allowlist is allowed

- **WHEN** the local profile uses an open allowlist
- **THEN** the stack starts and the local acceptance flow works

#### Scenario: Configured CIDRs are enforced

- **WHEN** an admin connects from an address outside the configured CIDRs
- **THEN** Caddy returns 403 even with a valid admin session

### Requirement: Logout clears all downstream cookies

Logout SHALL clear every Coder cookie created by the deployment, not only the Pad session. The documented cookie set SHALL be removed on the Coder host before the Keycloak end-session redirect.

#### Scenario: Coder cookies are cleared

- **WHEN** the user logs out
- **THEN** the Pad session and every documented Coder cookie are cleared

#### Scenario: User switch is clean

- **WHEN** a second user logs in on the same browser
- **THEN** no Coder session or workspace from the first user is visible

### Requirement: Explicit Coder edge exceptions

The Coder UI and admin paths SHALL remain Pad-gated. Only `/api/v2/*`, `/derp`, `/derp/*`, `/bin/*`, `/@*` and Coder static assets MAY bypass Pad authentication because Coder authenticates them. The exception list SHALL be documented and tested.

#### Scenario: Coder UI stays gated

- **WHEN** an anonymous browser opens the Coder UI root
- **THEN** Caddy redirects to Pad login

#### Scenario: Machine and app paths reach Coder

- **WHEN** a Coder agent, CLI or workspace app uses an exempt path without a Pad cookie
- **THEN** Caddy forwards the request and Coder enforces its own authentication

#### Scenario: Exception list is enforced

- **WHEN** a protected Coder path is requested without a Pad session
- **THEN** Caddy denies it and the path is not silently added to the exception list

### Requirement: Session lifetime and expiry UX

The production session SHALL use the documented idle and absolute lifetimes. A 401 from a Pad API SHALL redirect the browser to login with the current path as the return destination, not loop on retries.

#### Scenario: Session lifetime matches configuration

- **WHEN** the realm and cookie lifetimes are reviewed
- **THEN** the Pad cookie Max-Age matches the configured refresh lifetime and the absolute session limit is documented

#### Scenario: Expired API session redirects

- **WHEN** a Pad API request returns 401 because the session expired
- **THEN** the frontend navigates to login with the current path as `rd`

#### Scenario: Expiry does not break Coder

- **WHEN** the Pad session is renewed through login
- **THEN** the Coder session remains usable or is re-primed without a manual Coder login
