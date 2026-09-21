from __future__ import annotations

import pytest

from homelab_auth.redirects import safe_redirect_target

COOKIE_DOMAIN = ".home.arpa"


@pytest.mark.parametrize(
    "rd",
    [
        "/",
        "/admin",
        "/some/deep/path?x=1",
        "https://podcast-digest.home.arpa/admin",
        "http://home.arpa/",
        "https://home.arpa/x",
    ],
)
def test_accepts_relative_and_same_domain_suffix_targets(rd: str) -> None:
    assert safe_redirect_target(rd, COOKIE_DOMAIN) == rd


@pytest.mark.parametrize(
    "rd",
    [
        "https://evil.example.com",
        "https://evil.example.com/login",
        "http://not-home.arpa.evil.com",
        "//evil.example.com",
        "javascript:alert(1)",
        "ftp://home.arpa/x",
        "https://home.arpa.evil.com",
    ],
)
def test_rejects_open_redirect_attempts(rd: str) -> None:
    assert safe_redirect_target(rd, COOKIE_DOMAIN) == "/"


def test_missing_rd_falls_back_to_root() -> None:
    assert safe_redirect_target(None, COOKIE_DOMAIN) == "/"
    assert safe_redirect_target("", COOKIE_DOMAIN) == "/"
