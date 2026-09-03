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
- Uploading files into the current folder — via the toolbar button or by
  dragging files onto the window
- Downloading selected files/folders to a local directory
- Upload/download progress bar (best-effort — scrapes the CLI's live spinner
  output since there's no `--json` progress format; see caveat in Roadmap)
- Delete key moves the selected item(s) in "My files" to Trash (confirms first)
- New folder, rename, and move-to-Trash (right-click a row) — "My files" only for now
- Browse Trash, restore or permanently delete individual items (right-click),
  and Empty Trash (only shown while browsing Trash; both confirm first, since
  they're irreversible)
- Breadcrumb trail showing where you are, click any segment to jump back
- Log in / log out (`auth login` opens your browser, `auth logout` is instant)
- Sidebar sections: My files, Photos (flat, most-recent-first timeline — no
  folders, no file size, just what the CLI exposes for it), Trash, Shared by
  me, Shared with me (the last two are new and only lightly tested — right-click
  actions are intentionally disabled there until confirmed safe)
- List view and grid/tile view, switchable from the toolbar

Not yet implemented (see [Roadmap](#roadmap)): search, sharing management
(invite/remove/set-url), multi-select bulk actions, packaging as an AppImage.

## Requirements

- Linux
- Python 3.10+
- The official [Proton Drive CLI](https://proton.me/drive/download), installed and on your `PATH` as `proton-drive`

## Setup

### Quick start (recommended)

One script does everything: installs system packages, downloads and verifies
the official CLI, sets up the Python environment, and adds a desktop
launcher.

```bash
git clone https://github.com/<your-username>/protondrive-gui.git
cd protondrive-gui
./install.sh
```

It only asks for `sudo` once, to install system packages (`libxcb-cursor0`
for the GUI; `libsecret` and `dbus-x11`, which the official CLI itself needs
to store your login session). Everything else stays local to your user
account or this folder. Safe to re-run any time — it skips whatever's
already done.

Once it finishes:

```bash
proton-drive auth login   # one-time login, opens your browser
```

Then launch **Proton Drive GUI** from your application menu.

### Manual setup

If you'd rather do it yourself, or `install.sh` doesn't fit your distro:

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

### Desktop launcher only

If you already have the CLI and a venv set up and just want the app-menu
launcher:

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

- [x] ~~Delete key shortcut~~ — moves the selection to Trash in My files, with confirmation
- [x] ~~List/grid view toggle~~ — in the top toolbar
- [x] ~~Shared by me / Shared with me~~ — added as sidebar sections; listing
      reuses the same `filesystem list` call as My files/Trash (an educated
      guess, not confirmed against real shared content yet — please report
      back if browsing them errors or shows something unexpected). Rename,
      delete, and Restore are deliberately **not** enabled there yet — those
      likely need different verbs (leave/unshare) for content you don't own,
      and guessing wrong risked doing the wrong thing to someone else's files
- [ ] Sharing management itself — `sharing invite`, `sharing status`,
      `sharing set-url`, accepting/rejecting invitations — none of this is
      wired up yet, only browsing shared content
- [x] ~~Permanent delete~~ — Empty Trash (`filesystem empty-trash`) and
      per-item Delete Permanently (`filesystem delete`, right-click in Trash)
      are both wired up, each confirms first since they're irreversible
- [x] ~~Breadcrumbs~~ — clickable trail above the file list
- [x] ~~Drag & drop upload~~ — drop files onto the window (folders aren't
      supported yet — drop the files inside them instead)
- [x] ~~Upload/download progress~~ — done, but fragile by nature: it scrapes the
      CLI's live spinner text (`NN.NN% name (size)`), which isn't a documented
      format and has no `--json` equivalent as of CLI 0.8.0. May silently stop
      working on a future CLI update.
- [ ] Sharing (`sharing invite`, list existing shares)
- [ ] Search
- [ ] Remember last-visited folder / window state
- [ ] Packaging (AppImage / Flatpak)
- [ ] Dark/light theme following system settings
- [ ] Show logged-in account + storage quota (not currently possible — `proton-drive --help` exposes no account/whoami/quota command, only `auth login` / `auth logout`)
- [x] ~~One-shot installer~~ — `./install.sh` fetches the CLI (with checksum
      verification), installs system deps, sets up the venv, and installs
      the desktop launcher

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
