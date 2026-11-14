# Spec Delta

## ADDED Requirements

### Requirement: Auditable route authorization

Every backend route SHALL be classified as public or protected, and a test SHALL enumerate the FastAPI routes and fail when a non-public route lacks an authentication dependency or an admin route lacks the admin dependency.

#### Scenario: Protected route is registered

- **WHEN** the route inventory test runs
- **THEN** every route outside the explicit public list has `require_auth` or `require_admin`

#### Scenario: New unprotected route is caught

- **WHEN** a developer adds a sensitive endpoint without an auth dependency
- **THEN** the route inventory test fails and names the route

### Requirement: Explicit trusted proxy configuration

Production SHALL use a fixed proxy peer or a dedicated proxy network for forwarded-header trust. It SHALL NOT accept forwarded headers from arbitrary peers. Local development MAY use an explicit trusted-proxy bypass when Pad is not published.

#### Scenario: Production proxy trust is fixed

- **WHEN** the production profile is resolved
- **THEN** `TRUSTED_PROXY_IPS` is a fixed Caddy address or network, not a wildcard

#### Scenario: Forged header from a non-proxy is ignored

- **WHEN** a client outside the proxy network sends `X-Forwarded-Proto`
- **THEN** Pad does not treat the request as HTTPS and the request is refused or handled as direct HTTP

### Requirement: Bounded WebSocket revocation

An established Pad WebSocket SHALL revalidate its session at an interval no longer than 30 seconds and SHALL close when the session is revoked or the user loses Pad access.

#### Scenario: Logout closes an open socket

- **WHEN** the session is deleted while a Pad WebSocket is open
- **THEN** the socket closes within the revalidation interval

#### Scenario: Access removal closes the socket

- **WHEN** a user loses access to the pad
- **THEN** the open socket closes and no further collaboration messages are accepted

### Requirement: Edge and application log hygiene

Caddy, Pad, Keycloak and Coder logs used by this deployment SHALL NOT record session cookies, authorization headers, OIDC codes, state values or Coder API keys. A verification step SHALL exercise login, callback and logout and inspect the logs.

#### Scenario: Authentication request leaves no secrets

- **WHEN** a login, callback and logout are executed and the logs are inspected
- **THEN** no session cookie, authorization header, code, state or Coder key is present

#### Scenario: Redaction survives configuration changes

- **WHEN** the Caddy log configuration is changed
- **THEN** the redaction test fails if a protected value becomes visible
