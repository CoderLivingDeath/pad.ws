# application-security Specification

## Purpose
Pad's browser-facing behavior remains safe when it is served through Caddy, including origin handling, session lifecycle, OIDC flow validation, proxy trust and embedding rules for Coder.

## Requirements

### Requirement: Restricted CORS

The Pad API SHALL allow credentialed cross-origin requests only from the configured frontend origin. It SHALL NOT combine a wildcard origin with credentials or reflect arbitrary request origins.

#### Scenario: Configured origin is allowed

- **WHEN** the frontend at `FRONTEND_URL` calls the Pad API with credentials
- **THEN** the response includes an `Access-Control-Allow-Origin` value equal to that origin and allows credentials

#### Scenario: Other origin is rejected

- **WHEN** a page on an unrelated origin calls the Pad API with credentials
- **THEN** the response does not grant that origin access

### Requirement: CSRF protection for state-changing requests

Pad SHALL validate the `Origin`, or the `Referer` when `Origin` is absent, of every state-changing request against the configured frontend origin and SHALL reject mismatches with `403`. `SameSite=Lax` and restricted CORS SHALL NOT be considered sufficient on their own. Logout MAY remain a `GET` because it only ends the current session, but it SHALL be idempotent and SHALL NOT accept a redirect target.

#### Scenario: Cross-site state change is rejected

- **WHEN** a state-changing request arrives with a foreign or missing `Origin`
- **THEN** Pad returns `403` and does not modify data

#### Scenario: Legitimate frontend request succeeds

- **WHEN** the Pad frontend sends a state-changing request with the configured origin
- **THEN** Pad processes it normally

#### Scenario: Logout cannot be abused as a redirect

- **WHEN** a cross-site request invokes logout with an external redirect parameter
- **THEN** Pad ends only the current session, ignores the redirect target and returns a response that does not navigate off-site

### Requirement: OIDC state validation

Login SHALL generate a cryptographically random `state` value, bind it to the login attempt in server-side storage, and require an exact match at the callback. A missing, unknown, reused or mismatched `state` SHALL reject the callback.

#### Scenario: Valid state completes login

- **WHEN** the callback contains the `state` value issued for the current login attempt
- **THEN** Pad exchanges the code and creates the session

#### Scenario: Missing state is rejected

- **WHEN** the callback arrives without a `state` parameter
- **THEN** Pad returns an authentication error and does not create a session

#### Scenario: Replayed state is rejected

- **WHEN** an attacker replays a previously used `state` value
- **THEN** Pad rejects the callback and does not create a session

### Requirement: Session fixation resistance

Pad SHALL issue a new session identifier after successful authentication and SHALL invalidate any pre-authentication session identifier associated with that login attempt.

#### Scenario: Pre-login identifier cannot be reused

- **WHEN** a user completes login and an attacker replays the session identifier that existed before authentication
- **THEN** the replayed identifier does not grant access

### Requirement: Secure session cookie attributes

Pad SHALL set the session cookie with `Secure`, `HttpOnly` and `SameSite=Lax`, and with the configured domain and path. The cookie SHALL NOT contain access or refresh tokens.

#### Scenario: Cookie protects token material

- **WHEN** the session cookie is inspected in the browser
- **THEN** it contains only an opaque identifier and is not readable by JavaScript

#### Scenario: Cookie is not sent over plain HTTP

- **WHEN** a request is made to a plain HTTP endpoint for the configured domain
- **THEN** the browser does not send the `Secure` session cookie

### Requirement: Trusted proxy handling

Pad SHALL accept forwarded scheme and client-address headers only from the configured proxy peers. The deployment SHALL ensure those peers are only Caddy; when no fixed proxy peer is configured, Pad SHALL be unreachable except through Caddy. Redirects, cookie security decisions and generated URLs SHALL use the public HTTPS scheme and host seen by the client.

#### Scenario: Public scheme is used behind Caddy

- **WHEN** Caddy forwards an HTTPS request to Pad
- **THEN** Pad generates redirects and URLs with `https` and the public host

#### Scenario: Direct access cannot spoof the scheme

- **WHEN** a client outside the deployment network attempts to reach Pad directly with a forged `X-Forwarded-Proto` header
- **THEN** the connection is refused and Pad never evaluates the header

### Requirement: Exact OIDC redirect registration

Keycloak clients SHALL register exact redirect URIs for the Pad callback and the Coder callback. Wildcard redirect URIs and wildcard web origins SHALL NOT be used in production.

#### Scenario: Registered callback succeeds

- **WHEN** Pad or Coder sends its configured callback URI to Keycloak
- **THEN** Keycloak accepts the request

#### Scenario: Unregistered callback is refused

- **WHEN** a request uses a callback URI that is not exactly registered
- **THEN** Keycloak refuses to redirect to it

### Requirement: Coder embedding restrictions

Coder SHALL allow framing only by the configured Pad origin, and its OIDC integration SHALL NOT accept unverified email addresses as sufficient proof of identity.

#### Scenario: Pad can embed Coder

- **WHEN** Pad embeds a Coder terminal from `CODER_DOMAIN`
- **THEN** Coder's content security policy permits the Pad origin as a frame ancestor

#### Scenario: Unrelated site cannot embed Coder

- **WHEN** a page on an unrelated origin embeds `CODER_DOMAIN`
- **THEN** the browser blocks the frame because the origin is not an allowed frame ancestor

#### Scenario: Unverified email is rejected

- **WHEN** Keycloak reports an email address that the user has not verified
- **THEN** Coder does not treat that claim as verified identity

### Requirement: WebSocket authentication

Pad SHALL validate the session and the `Origin` of every WebSocket handshake. Established connections SHALL revalidate the session at a configured interval not exceeding 60 seconds and close when the session is revoked.

#### Scenario: Cross-origin handshake is rejected

- **WHEN** a page on a foreign origin opens a Pad WebSocket with a valid cookie
- **THEN** Pad rejects the handshake and does not start collaboration

#### Scenario: Logout closes an open socket

- **WHEN** the session is deleted while a Pad WebSocket is open
- **THEN** the socket closes within the revalidation interval

#### Scenario: Removed user loses the socket

- **WHEN** a user loses access to the pad
- **THEN** the open socket closes and no further messages are accepted

### Requirement: No secrets in application logs

Pad SHALL NOT log session identifiers, access or refresh tokens, authorization codes or cookie values. Error paths SHALL log at most truncated, non-reversible identifiers.

#### Scenario: Authentication logs are clean

- **WHEN** login, refresh, logout and an authentication error are exercised
- **THEN** the application logs contain no full session identifier, token, code or cookie value

#### Scenario: Error paths do not leak identifiers

- **WHEN** a session lookup or token validation fails
- **THEN** the logged message does not contain the full session identifier or token

### Requirement: Authenticated API default

Every Pad API route SHALL require a valid session except the explicitly public auth, status and runtime-configuration endpoints. Authorization failures SHALL return `401` for missing or invalid sessions and `403` for insufficient permissions.

#### Scenario: Protected route without session

- **WHEN** a client calls a pad, user or workspace API route without a valid session
- **THEN** Pad returns `401`

#### Scenario: Insufficient permission

- **WHEN** an authenticated user requests a pad they cannot access or an admin-only operation without the `admin` role
- **THEN** Pad returns `403`
