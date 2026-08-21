# Proton Drive GUI (unofficial)

A minimal desktop GUI wrapper around the official [Proton Drive CLI](https://proton.me/support/drive-cli).

> **Not affiliated with Proton AG.** This is a third-party client that shells out to
> the official `proton-drive` binary — it doesn't reimplement any Proton Drive
> protocol or touch your credentials directly.

> **Linux only.** Built and tested on Linux. PySide6 is technically
> cross-platform, so it may run on Windows/macOS with some tweaks, but that's
> untested and unsupported for now.

## Status

Early / minimal. Currently supports:

- Browsing folders (double-click to open, "Back" to go back — disabled at the root)
- Uploading files into the current folder
- Downloading selected files/folders to a local directory
- Log in / log out (`auth login` opens your browser, `auth logout` is instant)
- Separate "My files" and "Photos" sections — Photos is a flat, most-recent-first
  timeline (no folders, no file size — that's just what the CLI exposes for it)

Not yet implemented (see [Roadmap](#roadmap)): delete, rename, new folder, search,
sharing, drag & drop, upload/download progress bars, multi-select bulk actions,
packaging as an AppImage.

## Requirements

- Linux
- Python 3.10+
- The official [Proton Drive CLI](https://proton.me/drive/download), installed and on your `PATH` as `proton-drive`

## Setup

```bash
# 1. Install and authenticate the official CLI first (one-time, from a terminal)
./proton-drive auth login

# 2. Clone this repo
git clone https://github.com/<your-username>/protondrive-gui.git
cd protondrive-gui

# 3. Install Python dependencies (a virtualenv is recommended)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Run
python -m gui
```

Or, install it as a proper package:

```bash
pip install -e .
protondrive-gui
```

## Desktop launcher (no terminal needed after setup)

Once you've done `pip install -e .` inside `.venv` (above), add a clickable
launcher to your application menu:

```bash
./scripts/install-desktop-entry.sh
```

This installs `~/.local/share/applications/protondrive-gui.desktop` pointing
at your venv, so "Proton Drive GUI" shows up in your app launcher/dock like
any other installed app.

## A note on the JSON schema

The Proton Drive CLI supports a `--json` flag but Proton hasn't published one
single documented schema for its output. `gui/cli.py` normalizes
a handful of common field-name variants (`name`/`Name`, `size`/`Size`, etc.).

If items show up with missing names/sizes on your CLI version, run:

```bash
proton-drive filesystem list / --json
```

...and compare the raw output to `ProtonDriveCLI._normalize_item()` in
`gui/cli.py` — that's the only place that should need adjusting.
Pull requests fixing this for real-world output are very welcome.

## Roadmap

- [ ] Delete / rename / new folder
- [ ] Drag & drop upload
- [ ] Upload/download progress (the CLI's stdout would need streaming, not just captured)
- [ ] Sharing (`sharing invite`, list existing shares)
- [ ] Search
- [ ] Remember last-visited folder / window state
- [ ] Packaging (AppImage / Flatpak)
- [ ] Dark/light theme following system settings
- [ ] Show logged-in account + storage quota (not currently possible — `proton-drive --help` exposes no account/whoami/quota command, only `auth login` / `auth logout`)
- [ ] One-shot installer (fetch CLI, install system deps, set up venv,
      install desktop entry) instead of today's multi-step manual setup

## Contributing

Issues and PRs welcome. The GUI layer (`gui/main_window.py`) and the CLI
wrapper (`gui/cli.py`) are kept separate on purpose — most new features only
need changes in one of the two.

## License

MIT — see [LICENSE](LICENSE).

---

Don't have a Proton account yet? This app (and Proton Drive itself) is free —
if you sign up via [my referral link](https://pr.tn/ref/H3Y6DHT7) it costs
you nothing extra and gives me a little credit. Totally optional.
