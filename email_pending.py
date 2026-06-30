"""
Email pending — STEP 4: hold proposals between 'detected' and 'confirmed'.
Parked under a short token until a human confirms (commit) or rejects (discard).
In-memory on purpose: pending items are short-lived. Back it with a SQLite table
if you want them to survive a restart — nothing else would change.
"""
import secrets
import threading

_pending: dict[str, dict] = {}
_lock = threading.Lock()


def add(proposal: dict) -> str:
    token = secrets.token_urlsafe(8)
    with _lock:
        _pending[token] = proposal
    return token


def get(token: str) -> dict | None:
    with _lock:
        return _pending.get(token)


def pop(token: str) -> dict | None:
    with _lock:
        return _pending.pop(token, None)


def all_items() -> list[tuple[str, dict]]:
    with _lock:
        return list(_pending.items())