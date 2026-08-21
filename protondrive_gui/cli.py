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
from pathlib import Path
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
        """Runs `auth login`, which opens a browser for the user to authenticate.

        Deliberately not using --json / capture_output here: this is an
        interactive flow, and we want it to behave like it would in a
        normal terminal.
        """
        subprocess.run([self.binary_path, "auth", "login"], check=False)

    def is_authenticated(self) -> bool:
        """There's no documented `auth status` subcommand, so we probe
        with a cheap list call instead."""
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

        name = pick("name", "Name", "filename", "fileName", default="?")
        item_type = pick("type", "Type", default="")
        is_folder = pick("isFolder", "is_dir", "isDir", "folder", default=None)
        if is_folder is None:
            is_folder = str(item_type).lower() in ("folder", "dir", "directory")

        return DriveItem(
            name=name,
            is_folder=bool(is_folder),
            size=pick("size", "Size", "fileSize"),
            modified=pick("modified", "modifiedTime", "updatedAt", "mtime", "modifiedAt"),
            raw=raw,
        )
