# Installing

Pick the option that fits your system. All of them need the official
Proton Drive CLI (`proton-drive`) at runtime; the GUI is only a window on top
of it. See [CLI notes](cli.md).

## .deb package (Debian, Ubuntu, Linux Mint)

Download `protondrive-gui_<version>_amd64.deb` (or `arm64`) from the
[Releases page](https://github.com/al3xg0r/protondrive-gui/releases) and open
it with your software installer, or from a terminal:

```bash
sudo apt install ./protondrive-gui_<version>_amd64.deb
```

`apt` installs the system libraries the app needs. The package contains the
app with its own Python and PySide6, so it doesn't depend on the PySide6
version in your distribution. It adds a `protondrive-gui` command, an app-menu
entry and an icon.

**The official CLI is installed too.** During installation the package
downloads `proton-drive` from proton.me and checks it against Proton's published
SHA-512 checksum. It needs internet access for that. If the CLI is already on
your system it's left alone. If the download, the checksum or the network
fails, the app still installs and the message says where to get the CLI from
(<https://proton.me/drive/download>).

- Remove it with `sudo apt remove protondrive-gui`. The CLI and your settings
  (`~/.config/protondrive-gui`) and cache (`~/.cache/protondrive-gui`) are kept.
- `sudo apt purge protondrive-gui` also removes the CLI, but only if this
  package installed it.
- Built on Ubuntu 22.04, so it needs a system at least that recent (Ubuntu
  22.04, Debian 12, Linux Mint 21 or newer). The package declares the glibc
  version it needs, and `apt` refuses to install it on an older system.
- There is no apt repository, so `apt upgrade` won't update it. Install the
  newer `.deb` yourself. The About dialog tells you when a newer version is out.

To build it yourself on Debian, Ubuntu or Mint, run `./build-deb.sh` (needs
`python3`, `pip` and `dpkg-deb`). Set `DEB_MAINTAINER="Name <you@example.com>"`
to change the contact in the package metadata. The result is
`dist/protondrive-gui_<version>_<arch>.deb`.

## AppImage (any Linux)

Download `ProtonDriveGUI-x86_64.AppImage` (or `ProtonDriveGUI-aarch64.AppImage`)
from the [latest release](https://github.com/al3xg0r/protondrive-gui/releases/latest),
then:

```bash
chmod +x ProtonDriveGUI-x86_64.AppImage
./ProtonDriveGUI-x86_64.AppImage
```

It contains the GUI but not the CLI, so the CLI must still be installed and on
your `PATH`.

To build it yourself, run `./build-appimage.sh` (needs `python3`, `pip` and
`curl`; it downloads `appimagetool` the first time).

## From source

`install.sh` does everything in one go: installs the system packages it needs
(asks for `sudo` once), downloads and checks the official CLI into
`~/.local/bin`, sets up a Python environment in the project folder, and adds a
desktop launcher. It's safe to re-run.

```bash
git clone https://github.com/al3xg0r/protondrive-gui.git
cd protondrive-gui
./install.sh
proton-drive auth login   # one-time login, opens your browser
```

Then start **Proton Drive GUI** from your application menu.

Manual setup, if you'd rather do it yourself:

```bash
# 1. Install and log in to the official CLI first
proton-drive auth login

# 2. Python dependencies (a virtualenv is recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Run
python -m gui
```

To add only the app-menu launcher to an existing setup:
`./scripts/install-desktop-entry.sh`.

Requirements: Linux and Python 3.10 or newer.
