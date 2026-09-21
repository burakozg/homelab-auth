from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from fastapi.testclient import TestClient

from homelab_auth.config import Settings
from homelab_auth.main import create_app
from tests.conftest import TEST_PASSWORD, TEST_USERNAME


def _logged_in_cookies(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "rd": "/"},
        follow_redirects=False,
    )
    return dict(resp.cookies)


def test_verify_with_valid_cookie_returns_200(client: TestClient) -> None:
    cookies = _logged_in_cookies(client)
    resp = client.get("/verify", cookies=cookies)
    assert resp.status_code == 200


def test_verify_with_no_cookie_returns_302(client: TestClient) -> None:
    resp = client.get("/verify", follow_redirects=False)
    assert resp.status_code == 302


def test_verify_with_no_cookie_sets_a_login_redirect_location_header(
    client: TestClient,
) -> None:
    resp = client.get("/verify", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")


def test_verify_redirect_is_absolute_and_uses_forwarded_headers(
    client: TestClient,
) -> None:
    # Simulates what Traefik actually sends: the subrequest hits this
    # service's own /verify path, but carries the *original* app's identity
    # in X-Forwarded-*. The Location must point back to THIS service
    # (settings.login_url), not to wherever /verify itself was requested
    # from, and must carry the original app URL as ?rd= so login can return
    # the browser there afterwards.
    resp = client.get(
        "/verify",
        headers={
            "X-Forwarded-Proto": "http",
            "X-Forwarded-Host": "podcast-digest.home.arpa",
            "X-Forwarded-Uri": "/admin?tab=settings",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers.get("location", "")
    expected_rd = quote("http://podcast-digest.home.arpa/admin?tab=settings", safe="")
    assert location == f"http://auth.home.arpa/login?rd={expected_rd}"


def test_verify_with_tampered_cookie_returns_302(client: TestClient) -> None:
    cookies = _logged_in_cookies(client)
    tampered = {
        k: (v[:-1] + ("x" if v[-1] != "x" else "y")) for k, v in cookies.items()
    }
    resp = client.get("/verify", cookies=tampered, follow_redirects=False)
    assert resp.status_code == 302


def test_verify_with_expired_cookie_returns_302(settings: Settings) -> None:
    app = create_app(settings)
    manager = app.state.login_manager
    expired_token = manager.create_access_token(
        data={"sub": TEST_USERNAME},
        expires=timedelta(seconds=-1),
    )
    with TestClient(app) as client:
        resp = client.get(
            "/verify",
            cookies={"homelab_auth_session": expired_token},
            follow_redirects=False,
        )
    assert resp.status_code == 302


def test_verify_with_valid_cookie_for_unknown_user_returns_302(settings: Settings) -> None:
    app = create_app(settings)
    manager = app.state.login_manager
    # Well-formed, well-signed token, but for a username the user_loader
    # doesn't recognise — must still fail closed.
    other_user_token = manager.create_access_token(data={"sub": "someone-else"})
    with TestClient(app) as client:
        resp = client.get(
            "/verify",
            cookies={"homelab_auth_session": other_user_token},
            follow_redirects=False,
        )
    assert resp.status_code == 302
