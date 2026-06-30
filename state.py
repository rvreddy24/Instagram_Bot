"""
state.py — persistent JSON state file (replaces Hermes memory).

All modules read/write a single state.json at the project root.
A file-level lock prevents race conditions if multiple processes ever run.
"""
import json
from filelock import FileLock
from config import STATE_FILE

_LOCK = FileLock(str(STATE_FILE) + ".lock")


def _read() -> dict:
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _write(data: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get(key: str, default=None):
    """Read a single key from state."""
    with _LOCK:
        return _read().get(key, default)


def set(key: str, value) -> None:
    """Write a single key to state."""
    with _LOCK:
        data = _read()
        data[key] = value
        _write(data)


def delete(key: str) -> None:
    """Remove a key from state."""
    with _LOCK:
        data = _read()
        data.pop(key, None)
        _write(data)


def get_all() -> dict:
    """Return the full state dict."""
    with _LOCK:
        return _read()


def update(updates: dict) -> None:
    """Merge multiple keys into state atomically."""
    with _LOCK:
        data = _read()
        data.update(updates)
        _write(data)
