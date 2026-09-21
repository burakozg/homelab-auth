"""homelab-auth: one login for the homelab.

A small central login service fronting Traefik's forwardAuth middleware. It
replaces N per-app bespoke shared-secret headers (the X-API-Key style each
app previously rolled on its own) with a single session cookie, scoped to a
shared cookie domain, that gates every app's admin panel from one place.

There is exactly one admin account — no registration, no user database, no
OAuth. See main.py for the endpoint contract and config.py for the env vars.
"""
