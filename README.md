# homelab-auth

One login for the homelab.

Before this, five of the NAS's self-hosted admin panels each gated
themselves with a bespoke shared-secret header — a per-app `X-API-Key` or
`X-Admin-Token` typed into a browser prompt or pasted into curl, with no
session, no login form, and no way to revoke just one visit. This service
replaces all of those with a single login: one username, one password, one
session cookie, checked by Traefik's `forwardAuth` middleware in front of
every app that opts in.

It is not a user-management system. There is exactly one admin account — no
registration, no OAuth, no per-app roles, no database of users. That's the
right size for a household admin logging into their own LAN.

## The three pieces, and why all three exist

```
                 DNS override (router DHCP)
                            |
                            v
 browser --Host: X.<domain>--> dnsmasq --*.{domain}--> Traefik --Host-based routing--> each app
                                            (everything          |
                                             else: real           +-- forwardAuth(GET /verify) --> homelab-auth
                                             internet DNS)                                              |
                                                                                                    200 / 302
```

**Why a DNS component (`dnsmasq/`) is needed at all**, not just Traefik and
this service: a session cookie is scoped by `Domain=`, and a cookie set for
one domain is only ever sent back to hosts under that *same* domain — it
cannot cross different IP-address origins the way it crosses subdomains of
one real domain. Every gated app therefore needs a hostname under one shared
domain (`AUTH_COOKIE_DOMAIN`), and something on the LAN has to answer DNS
queries for that domain — dnsmasq does that (wildcard `address=/<domain>/…`
pointing at Traefik's address), forwarding everything else upstream so
normal internet browsing on the same network is unaffected. Devices pick this
up via a DHCP override on the router (UniFi: Settings → Networks → your LAN →
DNS Server → point it at dnsmasq's address) — set on *every* network your
devices actually use, not just the one the NAS sits on, and a device usually
needs a fresh DHCP lease (Wi-Fi off/on) to pick up a changed DNS server.

**Why Traefik, not each app doing its own thing**: one place to attach
`forwardAuth`, one place the DNS wildcard needs to point at, and it already
existed on this NAS for other routing.

**Why this service exists separately from Traefik**: `forwardAuth` needs
something to call that actually knows about the one account and can render a
login form — Traefik has no concept of "log in," only "call this URL and act
on the status code."

## The `/verify` contract — and why it's 302, not 401

Traefik's `forwardAuth` middleware, on any *non-2xx* response from the auth
service, relays that response back to the client verbatim (status, headers,
body) rather than following it itself. A browser, however, only
**auto-follows a `Location` header on a 3xx status** — a `401` with a
`Location` header renders as a blocked page, going nowhere. So `/verify`
returns:

- **200** (empty body) if the request carries a valid, unexpired session
  cookie — forwardAuth lets the request through to the app.
- **302** if the cookie is missing, invalid, or expired — still non-2xx, so
  forwardAuth still denies it, but the `Location` header (pointing at this
  service's own `/login?rd=<the original URL>`) now actually makes the
  browser navigate there.

That `Location` must be an **absolute URL** naming this service's own
origin (`AUTH_LOGIN_URL`), not a relative `/login` — `request.url` inside the
handler is Traefik's *subrequest* to this service's own `/verify` path, not
the app the browser actually asked for. The real target comes from the
`X-Forwarded-Proto` / `X-Forwarded-Host` / `X-Forwarded-Uri` headers Traefik
attaches to that subrequest; a relative redirect would send the browser to
`<the-app-that-denied-it>/login`, which doesn't exist there.

Both of these were verified against a real deployment, not assumed — see
`_deny_redirect()` in `homelab_auth/main.py` and `tests/test_verify.py`.

## Config

All via environment variables (`.env` for local dev — copy from
`.env.example` — or, on the NAS, a file literally **not** named `.env`; see
the note on `docker-compose.nas.yml`'s `env_file:` for why):

| var | meaning | default |
|---|---|---|
| `AUTH_USERNAME` | the one admin username | `admin` |
| `AUTH_PASSWORD_HASH` | bcrypt hash of the admin password — **never the plaintext** | *(empty — login fails closed until set)* |
| `AUTH_SECRET_KEY` | signs the session JWT/cookie | *(empty — login fails closed until set)* |
| `AUTH_COOKIE_DOMAIN` | `Domain=` attribute on the session cookie, e.g. `.home.arpa`, so one login covers every subdomain under it | `.home.arpa` |
| `AUTH_SESSION_DAYS` | how long a session lasts | `30` |
| `AUTH_LOGIN_URL` | this service's own absolute origin (e.g. `http://auth.home.arpa`) — required for `/verify`'s redirect to point at the right place | *(empty — see below)* |

`AUTH_SECRET_KEY`, `AUTH_PASSWORD_HASH` and `AUTH_LOGIN_URL` are all required
in any real deployment (`Settings.configured` checks all three). Leaving any
unset doesn't crash the process (so `/healthz` still answers) — it just makes
every login attempt fail with 503 rather than ever accepting a request.
That's deliberate: unset secret material must never mean "open to everyone."

## Setting or changing the admin password

There's no web UI for this — it's one account, and the password lives only
as a bcrypt hash in `AUTH_PASSWORD_HASH`. To set or change it:

```bash
uv run python scripts/hash_password.py
```

It prompts for the password twice (never echoed, never taken as an argument
that could land in shell history) and prints the bcrypt hash to put in
`AUTH_PASSWORD_HASH`.

## Running it

```bash
uv sync
cp .env.example .env   # then fill in AUTH_SECRET_KEY, AUTH_PASSWORD_HASH, AUTH_LOGIN_URL
uv run homelab-auth     # http://127.0.0.1:8098
```

Tests:

```bash
uv run pytest
```

## Deploying to the NAS

Same pattern as this fleet's other projects — see `deploy.lib.sh` (vendored
byte-identically from `homelab/deploy.lib.sh`) and `docker-compose.nas.yml`,
which brings up **two** containers: this service, and `dnsmasq` (see above).

```bash
cp deploy.env.example .deploy.env   # fill in real NAS/LAN values, incl. HOMELAB_DOMAIN
./deploy           # build, ship, bring both containers up
./deploy check      # is it running, and reachable over the LAN
./deploy logs       # follow this service's log
```

The NAS-side secrets file is **not** named `.env` — `docker-compose.nas.yml`
names it `homelab-auth.env` deliberately, because Docker Compose auto-loads a
file literally named `.env` in the project directory for its *own* `${...}`
interpolation, independent of the `env_file:` directive — and that mangled a
bcrypt hash's `$2b$12$…` down to 6 characters in testing, with no error
beyond an easy-to-miss warning, even though nothing in the compose file
references that variable. If a secret value ever needs a literal `$`, escape
it as `$$` in that file, or compose's interpolation will eat it.

`.deploy.env` and `.env` are both gitignored — nothing in this repo carries a
real hostname, IP, or secret. See `deploy.env.example` and `.env.example` for
the full documented set of variables.

## What's actually gated today

Traefik's own config (`dynamic-config.yml` on the NAS, not tracked in this
repo) decides what's protected — this service only answers "is this session
valid." As deployed:

| app | what's gated | what stays open |
|---|---|---|
| shortlist | everything (`Host` only, no path split) | — |
| podcast-digest | everything, including `/admin` (`Host` only) | — |
| vault-ask | `/admin*` (`PathPrefix`) | `/chat`, `/query`, `/v1/*` — by design, no login for the daily-use chat surface |
| security-digest, news-digest | `/admin*` and `/run` (`PathPrefix` + exact `Path`) | `/status` — read by the homelab status collector and this fleet's own deploy health-probes |
| family_calendar | `admin.html` only, and only when reached via its `family-calendar.servers.zou` route specifically (`Host` + exact `Path`, plus an app-level check in its own `main.py` — see below) | everything else: `mobile.html`, `display.html`, `recipes.html`, and the API they share |

**family_calendar is the one real exception to "Traefik decides everything,"**
for a hardware reason: its physical Inky Frame e-ink display fetches
`/display-data` by a fixed raw LAN IP, with no DNS and no way to reconfigure
it remotely, so that backend can't drop its direct address the way every
other app here did. Its own Host-header check (`ALLOWED_HOSTS` /
`_host_allowed` in that repo) deliberately permits any IP-literal Host for
exactly that reason — which means `admin.html` would still be reachable
unauthenticated by raw IP regardless of anything Traefik does. That repo's
`main.py` therefore has its own narrower check (`ADMIN_HOST`) refusing to
serve `admin.html` at all unless the Host header is exactly this service's
gated hostname. Every other route, including the ones the Inky Frame and the
family's own phones use, is unaffected.

`taster` (its relay's PWA uses one bearer key for both daily capture and
admin, with no clean split) and `video-digest`/`clippings-topics` (no browser
admin surface at all) were deliberately left out of this project — see the
per-project audit that scoped it, not repeated here.

## Endpoints

| method | path | auth | purpose |
|---|---|---|---|
| `GET` | `/login` | none | login form; `?rd=` names where to go after success |
| `POST` | `/login` | rate-limited | verifies credentials, sets the session cookie |
| `POST` | `/logout` | none | clears the session cookie |
| `GET` | `/verify` | — | the Traefik forwardAuth gate; see above |
| `GET` | `/healthz` | none | always 200 if the process is up |

Login attempts are throttled per source IP (10 failures / 5 minutes,
in-memory, same shape as this fleet's other admin-auth throttles) — see
`homelab_auth/ratelimit.py`.

## Gotchas hit building this, worth not re-discovering

- **macvlan-to-macvlan container traffic on this NAS is not universally
  unreliable** — the homelab-wide docs warn it can fail outright, but the
  right response is to test the *actual pair*, not assume. Traefik→this
  service and Traefik→shortlist were both tested 5/5 reliable before
  deciding whether a shared bridge network was even necessary.
- **A container recreate can leave the switch/router's ARP cache stale even
  with a pinned MAC** — symptom: `Up`/healthy, but completely unreachable
  (curl times out, not even a TCP reset) immediately after. Self-heals the
  moment the container sends any outbound packet; `docker exec <container>
  <anything that opens an outbound connection>` forces it immediately rather
  than waiting it out.
- **`docker network connect` adds a network to a *running* container without
  restarting it** — used to attach Traefik (and, for family_calendar, the
  Caddy proxy) to the new `homelab-internal` bridge with zero disruption to
  what they were already serving.
