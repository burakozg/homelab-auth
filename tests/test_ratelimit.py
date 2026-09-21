from __future__ import annotations

from fastapi.testclient import TestClient

from homelab_auth import ratelimit
from tests.conftest import TEST_PASSWORD, TEST_USERNAME


def test_rate_limiter_kicks_in_after_max_failures(client: TestClient) -> None:
    for _ in range(ratelimit.MAX_FAILURES):
        resp = client.post(
            "/login",
            data={"username": TEST_USERNAME, "password": "wrong", "rd": "/"},
        )
        assert resp.status_code == 401

    # One more attempt from the same address, even with the correct
    # password, is throttled rather than let through.
    throttled = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "rd": "/"},
    )
    assert throttled.status_code == 429
    assert "homelab_auth_session" not in throttled.cookies


def test_a_correct_login_clears_the_failure_count(client: TestClient) -> None:
    for _ in range(ratelimit.MAX_FAILURES - 1):
        client.post(
            "/login",
            data={"username": TEST_USERNAME, "password": "wrong", "rd": "/"},
        )

    ok = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "rd": "/"},
        follow_redirects=False,
    )
    assert ok.status_code == 303

    # Having just succeeded, the address should not be anywhere near
    # throttled — one more wrong attempt should not itself get 429.
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": "wrong", "rd": "/"},
    )
    assert resp.status_code == 401
