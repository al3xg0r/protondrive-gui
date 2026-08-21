# Proton Drive GUI (unofficial)

A minimal desktop GUI wrapper around the official [Proton Drive CLI](https://proton.me/support/drive-cli).

> **Not affiliated with Proton AG.** This is a third-party client that shells out to
> the official `proton-drive` binary — it doesn't reimplement any Proton Drive
> protocol or touch your credentials directly.

## Status

Early / minimal. Currently supports:

- Browsing folders (double-click to open, "Up" to go back)
- Uploading files into the current folder
- Downloading selected files/folders to a local directory
- Triggering `auth login` (opens your browser)

Not yet implemented (see [Roadmap](#roadmap)): delete, rename, new folder, search,
sharing, drag & drop, upload/download progress bars, multi-select bulk actions,
packaging as an AppImage.

## Requirements

- Linux (developed/tested here; PySide6 is cross-platform so Windows/macOS likely work too, untested)
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
python -m protondrive_gui
```

Or, install it as a proper package:

```bash
pip install -e .
protondrive-gui
```

## A note on the JSON schema

The Proton Drive CLI supports a `--json` flag but Proton hasn't published one
single documented schema for its output. `protondrive_gui/cli.py` normalizes
a handful of common field-name variants (`name`/`Name`, `size`/`Size`, etc.).

If items show up with missing names/sizes on your CLI version, run:

```bash
proton-drive filesystem list / --json
```

...and compare the raw output to `ProtonDriveCLI._normalize_item()` in
`protondrive_gui/cli.py` — that's the only place that should need adjusting.
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

## Contributing

Issues and PRs welcome. The GUI layer (`main_window.py`) and the CLI wrapper
(`cli.py`) are kept separate on purpose — most new features only need changes
in one of the two.

## License

MIT — see [LICENSE](LICENSE).
