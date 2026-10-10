"""Checks GitHub for the latest release. Only called from the About dialog,
and only that one request is made (no telemetry, no identifiers sent)."""

from __future__ import annotations

import json
import re
import urllib.request

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
