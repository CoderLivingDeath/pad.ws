# edge-gateway Specification

## Purpose
Caddy provides the single public entry point for the deployment, terminating TLS and routing each configured host to its internal service with WebSocket support, baseline security headers, request limits and access logs.

## Requirements

### Requirement: Single public ingress

Only Caddy SHALL publish host ports. PostgreSQL, Redis, Keycloak, Coder and Pad SHALL be reachable only from the internal Docker network, and direct access to their native ports from outside the host SHALL be refused.

#### Scenario: Database and cache ports are not public

- **WHEN** a client outside the host attempts to connect to the published PostgreSQL or Redis port
- **THEN** the connection is refused because no such port is published

#### Scenario: Application ports are not public

- **WHEN** a client attempts to reach Keycloak, Coder or Pad on their native ports from outside the host
- **THEN** the connection is refused and the service is reachable only through Caddy

### Requirement: Host-based routing

Caddy SHALL route `PAD_DOMAIN` to the Pad service, `AUTH_DOMAIN` to Keycloak and `CODER_DOMAIN` to Coder, preserving the original host, scheme and client address in forwarding headers.

#### Scenario: Each host reaches its service

- **WHEN** a request arrives for `https://pad.example.com`, `https://auth.example.com` or `https://coder.example.com`
- **THEN** Caddy proxies it to Pad, Keycloak or Coder respectively and the upstream receives the original host and `X-Forwarded-Proto: https`

#### Scenario: Unknown host is rejected

- **WHEN** a request arrives with a `Host` header that matches no configured domain
- **THEN** Caddy does not proxy it to any backend

### Requirement: TLS termination

In production mode Caddy SHALL obtain and renew publicly trusted certificates for every configured domain. In local test mode Caddy SHALL issue certificates from its internal CA. Plain HTTP SHALL redirect to HTTPS.

#### Scenario: Production certificate is valid

- **WHEN** a browser opens a configured production domain after DNS resolves to the host
- **THEN** the TLS certificate is publicly trusted and the HTTP endpoint redirects to the same URL over HTTPS

#### Scenario: Local test uses the internal CA

- **WHEN** `CADDY_TLS=internal` and a `*.pad.test` host is opened after trusting the Caddy root CA
- **THEN** the certificate is accepted and the same HTTPS routing and authentication behavior applies

### Requirement: WebSocket proxying

Caddy SHALL proxy Pad collaboration WebSockets and Coder terminal/workspace WebSockets without terminating or buffering the upgraded connection.

#### Scenario: Pad collaboration stays connected

- **WHEN** an authenticated browser opens `/ws/pad/{pad_id}` through Caddy
- **THEN** the WebSocket upgrade succeeds and messages continue to flow in both directions until the client or server closes the connection

#### Scenario: Coder terminal stays connected

- **WHEN** an authenticated user opens an embedded Coder terminal through `CODER_DOMAIN`
- **THEN** the terminal WebSocket upgrade succeeds and remains open while the user interacts with it

### Requirement: Baseline security headers

Caddy SHALL add `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` and `Permissions-Policy` to HTTPS responses. For Pad it SHALL send `X-Frame-Options: SAMEORIGIN`. For Coder it SHALL preserve Coder's own frame-ancestors policy and SHALL NOT add a permissive frame header.

#### Scenario: HTTPS response carries baseline headers

- **WHEN** any HTTPS response is returned by Caddy
- **THEN** it includes HSTS, `X-Content-Type-Options: nosniff`, a referrer policy and a permissions policy

#### Scenario: Framing is restricted

- **WHEN** a page on an unrelated origin attempts to embed Pad or Coder in an iframe
- **THEN** the browser refuses to render the embedded page

#### Scenario: Pad allows same-origin framing only

- **WHEN** a Pad response is loaded with `X-Frame-Options: SAMEORIGIN`
- **THEN** only pages from the same Pad origin can frame it

### Requirement: Request limits and timeouts

Caddy SHALL enforce a configurable maximum request body size suitable for pad content and SHALL apply upstream connection and response timeouts so that a stalled client or backend cannot hold resources indefinitely.

#### Scenario: Oversized request is rejected

- **WHEN** a client sends a request body larger than the configured maximum
- **THEN** Caddy responds with `413 Payload Too Large` and does not proxy the body

#### Scenario: Stalled upstream is bounded

- **WHEN** an upstream accepts a connection but does not return response headers within the configured timeout
- **THEN** Caddy closes the request with a gateway error instead of waiting indefinitely

### Requirement: Access logging

Caddy SHALL write structured access logs containing timestamp, host, method, path, status, duration, bytes and client address. Logs SHALL NOT contain session cookies, authorization headers, OIDC tokens, authorization codes or state values; request headers and authentication query parameters SHALL be filtered explicitly rather than relying on defaults.

#### Scenario: Request is logged without secrets

- **WHEN** an authenticated request passes through Caddy
- **THEN** the access log records the request metadata but not the `Cookie`, `Authorization` or token values

#### Scenario: Callback query is redacted

- **WHEN** the OIDC callback request passes through Caddy
- **THEN** the access log does not contain the authorization `code` or `state` value

#### Scenario: Filtering is explicit

- **WHEN** the Caddy log configuration is reviewed
- **THEN** it contains an explicit filter for request headers and authentication query parameters, and a test proves the values are absent
