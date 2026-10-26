from __future__ import annotations

import json
import logging
import sqlite3
from urllib.parse import quote

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import SESSION_COOKIE_NAME
from .service import validate_session
from .store import AuthSystemState, get_auth_system_state
from .templates import render_storage_error_page

logger = logging.getLogger("cinemymovies.auth.middleware")


try:
    import psycopg
    DB_STORAGE_ERRORS = (sqlite3.Error, OSError, psycopg.Error)
except ImportError:
    DB_STORAGE_ERRORS = (sqlite3.Error, OSError)


class PrivateAccessMiddleware(BaseHTTPMiddleware):
    """
    Server-wide security gate enforcing authentication across all pages,
    APIs, proxies, and media endpoints.
    Distinguishes:
      1. STORAGE_UNAVAILABLE -> Returns 503 error screen/JSON; denies access and NEVER exposes setup.
      2. GENUINELY_UNINITIALIZED -> Directs to /setup for first-time onboarding.
      3. INITIALIZED -> Permanently locks /setup, enforces session authentication, and routes unauthenticated visitors to /login.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            response = await self._dispatch(request, call_next)
        except DB_STORAGE_ERRORS:
            logger.exception("Authentication storage failed during request")
            if request.url.path.startswith('/api/'):
                response = Response('{"error":"storage_unavailable"}', status_code=503, media_type="application/json")
            else:
                response = HTMLResponse(render_storage_error_page(), status_code=503)
            response.headers['Retry-After'] = '5'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        return response

    async def _dispatch(self, request: Request, call_next):
        # Allow CORS preflight OPTIONS requests
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # 1. Allow browser metadata (favicon)
        if path == "/favicon.ico":
            return await call_next(request)

        # 2. Check global authentication storage state
        auth_state, state_err = get_auth_system_state()

        accept = request.headers.get("accept", "")
        is_html_request = (
            path in ("/", "/index.html", "/admin", "/login", "/setup")
            or path.endswith(".html")
            or ("text/html" in accept and not path.startswith(("/api/", "/proxy/")))
        )

        # 3. Handle Storage Failure: deny access and show 503 retry screen (NEVER setup)
        if auth_state == AuthSystemState.STORAGE_UNAVAILABLE:
            if is_html_request:
                html_body = render_storage_error_page()
                resp = HTMLResponse(content=html_body, status_code=503)
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Retry-After"] = "5"
                return resp

            body = json.dumps({
                "error": "storage_unavailable",
                "detail": "Authentication storage is temporarily unavailable. Please retry shortly.",
            })
            resp = Response(content=body, status_code=503, media_type="application/json")
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Retry-After"] = "5"
            return resp

        # 4. Handle Genuinely Uninitialized State
        if auth_state == AuthSystemState.GENUINELY_UNINITIALIZED:
            # Allow setup page and form submission
            if path == "/setup" or path.startswith("/setup/"):
                return await call_next(request)

            if is_html_request:
                resp = RedirectResponse(url="/setup", status_code=303)
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                return resp

            body = json.dumps({"detail": "Initial setup required", "setup_url": "/setup"})
            resp = Response(content=body, status_code=401, media_type="application/json")
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            return resp

        # 5. System is INITIALIZED: Setup is permanently locked
        if path == "/setup" or path.startswith("/setup/"):
            if request.method != "GET":
                return Response("Initial setup is permanently locked", status_code=403)
            resp = RedirectResponse(url="/login?notice=Initial+setup+has+already+been+completed.", status_code=303)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            return resp

        # Allow public authentication endpoints
        if any(path == p or path.startswith(f"{p}/") or path.startswith(f"{p}?") for p in ("/login", "/logout", "/api/auth/check")):
            return await call_next(request)

        # 6. Check for session cookie
        token = request.cookies.get(SESSION_COOKIE_NAME)
        session = validate_session(token) if token else None

        # 7. Handle unauthenticated / expired / revoked sessions -> Always return to /login (NEVER /setup)
        if not session:
            if is_html_request:
                target_next = quote(request.url.path if request.url.path != "/login" else "/")
                resp = RedirectResponse(url=f"/login?next={target_next}", status_code=303)
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                resp.headers["Pragma"] = "no-cache"
                return resp

            body = json.dumps({"detail": "Authentication required", "login_url": "/login"})
            resp = Response(
                content=body,
                status_code=401,
                media_type="application/json",
            )
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            resp.headers["Pragma"] = "no-cache"
            return resp

        # 8. Handle Role-Based Access for Admin paths
        if path.startswith("/admin") or path.startswith("/api/admin"):
            if session.get("role") != "admin":
                if is_html_request:
                    body = "<h1>403 Forbidden</h1><p>Administrator privileges required.</p><a href='/'>Return to Movies</a>"
                    resp = Response(content=body, status_code=403, media_type="text/html")
                else:
                    body = json.dumps({"detail": "Administrator privileges required"})
                    resp = Response(content=body, status_code=403, media_type="application/json")
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                return resp

        # 9. Attach authenticated user context to request state and proceed
        request.state.user = session.get("user")
        request.state.session = session

        response = await call_next(request)

        # Ensure no-store on sensitive paths
        if path.startswith(("/api/", "/admin", "/proxy/")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
