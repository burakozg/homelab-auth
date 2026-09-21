from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

from homelab_auth import ratelimit
from homelab_auth.config import Settings
from homelab_auth.main import create_app

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_USERNAME = "admin"
TEST_PASSWORD = "correct-horse-battery-staple"
TEST_COOKIE_DOMAIN = ".home.arpa"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        username=TEST_USERNAME,
        password_hash=pwd_context.hash(TEST_PASSWORD),
        secret_key="test-secret-key-not-for-production",
        cookie_domain=TEST_COOKIE_DOMAIN,
        session_days=30,
        login_url="http://auth.home.arpa",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    ratelimit.reset_throttle()
    app = create_app(settings)
    # A cookie set with Domain=.home.arpa is only valid for a request host
    # under that suffix — same rule a real browser enforces. TestClient's
    # default host ("testserver") isn't, so a real subdomain host is needed
    # here for the client's cookie jar to accept and replay the cookie at
    # all; this isn't a test-only workaround; it's the same constraint the
    # cookie is designed to enforce in production.
    with TestClient(app, base_url="http://auth.home.arpa") as test_client:
        yield test_client
    ratelimit.reset_throttle()
