"""Checks GitHub for the latest release. Only called from the About dialog,
and only that one request is made (no telemetry, no identifiers sent)."""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = "al3xg0r/protondrive-gui"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
LATEST_PAGE = f"https://github.com/{REPO}/releases/latest"
CLI_DOWNLOAD_PAGE = "https://proton.me/download/drive/cli/index.html"


def fetch_latest() -> tuple[str, str]:
    """Returns (latest version without the leading 'v', release page URL)."""
    request = urllib.request.Request(
        LATEST_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "protondrive-gui"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        data = json.load(response)
    tag = str(data.get("tag_name") or "")
    return tag.lstrip("v"), str(data.get("html_url") or LATEST_PAGE)


def _parse(version: str):
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    return tuple(int(part) for part in match.groups()) if match else None


def compare(current: str, latest: str) -> str:
    """'newer' if latest is ahead of current, 'same' or 'older' otherwise,
    'unknown' if either version can't be parsed."""
    cur, lat = _parse(current), _parse(latest)
    if cur is None or lat is None:
        return "unknown"
    if lat > cur:
        return "newer"
    return "same" if lat == cur else "older"


def _changelog_path() -> Path | None:
    """CHANGELOG.md next to the project when run from source, or bundled at the
    top of the frozen app (the AppImage and .deb builds add it)."""
    candidates = [Path(__file__).resolve().parent.parent / "CHANGELOG.md"]
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(getattr(sys, "_MEIPASS", ".")) / "CHANGELOG.md")
    return next((c for c in candidates if c.is_file()), None)


def latest_changelog_entry(current_version: str) -> tuple[str, list[str]] | None:
    """Returns (version, bullet points) for this version's changelog entry, or the
    newest entry if this version has none. None if the file can't be read."""
    path = _changelog_path()
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    entries = []
    for match in re.finditer(r"^## (\S+)\s*\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S):
        bullets = []
        for line in match.group(2).splitlines():
            if line.startswith("- "):
                bullets.append(line[2:].strip())
            elif bullets and line.strip() and line.startswith("  "):
                bullets[-1] += " " + line.strip()  # wrapped continuation line
        entries.append((match.group(1), bullets))
    if not entries:
        return None
    for version, bullets in entries:
        if version == current_version:
            return version, bullets
    return entries[0]
