"""Per-folder colours, stored only on this computer and keyed by the folder's
node id (uid), so they survive renames and moves. The CLI has no way to set a
folder colour, so these are not visible in the web app or on other devices."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Name -> hex. "Default" is represented by no entry at all.
FOLDER_COLORS: dict[str, str] = {
    "red": "#e5534b",
    "orange": "#e8833a",
    "yellow": "#e8c53a",
    "green": "#3fa86e",
    "blue": "#4f9ce8",
    "purple": "#9b6fe0",
    "pink": "#e06fb0",
    "grey": "#8a8f98",
}


class FolderColorStore:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and v in FOLDER_COLORS}

    def get(self, uid: str | None) -> str | None:
        return self._data.get(uid) if uid else None

    def set(self, uid: str, name: str | None):
        if name is None:
            self._data.pop(uid, None)
        else:
            self._data[uid] = name
        self._save()

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh)
            os.replace(tmp, self.path)
        except OSError:
            pass  # colours are a convenience; failing to save must not break the app
