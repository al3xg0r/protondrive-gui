"""On-disk cache of folder listings, so a folder can be shown instantly from
the last time it was loaded while the live listing is fetched in the
background. Lives in the user's cache directory with owner-only permissions,
is cleared on logout, and is dropped for My files after any change."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .cli import DriveItem


class ListingCache:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, key: str):
        """Returns (items, saved_at_epoch) or None."""
        entry = self._data.get(key)
        if not isinstance(entry, dict):
            return None
        try:
            items = [
                DriveItem(
                    name=d["name"],
                    is_folder=bool(d["is_folder"]),
                    size=d.get("size"),
                    modified=d.get("modified"),
                    raw=d.get("raw") or {},
                )
                for d in entry["items"]
            ]
            return items, float(entry["saved"])
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, key: str, items: list[DriveItem]):
        self._data[key] = {
            "saved": time.time(),
            "items": [
                {
                    "name": i.name,
                    "is_folder": i.is_folder,
                    "size": i.size,
                    "modified": i.modified,
                    "raw": i.raw,
                }
                for i in items
            ],
        }
        self._save()

    def drop_prefix(self, prefix: str):
        before = len(self._data)
        self._data = {k: v for k, v in self._data.items() if not k.startswith(prefix)}
        if len(self._data) != before:
            self._save()

    def clear(self):
        self._data = {}
        try:
            self.path.unlink()
        except OSError:
            pass

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh)
            os.replace(tmp, self.path)
        except OSError:
            pass  # cache is best-effort; the live listing still works
