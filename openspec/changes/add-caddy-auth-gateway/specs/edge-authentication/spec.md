# Spec Delta

## Purpose

Caddy authenticates every protected host and path through the existing Pad OIDC session before proxying, while keeping the OIDC login endpoints reachable and restricting administrative surfaces to authorized users.

## ADDED Requirements

### Requirement: Protected surfaces

The deployment SHALL require a valid Pad session for the entire Pad host including the landing page, for the Coder browser surfaces, and for Keycloak administrative paths under `/admin`. Coder machine API paths authenticated by Coder tokens, Pad authentication endpoints, Pad static assets and Keycloak OIDC endpoints SHALL remain reachable without a Pad session.

#### Scenario: Anonymous browser is sent to login

- **WHEN** an unauthenticated browser requests the Pad landing page, a Pad page or Coder
- **THEN** Caddy responds with a redirect to the Pad login endpoint and preserves the originally requested path on the same configured host

#### Scenario: Anonymous API call receives unauthorized

- **WHEN** an unauthenticated client requests a protected API endpoint with a JSON `Accept` header
- **THEN** Caddy returns `401 Unauthorized` instead of an HTML redirect

#### Scenario: Login endpoints remain public

- **WHEN** a browser requests the Pad login, callback or status endpoint, a Pad static asset or a Keycloak OIDC endpoint
- **THEN** Caddy forwards the request without requiring a prior session

### Requirement: Machine clients on Coder

The Coder CLI, workspace agents and IDE integrations SHALL authenticate to Coder with Coder's own token mechanism and SHALL NOT require a Pad session. Caddy SHALL exempt only the Coder API paths those clients use, while the Coder UI and browser paths remain Pad-gated.

#### Scenario: CLI with a Coder token is allowed

- **WHEN** the Coder CLI calls a Coder API path with a valid Coder session token and no Pad cookie
- **THEN** Caddy forwards the request and Coder authorizes it

#### Scenario: Tokenless machine request is denied

- **WHEN** a machine client calls a Coder API path without a Coder token and without a Pad session
- **THEN** Coder returns `401` and no data is served

#### Scenario: Browser UI stays gated

- **WHEN** an unauthenticated browser opens the Coder UI
- **THEN** Caddy redirects to Pad login instead of forwarding the request

### Requirement: Authorized users only

Pad SHALL create a session only for a Keycloak user provisioned for Pad access. Self-registration SHALL be disabled, and a user without the required role, group or allowlist entry SHALL be denied even after successful Keycloak authentication.

#### Scenario: Unprovisioned user is denied

- **WHEN** Keycloak authenticates a user who lacks the Pad role, group or allowlist entry
- **THEN** Pad returns `403`, creates no session and does not set the session cookie

#### Scenario: Provisioned user is allowed

- **WHEN** a user with the required Pad access completes authentication
- **THEN** Pad creates the session and the normal protected surfaces become reachable

#### Scenario: Registration is disabled

- **WHEN** an anonymous visitor attempts to create an account on the realm
- **THEN** Keycloak refuses registration

### Requirement: Keycloak public surface

Keycloak OIDC endpoints and the account console SHALL remain reachable without a Pad session because Keycloak authenticates them itself. Account registration SHALL be disabled, and administrative paths SHALL remain Pad-gated.

#### Scenario: Account console uses Keycloak authentication

- **WHEN** an anonymous browser opens the Keycloak account console
- **THEN** Keycloak requires its own login instead of a Pad session

#### Scenario: Administrative paths still require Pad authorization

- **WHEN** a user opens a Keycloak administrative path without a Pad admin session
- **THEN** Caddy denies the request before Keycloak is reached

### Requirement: Session verification contract

Pad SHALL expose `GET /api/auth/verify` for Caddy. A valid session SHALL return `200` with the authenticated user identifier, roles and an admin flag in dedicated response headers. An invalid or missing session SHALL return `401` for API clients and a redirect to login for browser navigation.

#### Scenario: Valid session is accepted

- **WHEN** Caddy calls the verify endpoint with a valid session cookie
- **THEN** Pad returns `200` and identity, role and admin-flag headers for that user

#### Scenario: Expired token is refreshed

- **WHEN** the access token is expired but a valid refresh token exists
- **THEN** Pad refreshes the session, returns `200` and the request continues without forcing a new login

#### Scenario: Missing session is rejected

- **WHEN** the verify endpoint is called without a session cookie
- **THEN** it returns `401` for API clients or a redirect to login for browser navigation

### Requirement: Session verification does not rotate the cookie

`GET /api/auth/verify` SHALL NOT rotate the session identifier and SHALL NOT depend on the browser receiving a `Set-Cookie` header from the verification response. Token refresh SHALL update server-side session state only.

#### Scenario: Refresh keeps the session identifier

- **WHEN** the verify endpoint refreshes an expired access token
- **THEN** the session identifier and the browser cookie remain unchanged

#### Scenario: Verify response carries no cookie update

- **WHEN** Caddy calls the verify endpoint
- **THEN** the response contains no `Set-Cookie` header that the browser would need to receive

### Requirement: Verify content negotiation

`GET /api/auth/verify` SHALL redirect only top-level browser navigation to login. It SHALL return `401` JSON for API and scripted clients, including requests whose `Accept` header is `*/*`.

#### Scenario: Browser navigation is redirected

- **WHEN** the verify request indicates navigation with `Sec-Fetch-Mode: navigate` or an `Accept` header containing `text/html`
- **THEN** Pad returns `302` to the login endpoint with the original destination

#### Scenario: Scripted client receives unauthorized

- **WHEN** the verify request has `Accept: */*` or `application/json`
- **THEN** Pad returns `401` JSON instead of a redirect

#### Scenario: Command-line client receives unauthorized

- **WHEN** a client sends no browser navigation headers
- **THEN** Pad returns `401` and never an HTML login page

### Requirement: Single refresh path

Token refresh SHALL be single-flight. `/api/auth/verify` and any explicit refresh endpoint SHALL NOT rotate the same refresh token concurrently or invalidate a session refreshed by the other path.

#### Scenario: Concurrent refresh is serialized

- **WHEN** verify and an explicit refresh request arrive for the same session at the same time
- **THEN** one refresh occurs and the session remains valid

#### Scenario: Explicit refresh is idempotent

- **WHEN** the explicit refresh endpoint is called with a valid session
- **THEN** it returns success without breaking the session or the stored refresh token

### Requirement: Redirect after login

After a successful OIDC callback Pad SHALL redirect the browser to the original protected path supplied in the login request when it is either a local absolute path or an absolute HTTPS URL on one of the configured Pad, Coder or Keycloak hosts. Scheme-relative URLs, non-HTTPS URLs and hosts outside that allowlist SHALL be rejected and replaced with `/`.

#### Scenario: Local return path is honored

- **WHEN** a user starts login from `/pad/{pad_id}` and completes authentication
- **THEN** Pad redirects to `/pad/{pad_id}`

#### Scenario: Configured sibling host is honored

- **WHEN** a user starts login from a Coder URL and completes authentication
- **THEN** Pad redirects to the original HTTPS URL on the configured Coder host

#### Scenario: External return path is rejected

- **WHEN** the login request contains `rd=https://attacker.example` or `rd=//attacker.example`
- **THEN** Pad ignores it and redirects to `/`

### Requirement: Session cookie scope

The session cookie SHALL be set with `Secure`, `HttpOnly` and `SameSite=Lax`. When a shared parent domain is configured, the cookie SHALL use that domain so Caddy can validate the same session on the Pad, Coder and Keycloak hosts. When the Coder host is protected in production, a shared parent domain SHALL be configured and startup SHALL fail with a clear message when it is missing. Logout SHALL clear the cookie with the same scope.

#### Scenario: Cookie is not readable by scripts

- **WHEN** the session cookie is set or read in the browser
- **THEN** JavaScript cannot access it because the cookie is `HttpOnly`

#### Scenario: Cookie is available to the auth layer on sibling hosts

- **WHEN** a user with a valid session opens the Coder host
- **THEN** the browser sends the session cookie to Caddy and Caddy can validate it against Pad

#### Scenario: Logout clears the shared cookie

- **WHEN** the user logs out
- **THEN** Pad deletes the server-side session and clears the cookie for the configured domain and path

#### Scenario: Production requires a shared cookie domain

- **WHEN** the production stack protects the Coder host but no shared cookie domain is configured
- **THEN** startup fails with a message naming the missing setting instead of starting an unreachable Coder host

### Requirement: Session lifetime

Access token, refresh token and session cookie lifetimes SHALL be documented and consistent. The cookie SHALL NOT expire before the server-side session unless a silent re-authentication path is defined and tested.

#### Scenario: Cookie expiry re-authenticates silently

- **WHEN** the session cookie expires while the Keycloak SSO session is still valid
- **THEN** the next navigation re-authenticates without prompting and restores the Pad session

#### Scenario: Absolute expiry requires credentials

- **WHEN** the refresh lifetime ends
- **THEN** the session cannot be refreshed, verify returns `401` and the user must authenticate again

#### Scenario: Lifetimes are explicit

- **WHEN** the deployment configuration is reviewed
- **THEN** the access token, refresh token and cookie lifetimes are stated and match the observed behavior

### Requirement: Logout ends downstream sessions

Logout SHALL delete the Pad session, clear the shared cookie and end the Coder session associated with the same browser, so that a different Pad user on that browser cannot inherit the previous Coder session.

#### Scenario: Coder session ends with Pad logout

- **WHEN** the user logs out of Pad
- **THEN** the next Coder request requires a new Coder authentication instead of reusing the previous Coder session

#### Scenario: User switch does not inherit Coder

- **WHEN** a second Pad user logs in on the same browser
- **THEN** Coder does not show the first user's session or workspaces

### Requirement: Administrative authorization

Keycloak administrative paths SHALL require both a valid Pad session with the `admin` role and, when configured, a client address from the allowlist. The Pad `admin` role and Keycloak administrative permissions SHALL be provisioned separately and documented. The allowlist SHALL accept IPv4 and IPv6 CIDRs, and malformed values SHALL fail startup.

#### Scenario: Admin reaches Keycloak console

- **WHEN** an authenticated user with the `admin` role requests `/admin` on the Keycloak host from an allowed address
- **THEN** Caddy proxies the request to Keycloak

#### Scenario: Non-admin is denied

- **WHEN** an authenticated user without the `admin` role requests a Keycloak administrative path
- **THEN** Caddy returns `403 Forbidden` and does not proxy the request

#### Scenario: Address outside the allowlist is denied

- **WHEN** an `admin` user requests a Keycloak administrative path from an address outside the configured allowlist
- **THEN** Caddy returns `403 Forbidden`

#### Scenario: IPv6 allowlist is honored

- **WHEN** an `admin` user connects over IPv6 from an address inside the allowlist
- **THEN** Caddy proxies the request, and an IPv6 address outside the allowlist receives `403`

#### Scenario: Malformed allowlist stops startup

- **WHEN** the allowlist contains an invalid CIDR or a comma-separated value Caddy cannot parse
- **THEN** startup fails with a message naming the setting instead of running with an ineffective allowlist

### Requirement: Identity header isolation

Caddy SHALL remove client-supplied identity headers before authentication and SHALL add identity headers only from the verified response. Backends SHALL NOT treat a client-supplied `X-Pad-*` header as proof of identity.

#### Scenario: Spoofed identity header is ignored

- **WHEN** a client sends `X-Pad-User` or `X-Pad-Roles` directly to Pad, Coder or Keycloak
- **THEN** Caddy removes the header and the backend does not grant access based on it

### Requirement: Fail-closed behavior

If the verification endpoint is unavailable, times out or returns an unexpected error, Caddy SHALL deny protected requests with a gateway error. It SHALL NOT allow the request through unauthenticated.

#### Scenario: Pad is unavailable

- **WHEN** the verify endpoint cannot be reached while a protected request arrives
- **THEN** Caddy returns `502 Bad Gateway` or `503 Service Unavailable` and does not proxy the protected request

### Requirement: Session revocation

When a session is deleted or expires, subsequent protected requests SHALL be rejected even if the browser still holds the cookie. A user removed from Pad access SHALL lose access to Coder and Keycloak administrative paths at the next request.

#### Scenario: Logged-out cookie no longer works

- **WHEN** a user logs out and then replays the previous cookie against a protected endpoint
- **THEN** Caddy receives `401` from the verify endpoint and denies the request

#### Scenario: Revoked user loses Coder access

- **WHEN** an administrator deletes a user's session or the user's Pad access is removed
- **THEN** the next request to Coder through Caddy is denied