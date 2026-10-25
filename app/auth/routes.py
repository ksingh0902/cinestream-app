from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from .config import (
    CSRF_COOKIE_NAME,
    IS_PRODUCTION,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
)
from .security import (
    generate_csrf_token,
    sanitize_redirect_url,
    verify_csrf_token,
)
from .service import (
    admin_change_admin_password,
    admin_change_viewer_password,
    admin_sign_out_all_viewers,
    authenticate_user,
    issue_user_session,
    terminate_session,
    validate_session,
)
from .store import (
    AuthSystemState,
    complete_initial_setup,
    count_active_sessions,
    get_auth_system_state,
    get_user,
    get_user_by_role,
    is_setup_completed,
)
from .templates import (
    render_admin_page,
    render_login_page,
    render_setup_page,
    render_storage_error_page,
)

logger = logging.getLogger("cinemymovies.auth.routes")

auth_router = APIRouter()


def _get_client_ip(request: Request) -> str:
    """Extract client IP handling reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _is_secure_request(request: Request) -> bool:
    """Determine if cookie should have Secure flag."""
    if IS_PRODUCTION:
        return True
    if request.url.scheme == "https":
        return True
    if request.headers.get("x-forwarded-proto") == "https":
        return True
    return False


def _set_no_cache(response: Response) -> None:
    """Set strictly private no-store headers on sensitive auth and admin responses."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


@auth_router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, error: Optional[str] = None):
    """Render one-time initial setup page if not yet completed and storage is healthy."""
    state, err = get_auth_system_state()
    if state == AuthSystemState.STORAGE_UNAVAILABLE:
        resp = HTMLResponse(content=render_storage_error_page(error_detail=err), status_code=503)
        _set_no_cache(resp)
        resp.headers["Retry-After"] = "5"
        return resp
    if state == AuthSystemState.INITIALIZED:
        return RedirectResponse(url="/login?notice=Initial+setup+has+already+been+completed.", status_code=303)

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or generate_csrf_token()
    html_content = render_setup_page(csrf_token=csrf_token, error=error)
    resp = HTMLResponse(content=html_content, status_code=200)
    resp.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=3600,
    )
    _set_no_cache(resp)
    return resp


@auth_router.post("/setup")
async def setup_submit(
    request: Request,
    admin_password: str = Form(""),
    confirm_admin_password: str = Form(""),
    viewer_password: str = Form(""),
    csrf_token: str = Form(""),
):
    """Process initial password configuration for admin and viewer. Permanently locked once initialized."""
    state, err = get_auth_system_state()
    if state == AuthSystemState.STORAGE_UNAVAILABLE:
        resp = HTMLResponse(content=render_storage_error_page(error_detail=err), status_code=503)
        _set_no_cache(resp)
        resp.headers["Retry-After"] = "5"
        return resp
    if state == AuthSystemState.INITIALIZED:
        return RedirectResponse(url="/login?notice=Initial+setup+has+already+been+completed.", status_code=303)

    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    if not verify_csrf_token(csrf_token, cookie_csrf):
        new_csrf = generate_csrf_token()
        resp = HTMLResponse(
            render_setup_page(csrf_token=new_csrf, error="Session expired or invalid form submission. Please try again."),
            status_code=403,
        )
        resp.set_cookie(CSRF_COOKIE_NAME, new_csrf, httponly=False, secure=_is_secure_request(request), samesite="lax", path="/", max_age=3600)
        _set_no_cache(resp)
        return resp

    if admin_password != confirm_admin_password:
        new_csrf = generate_csrf_token()
        resp = HTMLResponse(
            render_setup_page(csrf_token=new_csrf, error="Administrator passwords do not match."),
            status_code=400,
        )
        resp.set_cookie(CSRF_COOKIE_NAME, new_csrf, httponly=False, secure=_is_secure_request(request), samesite="lax", path="/", max_age=3600)
        _set_no_cache(resp)
        return resp

    ok, err = complete_initial_setup(
        admin_password=admin_password,
        viewer_password=viewer_password,
    )
    if not ok:
        new_csrf = generate_csrf_token()
        resp = HTMLResponse(
            render_setup_page(csrf_token=new_csrf, error=err or "Setup failed."),
            status_code=403 if "locked" in (err or "").lower() else 400,
        )
        resp.set_cookie(CSRF_COOKIE_NAME, new_csrf, httponly=False, secure=_is_secure_request(request), samesite="lax", path="/", max_age=3600)
        _set_no_cache(resp)
        return resp

    # Immediately log in admin
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    admin_user = get_user("admin")
    sess_id, token_val = issue_user_session(
        admin_user or {"username": "admin", "role": "admin", "auth_version": 1},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    resp = RedirectResponse(url="/admin?notice=Setup+completed+successfully!+Welcome+to+CineMyMovies.", status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token_val,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    _set_no_cache(resp)
    return resp


@auth_router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: str = "/",
    notice: Optional[str] = None,
    error: Optional[str] = None,
):
    """Render login page with CSRF protection and redirect-safety."""
    state, err = get_auth_system_state()
    if state == AuthSystemState.STORAGE_UNAVAILABLE:
        resp = HTMLResponse(content=render_storage_error_page(error_detail=err), status_code=503)
        _set_no_cache(resp)
        resp.headers["Retry-After"] = "5"
        return resp
    if state == AuthSystemState.GENUINELY_UNINITIALIZED:
        return RedirectResponse(url="/setup", status_code=303)

    # Check if already authenticated
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        sess = validate_session(token)
        if sess:
            safe_target = sanitize_redirect_url(next, default="/")
            resp = RedirectResponse(url=safe_target, status_code=303)
            _set_no_cache(resp)
            return resp

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or generate_csrf_token()
    safe_next = sanitize_redirect_url(next, default="/")
    html_content = render_login_page(
        csrf_token=csrf_token,
        next_url=safe_next,
        error=error,
        notice=notice,
    )
    resp = HTMLResponse(content=html_content, status_code=200)
    resp.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=3600,
    )
    _set_no_cache(resp)
    return resp


@auth_router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    next: str = Form("/"),
):
    """Validate credentials, issue encrypted session, and redirect safely."""
    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    if not verify_csrf_token(csrf_token, cookie_csrf):
        logger.warning("Login rejected: CSRF token mismatch from IP %s", _get_client_ip(request))
        new_csrf = generate_csrf_token()
        resp = HTMLResponse(
            render_login_page(csrf_token=new_csrf, next_url=next, error="Session expired or invalid form submission. Please try again."),
            status_code=403,
        )
        resp.set_cookie(CSRF_COOKIE_NAME, new_csrf, httponly=False, secure=_is_secure_request(request), samesite="lax", path="/", max_age=3600)
        _set_no_cache(resp)
        return resp

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    user, signed_token, err = authenticate_user(
        username=username,
        password=password,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if err or not user or not signed_token:
        new_csrf = generate_csrf_token()
        resp = HTMLResponse(
            render_login_page(csrf_token=new_csrf, next_url=next, error=err or "Invalid credentials."),
            status_code=401 if "wait" not in (err or "").lower() else 429,
        )
        resp.set_cookie(CSRF_COOKIE_NAME, new_csrf, httponly=False, secure=_is_secure_request(request), samesite="lax", path="/", max_age=3600)
        _set_no_cache(resp)
        return resp

    safe_target = sanitize_redirect_url(next, default="/")
    resp = RedirectResponse(url=safe_target, status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=signed_token,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    _set_no_cache(resp)
    logger.info("User '%s' (%s) logged in successfully from IP %s", user["username"], user["role"], ip_address)
    return resp


@auth_router.post("/logout")
async def logout(request: Request):
    """Sign out user, terminate server-side session, and clear cookies."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        terminate_session(token)

    resp = RedirectResponse(url="/login?notice=Signed+out+successfully", status_code=303)
    resp.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    resp.delete_cookie(key=CSRF_COOKIE_NAME, path="/")
    _set_no_cache(resp)
    return resp


@auth_router.get("/api/auth/check")
async def auth_check(request: Request):
    """Lightweight periodic status endpoint to detect revoked sessions promptly."""
    state, err = get_auth_system_state()
    if state == AuthSystemState.STORAGE_UNAVAILABLE:
        resp = Response(
            content=import_json().dumps({"authenticated": False, "error": "storage_unavailable", "detail": "Storage unavailable"}),
            status_code=503,
            media_type="application/json",
        )
        _set_no_cache(resp)
        resp.headers["Retry-After"] = "5"
        return resp

    token = request.cookies.get(SESSION_COOKIE_NAME)
    resp_data = {"authenticated": False}
    if token:
        sess = validate_session(token)
        if sess:
            resp_data = {
                "authenticated": True,
                "username": sess["username"],
                "role": sess["role"],
                "auth_version": sess["auth_version"],
            }
    resp = Response(
        content=import_json().dumps(resp_data),
        media_type="application/json",
    )
    _set_no_cache(resp)
    return resp


def import_json():
    import json
    return json


# --- Admin Routes ---


def _require_admin_session(request: Request) -> Optional[dict]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    sess = validate_session(token)
    if sess and sess["role"] == "admin":
        return sess
    return None


@auth_router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    notice: Optional[str] = None,
    error: Optional[str] = None,
):
    """Render the administrator control console."""
    sess = _require_admin_session(request)
    if not sess:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        # If logged in as viewer, reject with 403
        if token and validate_session(token):
            raise HTTPException(status_code=403, detail="Administrator access required")
        resp = RedirectResponse(url="/login?next=/admin", status_code=303)
        _set_no_cache(resp)
        return resp

    admin_user = sess["user"]
    viewer_user = get_user_by_role("viewer") or {"username": "viewer", "auth_version": 1}
    session_counts = count_active_sessions()

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or generate_csrf_token()
    content = render_admin_page(
        csrf_token=csrf_token,
        admin_user=admin_user,
        viewer_user=viewer_user,
        session_counts=session_counts,
        notice=notice,
        error=error,
    )
    resp = HTMLResponse(content=content, status_code=200)
    resp.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=3600,
    )
    _set_no_cache(resp)
    return resp


@auth_router.post("/api/admin/change-viewer-password")
async def admin_change_viewer_pw_submit(
    request: Request,
    current_admin_password: str = Form(""),
    new_viewer_password: str = Form(""),
    csrf_token: str = Form(""),
):
    """Admin action: Change viewer password and revoke all viewer sessions."""
    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    if not verify_csrf_token(csrf_token, cookie_csrf):
        return RedirectResponse(url="/admin?error=Invalid+or+expired+security+token.+Please+try+again.", status_code=303)

    sess = _require_admin_session(request)
    if not sess:
        raise HTTPException(status_code=403, detail="Administrator access required")

    ok, err = admin_change_viewer_password(
        current_admin_password=current_admin_password,
        new_viewer_password=new_viewer_password,
        admin_username=sess["username"],
    )

    if not ok:
        resp = RedirectResponse(url=f"/admin?error={quote(err or 'Error updating password')}", status_code=303)
        _set_no_cache(resp)
        return resp

    resp = RedirectResponse(
        url="/admin?notice=Shared+viewer+password+updated+successfully.+All+viewer+devices+have+been+signed+out.",
        status_code=303,
    )
    _set_no_cache(resp)
    return resp


@auth_router.post("/api/admin/sign-out-viewers")
async def admin_sign_out_viewers_submit(
    request: Request,
    current_admin_password: str = Form(""),
    csrf_token: str = Form(""),
):
    """Admin action: Invalidate all existing viewer sessions without changing password."""
    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    if not verify_csrf_token(csrf_token, cookie_csrf):
        return RedirectResponse(url="/admin?error=Invalid+or+expired+security+token.+Please+try+again.", status_code=303)

    sess = _require_admin_session(request)
    if not sess:
        raise HTTPException(status_code=403, detail="Administrator access required")

    ok, err = admin_sign_out_all_viewers(
        current_admin_password=current_admin_password,
        admin_username=sess["username"],
    )

    if not ok:
        resp = RedirectResponse(url=f"/admin?error={quote(err or 'Error signing out viewers')}", status_code=303)
        _set_no_cache(resp)
        return resp

    resp = RedirectResponse(
        url="/admin?notice=All+viewer+devices+have+been+signed+out+successfully.",
        status_code=303,
    )
    _set_no_cache(resp)
    return resp


@auth_router.post("/api/admin/change-admin-password")
async def admin_change_admin_pw_submit(
    request: Request,
    current_admin_password: str = Form(""),
    new_admin_password: str = Form(""),
    csrf_token: str = Form(""),
):
    """Admin action: Change personal admin password."""
    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    if not verify_csrf_token(csrf_token, cookie_csrf):
        return RedirectResponse(url="/admin?error=Invalid+or+expired+security+token.+Please+try+again.", status_code=303)

    sess = _require_admin_session(request)
    if not sess:
        raise HTTPException(status_code=403, detail="Administrator access required")

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    ok, err, new_token = admin_change_admin_password(
        current_admin_password=current_admin_password,
        new_admin_password=new_admin_password,
        admin_username=sess["username"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if not ok or not new_token:
        resp = RedirectResponse(url=f"/admin?error={quote(err or 'Error changing password')}", status_code=303)
        _set_no_cache(resp)
        return resp

    resp = RedirectResponse(url="/admin?notice=Administrator+password+changed+successfully.", status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_token,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    _set_no_cache(resp)
    return resp
