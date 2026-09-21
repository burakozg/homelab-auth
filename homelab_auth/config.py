"""Settings for the single admin account this service gates.

There is exactly one account. Nothing here is a user database — see the
module docstring in main.py for why that's deliberate.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    #: The one admin username.
    username: str = "admin"

    #: Bcrypt hash of the admin password — never the plaintext. Set via
    #: scripts/hash_password.py.
    password_hash: str = ""

    #: Signs the session JWT. Required in any real deployment; a blank
    #: default here means "process starts, every login fails" rather than
    #: crashing on import, which keeps /healthz answerable while it's fixed.
    secret_key: str = ""

    #: Cookie Domain attribute, e.g. ".home.arpa" — shared across every
    #: subdomain on the LAN so one login covers every gated app. Also doubles
    #: as the allow-list suffix for the ?rd= post-login redirect target.
    cookie_domain: str = ".home.arpa"

    #: Session/cookie lifetime in days. A household convenience tool, not a
    #: high-security SaaS — long-lived by design.
    session_days: int = 30

    #: Absolute origin this service is reachable at from a browser, e.g.
    #: "http://auth.home.arpa" — no trailing slash. Required so /verify can
    #: build an ABSOLUTE redirect Location: a bare "/login" would send the
    #: browser to <the-app-that-denied-it>/login, which doesn't exist there,
    #: not to this service.
    login_url: str = ""

    @property
    def configured(self) -> bool:
        """False until both secret material vars are actually set.

        Used to fail closed (503, never "open to everyone") if the container
        started without them.
        """
        return bool(self.secret_key) and bool(self.password_hash) and bool(self.login_url)
