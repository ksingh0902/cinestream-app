from __future__ import annotations

import json
import logging
from urllib.parse import quote

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import SESSION_COOKIE_NAME
from .service import validate_session
from .store import is_setup_completed

logger = logging.getLogger("cinemymovies.auth.middleware")

PUBLIC_PREFIXES = (
    "/login",
    "/logout",
    "/setup",
    "/api/auth/check",
    "/favicon.ico",
)


class PrivateAccessMiddleware(BaseHTTPMiddleware):
    """
    Server-wide security gate enforcing authentication across all pages,
    APIs, proxies, and media endpoints.
    """

    async def dispatch(self, request: Request, call_next):
        # Allow CORS preflight OPTIONS requests
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # 1. Allow public authentication endpoints and browser metadata
        if any(path == p or path.startswith(f"{p}/") or path.startswith(f"{p}?") for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # 2. If initial setup has not been completed, redirect to /setup
        if not is_setup_completed():
            accept = request.headers.get("accept", "")
            is_html_request = (
                path in ("/", "/index.html", "/admin", "/login")
                or path.endswith(".html")
                or ("text/html" in accept and not path.startswith(("/api/", "/proxy/")))
            )
            if is_html_request:
                resp = RedirectResponse(url="/setup", status_code=303)
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                return resp
            body = json.dumps({"detail": "Initial setup required", "setup_url": "/setup"})
            resp = Response(content=body, status_code=401, media_type="application/json")
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            return resp

        # 3. Check for session cookie
        token = request.cookies.get(SESSION_COOKIE_NAME)
        session = validate_session(token) if token else None

        # 4. Handle unauthenticated requests
        if not session:
            # Check if this is a browser navigation request for an HTML page
            accept = request.headers.get("accept", "")
            is_html_request = (
                path in ("/", "/index.html", "/admin")
                or path.endswith(".html")
                or ("text/html" in accept and not path.startswith(("/api/", "/proxy/")))
            )

            if is_html_request:
                target_next = quote(request.url.path if request.url.path != "/login" else "/")
                resp = RedirectResponse(url=f"/login?next={target_next}", status_code=303)
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                resp.headers["Pragma"] = "no-cache"
                return resp

            # For API, stream proxy, and media requests: return 401 Unauthorized
            body = json.dumps({"detail": "Authentication required", "login_url": "/login"})
            resp = Response(
                content=body,
                status_code=401,
                media_type="application/json",
            )
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            resp.headers["Pragma"] = "no-cache"
            return resp

        # 4. Handle Role-Based Access for Admin paths
        if path.startswith("/admin") or path.startswith("/api/admin"):
            if session.get("role") != "admin":
                accept = request.headers.get("accept", "")
                if "text/html" in accept:
                    body = "<h1>403 Forbidden</h1><p>Administrator privileges required.</p><a href='/'>Return to Movies</a>"
                    resp = Response(content=body, status_code=403, media_type="text/html")
                else:
                    body = json.dumps({"detail": "Administrator privileges required"})
                    resp = Response(content=body, status_code=403, media_type="application/json")
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                return resp

        # 5. Attach authenticated user context to request state
        request.state.user = session.get("user")
        request.state.session = session

        # 6. Proceed to endpoint
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
