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