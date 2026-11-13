import secrets
import json
import jwt
import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
import os
from typing import Optional
import time
from urllib.parse import urlparse, quote, urlencode

from config import (
    FRONTEND_URL,
    STATIC_DIR,
    SESSION_COOKIE_NAME,
    COOKIE_DOMAIN,
    PAD_DOMAIN,
    AUTH_DOMAIN,
    CODER_DOMAIN,
    PAD_ALLOWED_ROLES,
)
from dependencies import (
    get_coder_api,
    get_session_domain,
    get_verified_user,
    get_identity_headers,
    is_user_provisioned,
)
from coder import CoderAPI
from dependencies import optional_auth, UserSession
from domain.session import Session, OIDC_STATE_TTL
from database.database import async_session
from domain.user import User

auth_router = APIRouter()


def _set_session_cookie(response, session_id: str, max_age: int) -> None:
    """Set the shared session cookie with the configured security attributes."""
    kwargs = {
        "key": SESSION_COOKIE_NAME,
        "value": session_id,
        "path": "/",
        "secure": True,
        "httponly": True,
        "samesite": "lax",
        "max_age": max_age,
    }
    if COOKIE_DOMAIN:
        kwargs["domain"] = COOKIE_DOMAIN
    response.set_cookie(**kwargs)


def _clear_session_cookie(response) -> None:
    """Clear the shared session cookie with the same scope used at login."""
    kwargs = {
        "key": SESSION_COOKIE_NAME,
        "path": "/",
        "secure": True,
        "httponly": True,
        "samesite": "lax",
    }
    if COOKIE_DOMAIN:
        kwargs["domain"] = COOKIE_DOMAIN
    response.delete_cookie(**kwargs)


def validate_redirect(rd: Optional[str]) -> str:
    """
    Validate a post-login return destination.

    Accepts:
    - a local absolute path starting with a single '/' (no '//', backslashes,
      or encoded path separators)
    - an absolute https:// URL whose host exactly matches PAD_DOMAIN,
      AUTH_DOMAIN or CODER_DOMAIN

    Everything else falls back to '/'.
    """
    if not rd:
        return "/"

    rd = rd.strip()
    if not rd:
        return "/"

    # Local absolute path
    if rd.startswith("/"):
        # Reject scheme-relative and protocol-relative paths disguised as local.
        if rd.startswith("//"):
            return "/"
        # Reject backslashes and encoded separators that could be abused.
        rd_lower = rd.lower()
        if "\\" in rd or "%5c" in rd_lower or "%2f" in rd_lower:
            return "/"
        # Reject control characters and null bytes.
        if any(ord(c) < 0x20 for c in rd):
            return "/"
        return rd

    # Absolute HTTPS URL
    parsed = urlparse(rd)
    if parsed.scheme != "https":
        return "/"
    if not parsed.netloc:
        return "/"
    # Reject userinfo tricks such as https://pad.example.com@evil.example
    if "@" in parsed.netloc:
        return "/"
    host = parsed.netloc.split(":")[0].lower()
    allowed_hosts = {h.lower() for h in (PAD_DOMAIN, AUTH_DOMAIN, CODER_DOMAIN) if h}
    if host not in allowed_hosts:
        return "/"
    return rd


def _is_navigation_request(request: Request) -> bool:
    """Return True if the client expects an HTML redirect (browser navigation)."""
    sec_fetch_mode = request.headers.get("Sec-Fetch-Mode")
    if sec_fetch_mode == "navigate":
        return True
    accept = request.headers.get("Accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return True
    return False


@auth_router.get("/login")
async def login(
    request: Request,
    session_domain: Session = Depends(get_session_domain),
    kc_idp_hint: Optional[str] = None,
    popup: Optional[str] = None,
    rd: Optional[str] = None,
):
    state = secrets.token_urlsafe(32)
    mode = "popup" if popup == "1" else "default"
    safe_rd = validate_redirect(rd)

    # Store a server-side login transaction bound to this state value.
    await session_domain.redis_client.setex(
        f"oidc_state:{state}",
        OIDC_STATE_TTL,
        json.dumps({
            "mode": mode,
            "rd": safe_rd,
            "created_at": time.time(),
        }),
    )

    auth_url = session_domain.get_auth_url()
    if kc_idp_hint:
        auth_url = f"{auth_url}&kc_idp_hint={kc_idp_hint}"
    auth_url = f"{auth_url}&state={state}"

    response = RedirectResponse(auth_url)
    # Cookie scoped to the auth router so it is not sent to other Pad paths.
    response.set_cookie(
        key="oidc_state",
        value=state,
        path="/api/auth",
        secure=True,
        httponly=True,
        samesite="lax",
        max_age=OIDC_STATE_TTL,
    )
    return response


@auth_router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    coder_api: CoderAPI = Depends(get_coder_api),
    session_domain: Session = Depends(get_session_domain),
):
    cookie_state = request.cookies.get("oidc_state")

    # Both cookie and query state must be present and match.
    if not state or not cookie_state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")

    # The Redis record must exist; delete it immediately to enforce one-time use.
    transaction_key = f"oidc_state:{state}"
    transaction_data = await session_domain.redis_client.get(transaction_key)
    if transaction_data:
        await session_domain.redis_client.delete(transaction_key)

    if not transaction_data:
        raise HTTPException(status_code=400, detail="Invalid or replayed OIDC state")

    try:
        if isinstance(transaction_data, (str, bytes)):
            transaction = json.loads(transaction_data)
        else:
            transaction = transaction_data
        mode = transaction.get("mode", "default")
        safe_rd = transaction.get("rd", "/")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")

    # Exchange code for token using the internal OIDC endpoint.
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            session_domain.get_token_url(),
            data={
                'grant_type': 'authorization_code',
                'client_id': session_domain.oidc_config['client_id'],
                'client_secret': session_domain.oidc_config['client_secret'],
                'code': code,
                'redirect_uri': session_domain.oidc_config['redirect_uri']
            }
        )

        if token_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Auth failed")

        token_data = token_response.json()
        expiry = token_data['refresh_expires_in']

    # Validate the access token signature, audience and issuer before creating a session.
    try:
        jwks_client = session_domain._get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token_data['access_token'])
        user_info = jwt.decode(
            token_data['access_token'],
            signing_key.key,
            algorithms=["RS256"],
            audience=session_domain.oidc_config['client_id'],
            issuer=session_domain.get_issuer(),
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=400, detail=f"Invalid token: {str(e)}")

    # Enforce Pad access provisioning when roles are configured.
    if not is_user_provisioned(user_info):
        raise HTTPException(
            status_code=403,
            detail="User is not provisioned for Pad access"
        )

    # Rotate the session identifier so the pre-auth cookie cannot access the new session.
    new_session_id = secrets.token_urlsafe(32)
    success = await session_domain.set(new_session_id, token_data, expiry)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to store session")

    await session_domain.track_event(new_session_id, 'login')

    # Ensure user exists in database (only during login)
    async with async_session() as db_session:
        try:
            await User.ensure_exists(db_session, user_info)
        except Exception as e:
            # Handle duplicate key violations gracefully - this means user already exists
            if "duplicate key value violates unique constraint" in str(e) or "already exists" in str(e):
                print(f"User {user_info.get('sub')} already exists in database (race condition handled)")
            else:
                raise e

    try:
        user_data, _ = coder_api.ensure_user_exists(user_info)
        coder_api.ensure_workspace_exists(user_data['username'])
    except Exception as e:
        print(f"Error in user/workspace setup: {str(e)}")
        # Continue with login even if Coder API fails

    if mode == "popup":
        response = FileResponse(os.path.join(STATIC_DIR, "auth/popup-close.html"))
    else:
        response = RedirectResponse(safe_rd)

    _set_session_cookie(response, new_session_id, expiry)
    response.delete_cookie(key="oidc_state", path="/api/auth")
    return response


@auth_router.get("/verify")
async def verify(request: Request):
    """
    Verification endpoint for Caddy forward_auth.

    Returns identity headers for valid sessions, redirects browser navigation
    to login, and returns 401 JSON for API clients. Never rotates the session
    identifier and never emits a Set-Cookie header.
    """
    status, user_session = await get_verified_user(request)

    if status == "ok" and user_session:
        headers = get_identity_headers(user_session)
        return JSONResponse({"authenticated": True}, headers=headers, status_code=200)

    if status == "forbidden":
        return JSONResponse(
            {"detail": "User is not provisioned for Pad access"},
            status_code=403,
        )

    if _is_navigation_request(request):
        original_host = request.headers.get("X-Original-Host") or PAD_DOMAIN
        original_uri = request.headers.get("X-Original-URI") or "/"
        original_url = f"https://{original_host}{original_uri}"
        safe_rd = validate_redirect(original_url)
        login_url = f"{FRONTEND_URL}/api/auth/login?rd={quote(safe_rd, safe='/')}"
        return RedirectResponse(login_url, status_code=302)

    return JSONResponse({"detail": "Not authenticated"}, status_code=401)


@auth_router.get("/logout")
async def logout(request: Request, session_domain: Session = Depends(get_session_domain)):
    """
    Idempotent logout. Deletes the server-side session, clears the shared
    cookie and returns the Keycloak end-session URL. Does not accept a
    user-controlled redirect target.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session_data = None

    if session_id:
        session_data = await session_domain.get(session_id)
        await session_domain.track_event(session_id, 'logout')
        await session_domain.delete(session_id)

    logout_params = {}
    if session_data and session_data.get("id_token"):
        logout_params["id_token_hint"] = session_data["id_token"]
    if FRONTEND_URL:
        logout_params["post_logout_redirect_uri"] = FRONTEND_URL

    end_session_url = (
        f"{session_domain.oidc_config['server_url']}"
        f"/realms/{session_domain.oidc_config['realm']}"
        f"/protocol/openid-connect/logout"
    )
    if logout_params:
        end_session_url = f"{end_session_url}?{urlencode(logout_params)}"

    payload = {
        "status": "success",
        "logout_url": end_session_url,
    }
    if CODER_DOMAIN:
        payload["coder_logout_url"] = f"https://{CODER_DOMAIN}/__pad/logout"

    response = JSONResponse(payload)
    _clear_session_cookie(response)
    return response


@auth_router.get("/status")
async def auth_status(
    user_session: Optional[UserSession] = Depends(optional_auth)
):
    """Check if the user is authenticated and return session information"""
    if not user_session:
        return JSONResponse({
            "authenticated": False,
            "message": "Not authenticated"
        })

    try:
        expires_in = user_session.token_data.get('exp') - time.time()

        return JSONResponse({
            "authenticated": True,
            "user": {
                "id": str(user_session.id),
                "username": user_session.username,
                "email": user_session.email,
                "name": user_session.name
            },
            "expires_in": expires_in
        })
    except Exception as e:
        return JSONResponse({
            "authenticated": False,
            "message": f"Error processing session: {str(e)}"
        })


@auth_router.post("/refresh")
async def refresh_session(request: Request, session_domain: Session = Depends(get_session_domain)):
    """Refresh the current session's access token"""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="No session found")

    session_data = await session_domain.get(session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Use the serialized refresh path so concurrent requests do not invalidate
    # the stored refresh token.
    success, new_token_data = await session_domain.refresh_token_with_lock(session_id, session_data)
    if not success:
        raise HTTPException(status_code=401, detail="Failed to refresh session")

    # Return the new expiry time
    return JSONResponse({
        "expires_in": new_token_data.get('expires_in'),
        "authenticated": True
    })
