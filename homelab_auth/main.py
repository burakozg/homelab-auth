"""FastAPI app: the login form, the session cookie, and the Traefik gate.

Endpoints
---------
GET  /login    Serves the login form. Accepts ?rd=<url> naming where to send
               the browser after a successful login (Traefik forwardAuth
               passes the originally-requested URL through this way).
POST /login    Verifies username+password, sets the session cookie on
               success, re-renders the form with a generic error on failure.
POST /logout   Clears the session cookie.
GET  /verify   The endpoint Traefik's forwardAuth middleware calls on every
               request to a protected app: 200 (empty body) if the session
               cookie is present and valid, 401 otherwise. This is the actual
               gate — see the docstring on `verify` below for the header
               contract assumption.
GET  /healthz  Unauthenticated, always 200 if the process is up.

Single admin account, no database
----------------------------------
fastapi-login's `user_loader` normally looks a user up by id; here there is
exactly one valid id (settings.username), so the "lookup" is a string
comparison and the "user object" is just that same username echoed back.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_login import LoginManager
from passlib.context import CryptContext

from homelab_auth import ratelimit
from homelab_auth.config import Settings
from homelab_auth.redirects import safe_redirect_target
from homelab_auth.templates import render_login_page

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#: Generic message for every login failure. Never says which half was wrong —
#: that would let an attacker enumerate valid usernames.
INVALID_CREDENTIALS = "Invalid username or password."

COOKIE_PATH = "/"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory so tests can build isolated instances with their own
    settings, without touching process environment variables — same pattern
    as shortlist's api/auth.py (settings live on app.state, not as module
    globals captured at import time).
    """
    settings = settings or Settings()

    manager = LoginManager(
        settings.secret_key or "unconfigured-placeholder-secret",
        token_url="/login",  # noqa: S106 — a route path, not a credential
        use_cookie=True,
        use_header=False,
        cookie_name="homelab_auth_session",
        default_expiry=timedelta(days=settings.session_days),
    )

    @manager.user_loader()
    def load_user(username: str) -> str | None:
        return username if username == settings.username else None

    app = FastAPI(title="homelab-auth")
    app.state.settings = settings
    app.state.login_manager = manager

    def _set_session_cookie(response: Response, username: str) -> None:
        token = manager.create_access_token(
            data={"sub": username},
            expires=timedelta(days=settings.session_days),
        )
        response.set_cookie(
            key=manager.cookie_name,
            value=token,
            max_age=int(timedelta(days=settings.session_days).total_seconds()),
            path=COOKIE_PATH,
            domain=settings.cookie_domain,
            httponly=True,
            samesite="lax",
            # Plain-HTTP LAN traffic by design (matches the per-app API-key
            # headers this replaces, which were also sent over plain HTTP on
            # the LAN) — not a regression introduced by this service.
            secure=False,
        )

    @app.get("/healthz")
    async def healthz() -> Response:
        return Response(status_code=status.HTTP_200_OK)

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(rd: Annotated[str, Query()] = "/") -> HTMLResponse:
        return HTMLResponse(render_login_page(rd=rd))

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: Annotated[str, Form()],
        password: Annotated[str, Form()],
        rd: Annotated[str, Form()] = "/",
    ) -> Response:
        address = _client_ip(request)

        if ratelimit.is_throttled(address):
            return HTMLResponse(
                render_login_page(
                    rd=rd,
                    error="Too many attempts. Wait a few minutes and try again.",
                ),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not settings.configured:
            # Fail closed: an unset secret/hash must never mean "let anyone in".
            return HTMLResponse(
                render_login_page(rd=rd, error="Login is not configured yet."),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        valid_user = username == settings.username
        valid_password = pwd_context.verify(password, settings.password_hash)

        if not (valid_user and valid_password):
            ratelimit.record_failure(address)
            return HTMLResponse(
                render_login_page(rd=rd, error=INVALID_CREDENTIALS),
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        ratelimit.record_success(address)
        target = safe_redirect_target(rd, settings.cookie_domain)
        response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
        _set_session_cookie(response, username)
        return response

    @app.post("/logout")
    async def logout() -> Response:
        response = Response(status_code=status.HTTP_200_OK)
        response.delete_cookie(
            key=manager.cookie_name,
            path=COOKIE_PATH,
            domain=settings.cookie_domain,
        )
        return response

    def _deny_redirect(request: Request) -> Response:
        """Build the "not logged in" response for /verify.

        Two things this has to get right, confirmed against Traefik's actual
        forwardAuth docs (not assumed, per the note this replaces below):

        1. Status must be a real 3xx, not 401. forwardAuth forwards any
           non-2xx auth-service response to the client verbatim, but a
           browser only auto-follows a Location header on a 3xx status —
           a 401+Location renders as a blocked page, going nowhere. 302 is
           still non-2xx, so forwardAuth still denies exactly as before.
        2. Location must be ABSOLUTE, pointing at this service's own origin
           (settings.login_url). request.url inside this handler is
           Traefik's subrequest to homelab-auth's own /verify path, not the
           original app URL — a relative "/login" would resolve against the
           app the browser was actually denied on, sending it to
           <that-app>/login, which doesn't exist there. The real original
           URL comes from the X-Forwarded-Proto/Host/Uri headers Traefik
           attaches to the subrequest (falling back to this request's own
           URL only for direct, non-Traefik testing).
        """
        proto = request.headers.get("x-forwarded-proto")
        host = request.headers.get("x-forwarded-host")
        uri = request.headers.get("x-forwarded-uri", "")
        original_url = f"{proto}://{host}{uri}" if proto and host else str(request.url)

        target = f"{settings.login_url}/login?rd={quote(original_url, safe='')}"
        return Response(status_code=status.HTTP_302_FOUND, headers={"Location": target})

    @app.get("/verify")
    async def verify(request: Request) -> Response:
        """The Traefik forwardAuth gate. Contract: 200 (empty body) for a
        present-and-valid session cookie, 302 to /login for missing/invalid/
        expired — see `_deny_redirect` for why 302 and not 401.
        """
        token = request.cookies.get(manager.cookie_name)

        if not token:
            return _deny_redirect(request)

        try:
            user = await manager.get_current_user(token)
        except Exception:
            return _deny_redirect(request)

        if user is None:
            return _deny_redirect(request)

        return Response(status_code=status.HTTP_200_OK)

    return app


app = create_app()


def cli() -> None:
    """Entry point for `uv run homelab-auth` / the container CMD."""
    uvicorn.run("homelab_auth.main:app", host="0.0.0.0", port=8098)  # noqa: S104 — container's own address, meant to be reachable on the LAN


if __name__ == "__main__":
    cli()
