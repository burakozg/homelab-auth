from __future__ import annotations

from fastapi.testclient import TestClient

from homelab_auth.main import INVALID_CREDENTIALS
from tests.conftest import TEST_PASSWORD, TEST_USERNAME


def test_successful_login_sets_a_valid_session_cookie(client: TestClient) -> None:
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "rd": "/"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "homelab_auth_session" in resp.cookies

    cookie_header = resp.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "samesite=lax" in cookie_header.lower()
    assert "domain=.home.arpa" in cookie_header.lower() or "domain=home.arpa" in cookie_header.lower()

    # The session the login just set actually verifies.
    verify_resp = client.get("/verify", cookies=resp.cookies)
    assert verify_resp.status_code == 200


def test_wrong_password_fails_with_generic_error(client: TestClient) -> None:
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": "not-the-password", "rd": "/"},
    )
    assert resp.status_code == 401
    assert "homelab_auth_session" not in resp.cookies
    assert INVALID_CREDENTIALS in resp.text


def test_wrong_username_fails_with_the_same_generic_error(client: TestClient) -> None:
    resp = client.post(
        "/login",
        data={"username": "not-admin", "password": TEST_PASSWORD, "rd": "/"},
    )
    assert resp.status_code == 401
    assert INVALID_CREDENTIALS in resp.text

    # No username enumeration: the wrong-username and wrong-password
    # responses must be byte-for-byte the same error text.
    wrong_password = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": "not-the-password", "rd": "/"},
    )
    assert resp.text == wrong_password.text


def test_login_form_renders_with_rd_carried_through(client: TestClient) -> None:
    resp = client.get("/login", params={"rd": "/some/admin/page"})
    assert resp.status_code == 200
    assert "/some/admin/page" in resp.text


def test_logout_clears_the_cookie(client: TestClient) -> None:
    login_resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "rd": "/"},
        follow_redirects=False,
    )
    logout_resp = client.post("/logout", cookies=login_resp.cookies)
    assert logout_resp.status_code == 200
    set_cookie = logout_resp.headers.get("set-cookie", "")
    assert "homelab_auth_session=" in set_cookie
    # Clearing sets an empty/expired cookie rather than omitting it.
    assert "homelab_auth_session=\"\"" in set_cookie or "Max-Age=0" in set_cookie
