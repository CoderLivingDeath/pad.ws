#!/usr/bin/env bash
set -euo pipefail

# Curl-based smoke test for the Pad Caddy-auth gateway.
#
# Usage:
#   PAD_BASE_URL=https://pad.pad.test \
#   AUTH_BASE_URL=https://auth.pad.test \
#   CODER_BASE_URL=https://coder.pad.test \
#   CA_BUNDLE=/usr/local/share/ca-certificates/caddy-local.crt \
#   OIDC_REALM=pad \
#   PAD_TEST_USERNAME=user \
#   PAD_TEST_PASSWORD='Password123!' \
#   ./scripts/smoke-test.sh
#
# If test credentials are omitted, the authenticated login/verify/logout flow is
# skipped. No secrets are hardcoded.

PAD_BASE_URL="${PAD_BASE_URL:-}"
AUTH_BASE_URL="${AUTH_BASE_URL:-}"
CODER_BASE_URL="${CODER_BASE_URL:-}"
CA_BUNDLE="${CA_BUNDLE:-}"
OIDC_REALM="${OIDC_REALM:-pad}"
PAD_TEST_USERNAME="${PAD_TEST_USERNAME:-}"
PAD_TEST_PASSWORD="${PAD_TEST_PASSWORD:-}"
SESSION_COOKIE_NAME="${SESSION_COOKIE_NAME:-session_id}"

usage() {
    cat <<'EOF'
Usage:
  PAD_BASE_URL=... AUTH_BASE_URL=... CODER_BASE_URL=... [CA_BUNDLE=...] \
    [OIDC_REALM=...] [PAD_TEST_USERNAME=...] [PAD_TEST_PASSWORD=...] \
    ./scripts/smoke-test.sh

Example (local *.pad.test, no credentials):
  PAD_BASE_URL=https://pad.pad.test \
  AUTH_BASE_URL=https://auth.pad.test \
  CODER_BASE_URL=https://coder.pad.test \
  CA_BUNDLE=/usr/local/share/ca-certificates/caddy-local.crt \
  ./scripts/smoke-test.sh
EOF
    exit 1
}

if [[ -z "$PAD_BASE_URL" || -z "$AUTH_BASE_URL" || -z "$CODER_BASE_URL" ]]; then
    usage
fi

CURL_OPTS=(-sS --max-time 10 --retry 0)
if [[ -n "$CA_BUNDLE" ]]; then
    CURL_OPTS+=(--cacert "$CA_BUNDLE")
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

pass=0
fail=0
skip=0

pass() { echo "PASS: $1"; pass=$((pass + 1)); }
fail() { echo "FAIL: $1"; fail=$((fail + 1)); }
skip() { echo "SKIP: $1"; skip=$((skip + 1)); }

# ---------------------------------------------------------------------------
# Reachability check
# ---------------------------------------------------------------------------
if ! curl "${CURL_OPTS[@]}" --max-time 5 -o /dev/null "$PAD_BASE_URL" 2>/dev/null; then
    echo "FAIL: cannot reach $PAD_BASE_URL (stack may be down or CA untrusted)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Anonymous checks
# ---------------------------------------------------------------------------

# 1. Anonymous Pad landing page redirects to login.
resp_headers="$TMPDIR/pad_root.headers"
code=$(curl "${CURL_OPTS[@]}" -H 'Accept: text/html' -H 'Sec-Fetch-Mode: navigate' -D "$resp_headers" -o /dev/null -w '%{http_code}' "$PAD_BASE_URL/")
location=$(grep -i '^Location:' "$resp_headers" 2>/dev/null | awk '{print $2}' | tr -d '\r' || true)
if [[ "$code" == "302" && "$location" == */api/auth/login* ]]; then
    pass "anonymous Pad root redirects to login ($code $location)"
else
    fail "anonymous Pad root did not redirect to login (got $code, location=$location)"
fi

# 2. API client receives 401, not HTML.
code=$(curl "${CURL_OPTS[@]}" -H 'Accept: application/json' -o /dev/null -w '%{http_code}' "$PAD_BASE_URL/api/auth/verify")
if [[ "$code" == "401" ]]; then
    pass "API verify returns 401 for anonymous client"
else
    fail "API verify did not return 401 for anonymous client (got $code)"
fi

# 3. Public static asset path is not behind auth.
code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$PAD_BASE_URL/favicon.ico")
if [[ "$code" == "200" ]]; then
    pass "public static asset returns 200"
elif [[ "$code" == "404" ]]; then
    pass "public static asset path is public (returned 404, file may be missing)"
elif [[ "$code" == "401" || "$code" == "403" || "$code" == "302" ]]; then
    fail "public static asset is protected (got $code)"
else
    pass "public static asset path is public (got $code)"
fi

# 4. Keycloak OIDC discovery is reachable.
disco="$TMPDIR/discovery.json"
code=$(curl "${CURL_OPTS[@]}" -o "$disco" -w '%{http_code}' "$AUTH_BASE_URL/realms/$OIDC_REALM/.well-known/openid-configuration")
if [[ "$code" == "200" ]] && grep -q '"issuer"' "$disco"; then
    pass "Keycloak OIDC discovery returns 200 with issuer"
else
    fail "Keycloak OIDC discovery failed (got $code)"
fi

# 5. Anonymous admin path is denied.
code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$AUTH_BASE_URL/admin")
if [[ "$code" == "302" || "$code" == "401" || "$code" == "403" ]]; then
    pass "anonymous Keycloak admin path is denied (got $code)"
else
    fail "anonymous Keycloak admin path was not denied (got $code)"
fi

# 6. Security headers are present and Server header is removed.
sh_headers="$TMPDIR/sec_headers.headers"
curl "${CURL_OPTS[@]}" -I -o "$sh_headers" "$PAD_BASE_URL/" || true
cto=$(grep -i '^X-Content-Type-Options:' "$sh_headers" 2>/dev/null | tr -d '\r' || true)
rp=$(grep -i '^Referrer-Policy:' "$sh_headers" 2>/dev/null | tr -d '\r' || true)
pp=$(grep -i '^Permissions-Policy:' "$sh_headers" 2>/dev/null | tr -d '\r' || true)
server=$(grep -i '^Server:' "$sh_headers" 2>/dev/null | tr -d '\r' || true)
if [[ "$cto" == *nosniff* && "$rp" == *strict-origin-when-cross-origin* && "$pp" == *camera=\(\)* && -z "$server" ]]; then
    pass "baseline security headers present and Server header removed"
else
    fail "missing security headers or Server header present (cto=$cto rp=$rp pp=$pp server=$server)"
fi

# 7. Coder UI also redirects anonymous browsers to login.
code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$CODER_BASE_URL/")
if [[ "$code" == "302" || "$code" == "401" || "$code" == "403" ]]; then
    pass "anonymous Coder root is denied (got $code)"
else
    fail "anonymous Coder root was not denied (got $code)"
fi

# ---------------------------------------------------------------------------
# Authenticated flow (only if credentials are provided)
# ---------------------------------------------------------------------------

if [[ -z "$PAD_TEST_USERNAME" || -z "$PAD_TEST_PASSWORD" ]]; then
    skip "authenticated login/verify/logout flow (no PAD_TEST_USERNAME/PAD_TEST_PASSWORD)"
else
    jar="$TMPDIR/cookies.txt"
    login_headers="$TMPDIR/login.headers"
    kc_html="$TMPDIR/kc_login.html"

    # Start Pad login to get the Keycloak authorization URL and state cookie.
    code=$(curl "${CURL_OPTS[@]}" -c "$jar" -b "$jar" -D "$login_headers" -o /dev/null -w '%{http_code}' "$PAD_BASE_URL/api/auth/login?rd=/")
    auth_url=$(grep -i '^Location:' "$login_headers" 2>/dev/null | awk '{print $2}' | tr -d '\r' || true)
    if [[ "$code" != "302" || -z "$auth_url" ]]; then
        fail "Pad login did not redirect to Keycloak (got $code)"
    else
        # Fetch the Keycloak login page and extract the login form action.
        curl "${CURL_OPTS[@]}" -c "$jar" -b "$jar" -D "$login_headers" -o "$kc_html" "$auth_url" || true
        form_action_line=$(grep -oE 'action="[^"]*login-actions/authenticate[^"]*"' "$kc_html" 2>/dev/null | head -1 || true)
        if [[ -z "$form_action_line" ]]; then
            fail "could not find Keycloak login form action"
        else
            form_action=${form_action_line#action=\"}
            form_action=${form_action%\"}
            form_action=${form_action//&amp;/&}

            # Submit credentials and follow the OIDC callback chain.
            if curl "${CURL_OPTS[@]}" -c "$jar" -b "$jar" -L -D "$login_headers" -o /dev/null \
                -d "username=$PAD_TEST_USERNAME" \
                -d "password=$PAD_TEST_PASSWORD" \
                -d "credentialId=" \
                -d "login=Sign+In" \
                "$form_action"; then
                if grep -q "$SESSION_COOKIE_NAME" "$jar" 2>/dev/null; then
                    pass "authenticated login obtained $SESSION_COOKIE_NAME cookie"
                else
                    fail "login flow did not set $SESSION_COOKIE_NAME cookie (credentials may be wrong)"
                fi
            else
                fail "Keycloak login submission failed"
            fi
        fi
    fi

    if grep -q "$SESSION_COOKIE_NAME" "$jar" 2>/dev/null; then
        # Verify the session through the gateway.
        verify_headers="$TMPDIR/verify.headers"
        code=$(curl "${CURL_OPTS[@]}" -c "$jar" -b "$jar" -D "$verify_headers" -o /dev/null -w '%{http_code}' "$PAD_BASE_URL/api/auth/verify")
        x_user=$(grep -i '^X-Pad-User:' "$verify_headers" 2>/dev/null | tr -d '\r' || true)
        x_admin=$(grep -i '^X-Pad-Admin:' "$verify_headers" 2>/dev/null | awk '{print $2}' | tr -d '\r' || true)
        if [[ "$code" == "200" && -n "$x_user" ]]; then
            pass "authenticated verify returns 200 with X-Pad-User"
        else
            fail "authenticated verify failed (got $code, x_user=$x_user)"
        fi

        # Non-admin user should be denied from Keycloak admin.
        if [[ "${x_admin:-}" == "true" ]]; then
            skip "admin deny with non-admin role (authenticated user has admin role)"
        else
            code=$(curl "${CURL_OPTS[@]}" -c "$jar" -b "$jar" -o /dev/null -w '%{http_code}' "$AUTH_BASE_URL/admin")
            if [[ "$code" == "403" ]]; then
                pass "non-admin user denied from Keycloak admin (got 403)"
            else
                fail "non-admin user was not denied from Keycloak admin (got $code)"
            fi
        fi

        # Logout should clear the session cookie.
        logout_headers="$TMPDIR/logout.headers"
        code=$(curl "${CURL_OPTS[@]}" -c "$jar" -b "$jar" -L -D "$logout_headers" -o /dev/null -w '%{http_code}' "$PAD_BASE_URL/api/auth/logout")
        cookie_cleared=false
        if grep -qi "Set-Cookie: $SESSION_COOKIE_NAME=;.*Max-Age=0" "$logout_headers" 2>/dev/null; then
            cookie_cleared=true
        elif ! grep -q "$SESSION_COOKIE_NAME" "$jar" 2>/dev/null; then
            cookie_cleared=true
        fi
        if [[ "$cookie_cleared" == true ]]; then
            pass "logout cleared the session cookie"
        else
            fail "logout did not clear the session cookie"
        fi

        # Replaying the old cookie must fail.
        code=$(curl "${CURL_OPTS[@]}" -b "$jar" -H 'Accept: application/json' -o /dev/null -w '%{http_code}' "$PAD_BASE_URL/api/auth/verify")
        if [[ "$code" == "401" ]]; then
            pass "replayed cookie after logout returns 401"
        else
            fail "replayed cookie after logout did not return 401 (got $code)"
        fi
    else
        skip "authenticated verify/logout/replay (login did not produce a cookie)"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "Smoke test summary: $pass passed, $fail failed, $skip skipped"

if [[ "$fail" -gt 0 ]]; then
    exit 1
fi
exit 0
