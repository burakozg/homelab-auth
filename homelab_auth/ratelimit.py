"""Per-IP throttle for login attempts.

Ported from shortlist's ``api/auth.py``, which throttles a bad ``X-API-Key``
header the same way — this fleet's admin-auth modules all do a per-IP failure
count over an in-memory window. Here it protects the login *form* instead of
an API-key header, but the shape (and the reasoning) is identical: this
service listens on the LAN with nothing else in front of it, so one
compromised device is enough to sit and guess a password, and the counter is
deliberately in memory so an unauthenticated caller can't make the process do
real work (a database write, a disk flush) merely by being throttled.
"""

from __future__ import annotations

import time
from collections import OrderedDict

#: Failures from one address before it is made to wait.
MAX_FAILURES = 10

#: How long failures are remembered, and how long a throttled address waits.
WINDOW_S = 300

#: Addresses tracked at once. Bounded because the key is chosen by whoever is
#: connecting — unbounded, a spray of forged source addresses would grow it
#: without limit. Oldest is evicted first.
MAX_TRACKED = 1024

#: address -> the times it failed, most recent last.
_failures: OrderedDict[str, list[float]] = OrderedDict()


def _recent(address: str, now: float) -> list[float]:
    """Failures still inside the window, pruned in place."""
    times = [t for t in _failures.get(address, []) if now - t < WINDOW_S]
    if times:
        _failures[address] = times
        _failures.move_to_end(address)
    else:
        _failures.pop(address, None)
    return times


def is_throttled(address: str) -> bool:
    return len(_recent(address, time.monotonic())) >= MAX_FAILURES


def record_failure(address: str) -> None:
    now = time.monotonic()
    times = _recent(address, now)
    times.append(now)
    _failures[address] = times
    _failures.move_to_end(address)
    while len(_failures) > MAX_TRACKED:
        _failures.popitem(last=False)


def record_success(address: str) -> None:
    """A correct login clears the address's history.

    Someone who mistyped their password twice and then got it right is not
    mid-attack, and shouldn't meet a wait later because of it.
    """
    _failures.pop(address, None)


def reset_throttle() -> None:
    """Forget every recorded failure. For tests, and for a fresh process."""
    _failures.clear()
