from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_returns_200(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


def test_healthz_requires_no_cookie(client: TestClient) -> None:
    # No auth, no rate-limit state, nothing — matches this fleet's convention
    # of an unauthenticated health endpoint per container.
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.cookies == {}
