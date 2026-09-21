"""Validate the ?rd= post-login redirect target.

Traefik's forwardAuth passes the originally-requested URL through as ``rd`` so
a user who got bounced to /login lands back where they wanted rather than on
a generic post-login page. Trusting that value unchecked makes this an open
redirect: a link like ``/login?rd=https://evil.example.com`` would send an
authenticated browser wherever an attacker wants after a real login.

Allowed:
  - a bare path ("/", "/podcast-digest/admin") — same-origin by construction.
  - an absolute URL whose host is AUTH_COOKIE_DOMAIN's exact suffix (e.g.
    "https://podcast-digest.home.arpa/admin" when the cookie domain is
    ".home.arpa") — this is safe precisely because the session cookie set
    with Domain=.home.arpa is only ever sent to hosts in that suffix, so a
    redirect there cannot leak the cookie anywhere new.

Anything else — a different host, a protocol-relative "//host" URL (which
urlsplit treats as carrying a netloc), a non-http(s) scheme — falls back to
"/".
"""

from __future__ import annotations

from urllib.parse import urlsplit


def safe_redirect_target(rd: str | None, cookie_domain: str) -> str:
    if not rd:
        return "/"

    parsed = urlsplit(rd)

    # No scheme and no host: either a plain path ("/x") or a scheme-relative
    # oddity. Reject "//host" (netloc set, no scheme) here rather than
    # falling through — urlsplit gives it an empty scheme but a real netloc.
    if not parsed.scheme and not parsed.netloc:
        if rd.startswith("/") and not rd.startswith("//"):
            return rd
        return "/"

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "/"

    host = (parsed.hostname or "").lower()
    bare_domain = cookie_domain.lstrip(".").lower()
    suffix = "." + bare_domain

    if host == bare_domain or host.endswith(suffix):
        return rd

    return "/"
