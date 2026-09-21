#!/usr/bin/env python3
"""Set or change the admin password.

There's no web-based account management here — deliberately, since this
service has exactly one account. This is how you set or change it: it prompts
for a password (never printed, never taken as an argv/env value that could
end up in shell history or `ps`), hashes it with bcrypt, and prints the value
to put in AUTH_PASSWORD_HASH.

Usage:
    uv run python scripts/hash_password.py
"""

from __future__ import annotations

import getpass
import sys

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def main() -> int:
    password = getpass.getpass("New admin password: ")
    if not password:
        print("Password must not be empty.", file=sys.stderr)
        return 1

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        return 1

    print()
    print("Put this in AUTH_PASSWORD_HASH (in .env, never in a tracked file):")
    print()
    print(pwd_context.hash(password))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
