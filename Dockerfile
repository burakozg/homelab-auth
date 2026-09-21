FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# uv itself, not a pip install of it — the image ships pinned to a known uv
# release rather than whatever pip resolves that day.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# tini as PID 1 so a SIGTERM actually reaches uvicorn and its in-flight
# requests get a clean shutdown instead of a hard kill.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- dependency layer --------------------------------------------------------
# `--frozen` is the point: uv.lock is the lockfile, and a resolve that would
# change it fails the build instead of quietly shipping different versions than
# were tested. Separated from the application layer so an app-only change does
# not invalidate Docker's dependency cache. --no-install-project because the
# source has not been copied yet.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# --- application layer -------------------------------------------------------
COPY homelab_auth ./homelab_auth
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# Non-root. The rootfs is read-only at runtime (docker-compose.nas.yml) — this
# service has no state of its own (no database, no files), so unlike its
# siblings it needs no writable bind mount at all, only /tmp.
RUN groupadd -g 10001 appuser && useradd -g appuser -u 10001 appuser
USER appuser

EXPOSE 8098

# Unauthenticated by design: this is what the deploy probe and Docker read,
# and a health endpoint that needs a session cookie reports "unhealthy"
# exactly when login itself is broken, which is the one time you need it to
# still answer. See homelab_auth/main.py::healthz.
# start-period is generous because this NAS is memory-tight: a recreate under
# load has been measured taking minutes, and a short grace period reports a
# container that is merely starting as unhealthy.
HEALTHCHECK --interval=60s --timeout=10s --start-period=300s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8098/healthz', timeout=8).status==200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["homelab-auth"]
