"""
Thin wrapper around the official Proton Drive CLI (``proton-drive``).

This module shells out to the ``proton-drive`` binary and parses its
JSON output (the CLI supports a global ``--json`` flag). Proton hasn't
published one single documented JSON schema, so :func:`ProtonDriveCLI._normalize_item`
below tries a handful of common field-name variants defensively.

If your installed CLI version uses different field names than what's
listed here, run:

    proton-drive filesystem list / --json

...and compare the raw output to the ``pick(...)`` calls below — this
is the only place you should need to edit.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Optional


class ProtonDriveError(RuntimeError):
    """Raised when the proton-drive CLI returns a non-zero exit code
    or its output can't be parsed."""

    def __init__(self, message: str, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class ProtonDriveNotFoundError(RuntimeError):
    """Raised when the proton-drive binary can't be located."""


@dataclass
class DriveItem:
    name: str
    is_folder: bool
    size: Optional[int] = None
    modified: Optional[str] = None
    raw: dict = field(default_factory=dict)


def find_binary(custom_path: Optional[str] = None) -> str:
    """Locate the proton-drive executable, or raise ProtonDriveNotFoundError."""
    if custom_path:
        p = Path(custom_path).expanduser()
        if p.is_file():
            return str(p)
        raise ProtonDriveNotFoundError(f"proton-drive not found at: {custom_path}")

    for name in ("proton-drive", "proton-drive.exe"):
        found = shutil.which(name)
        if found:
            return found

    raise ProtonDriveNotFoundError(
        "Couldn't find the 'proton-drive' executable on your PATH.\n\n"
        "Download it from https://proton.me/drive/download, make sure it's "
        "executable and reachable on PATH (or set a custom path in Settings)."
    )


class ProtonDriveCLI:
    """Synchronous wrapper around the proton-drive binary.

    Every method here blocks on a subprocess call — always invoke these
    from a background thread (see gui/workers.py), never from the Qt
    main/GUI thread, or the UI will freeze.
    """

    def __init__(self, binary_path: Optional[str] = None):
        self.binary_path = find_binary(binary_path)

    # -- low level ---------------------------------------------------------

    def _run(
        self,
        args: list[str],
        json_output: bool = True,
        timeout: Optional[int] = None,
    ) -> Any:
        cmd = [self.binary_path, *args]
        if json_output:
            cmd.append("--json")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                # Explicitly close stdin: if the CLI ever prompts for
                # interactive confirmation (observed: `auth logout` can
                # hang waiting on input that a GUI can never provide),
                # this makes it hit EOF immediately instead of blocking
                # forever. The timeout above is a second safety net.
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as e:
            raise ProtonDriveNotFoundError(str(e)) from e
        except subprocess.TimeoutExpired as e:
            raise ProtonDriveError(f"Command timed out: {' '.join(cmd)}") from e

        if result.returncode != 0:
            raise ProtonDriveError(
                f"'{' '.join(cmd)}' failed (exit {result.returncode}):\n{result.stderr.strip()}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        if not json_output:
            return result.stdout

        stdout = result.stdout.strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            raise ProtonDriveError(
                f"Couldn't parse JSON output from: {' '.join(cmd)}\n{e}",
                stdout=result.stdout,
                stderr=result.stderr,
            ) from e

    # -- auth ---------------------------------------------------------------

    def auth_login(self) -> None:
        """Runs `auth login`, which opens a browser for the user to
        authenticate. stdin is closed (like every other call) so a launch
        via a .desktop icon — which may hand the process a broken/closed
        stdin rather than a real terminal — can't cause a silent hang; a
        generous timeout is a second safety net for a stuck flow."""
        try:
            subprocess.run(
                [self.binary_path, "auth", "login"],
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=300,
            )
        except subprocess.TimeoutExpired as e:
            raise ProtonDriveError(
                "Login timed out after 5 minutes. Try running "
                "'proton-drive auth login' directly from a terminal instead."
            ) from e

    def auth_logout(self) -> None:
        """Runs `auth logout`. Confirmed via `proton-drive --help` — this
        one isn't a browser flow, so it's safe to capture normally."""
        self._run(["auth", "logout"], json_output=False)

    def is_authenticated(self) -> bool:
        """`proton-drive --help` lists no `auth status`/`whoami` command at
        all, so we probe with a cheap list call instead. This also means
        there's currently no way to fetch the account name or storage
        quota through this CLI — only a yes/no logged-in signal."""
        try:
            self.list_dir("/")
            return True
        except ProtonDriveError:
            return False

    # -- filesystem ----------------------------------------------------------

    def list_dir(self, path: str) -> list[DriveItem]:
        data = self._run(["filesystem", "list", path])
        return [self._normalize_item(raw) for raw in self._extract_items(data)]

    def upload(self, local_paths: list[str], remote_dir: str) -> None:
        self._run(["filesystem", "upload", *local_paths, remote_dir], json_output=False)

    def download(self, remote_path: str, local_dir: str) -> None:
        self._run(["filesystem", "download", remote_path, local_dir], json_output=False)

    # -- photos ---------------------------------------------------------------
    #
    # Confirmed: "filesystem list /photos" fails outright ("Path type
    # photos is not supported") — Photos isn't part of the regular
    # filesystem tree at all, it's a separate flat command namespace
    # (`photo timeline` / `photo upload` / `photo download`).
    #
    # `photo timeline --json` returns entries like:
    #   {"nodeUid": "...", "captureTime": "2026-08-01T05:24:49.000Z", "tags": []}
    # No filename, no size, no path — just an opaque id + capture date.
    # `photo download` accepts a node UID standing in for a name inside a
    # normal path, confirmed working as "/photos/<NODE-UID>".

    def list_photos(self) -> list[DriveItem]:
        data = self._run(["photo", "timeline"])
        items = data if isinstance(data, list) else []
        result = []
        for raw in items:
            capture = raw.get("captureTime")
            label = capture.replace("T", " ").replace(".000Z", "") if capture else raw.get(
                "nodeUid", "?"
            )
            result.append(
                DriveItem(name=label, is_folder=False, size=None, modified=capture, raw=raw)
            )
        return result

    def photo_upload(self, local_paths: list[str]) -> None:
        self._run(["photo", "upload", *local_paths], json_output=False)

    def photo_download(self, node_uids: list[str], local_dir: str) -> None:
        # Node UIDs stand in for a name inside a normal path — confirmed
        # working as "/photos/<NODE-UID>".
        paths = [f"/photos/{uid}" for uid in node_uids]
        self._run(["photo", "download", *paths, local_dir], json_output=False)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _extract_items(data: Any) -> list[dict]:
        """The list command may return a bare JSON array or a dict wrapping one."""
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "entries", "files", "data", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _normalize_item(raw: dict) -> DriveItem:
        def pick(*keys, default=None):
            for k in keys:
                if k in raw:
                    return raw[k]
            return default

        # Confirmed schema (CLI 0.x):
        #
        # Root listing "/": entries only carry a "path" field, e.g.
        # {"path": "/my-files"} — these are the virtual top-level sections
        # (my-files, devices, photos, shared-*, trash, albums), not real
        # files. The GUI skips this level entirely (see HOME_PATH in
        # main_window.py) so this branch mainly matters if someone calls
        # list_dir("/") directly.
        #
        # Listing inside e.g. "/my-files": real files/folders, where:
        #   - "name" is an object {"ok": true, "value": "..."} — wrapped
        #     because names are end-to-end encrypted and decrypted
        #     client-side; "ok" reflects whether decryption succeeded.
        #   - "type" is "folder" or "file".
        #   - folders carry no size field at all.
        #   - files carry "totalStorageSize" (encrypted size on Proton's
        #     servers, inflated by encryption overhead) and, nested under
        #     "activeRevision", "claimedSize" (the real original file size)
        #     and "storageSize". We prefer claimedSize since that's what a
        #     user actually expects to see.
        name = pick("name", "Name", "filename", "fileName")
        if isinstance(name, dict):
            name = name.get("value") if name.get("ok", True) else "<undecryptable name>"
        if name is None:
            path_value = pick("path", "Path", default="")
            name = PurePosixPath(str(path_value)).name or str(path_value) or "?"

        item_type = pick("type", "Type", default="")
        if item_type:
            is_folder = str(item_type).lower() == "folder"
        else:
            # No "type" at all -> a root-level virtual section.
            is_folder = "path" in raw or "Path" in raw

        active_revision = raw.get("activeRevision")
        if not isinstance(active_revision, dict):
            active_revision = {}

        size = pick("size", "Size", "fileSize")
        if size is None:
            size = active_revision.get("claimedSize")
        if size is None:
            size = pick("totalStorageSize")
        if size is None:
            size = active_revision.get("storageSize")

        modified = pick(
            "modificationTime", "modified", "modifiedTime", "updatedAt", "mtime", "modifiedAt"
        )

        return DriveItem(
            name=name,
            is_folder=bool(is_folder),
            size=size,
            modified=modified,
            raw=raw,
        )
