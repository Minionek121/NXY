"""
Lightweight JSON-backed storage layer.

This is intentionally simple (no external DB dependency) so the bot runs
out of the box. Every cog gets its own JSON file under /data. If you outgrow
this (large servers, high write volume), swap this module for SQLite/Postgres
without touching the cogs — they only call get/set/all.
"""
import json
import os
import threading

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)

_locks: dict[str, threading.Lock] = {}


class JSONStore:
    """A single JSON file treated as a dict-of-dicts key/value store."""

    def __init__(self, name: str):
        self.path = os.path.join(DATA_DIR, f"{name}.json")
        if name not in _locks:
            _locks[name] = threading.Lock()
        self._lock = _locks[name]
        if not os.path.exists(self.path):
            self._write({})

    def _read(self) -> dict:
        with self._lock:
            if not os.path.exists(self.path):
                return {}
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return {}

    def _write(self, data: dict):
        with self._lock:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2, default=str)

    def get(self, key, default=None):
        return self._read().get(str(key), default)

    def set(self, key, value):
        data = self._read()
        data[str(key)] = value
        self._write(data)

    def delete(self, key):
        data = self._read()
        data.pop(str(key), None)
        self._write(data)

    def all(self) -> dict:
        return self._read()

    def update(self, key, **kwargs):
        """Merge kwargs into the dict stored at key (creates it if missing)."""
        data = self._read()
        entry = data.get(str(key), {})
        entry.update(kwargs)
        data[str(key)] = entry
        self._write(data)
        return entry
