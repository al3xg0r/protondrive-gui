#!/usr/bin/env bash
set -euo pipefail

# Builds a self-contained .deb for Debian, Ubuntu, Linux Mint and derivatives.
#
# The GUI (Python + PySide6) is frozen with PyInstaller and installed under
# /usr/lib/protondrive-gui, so it doesn't depend on the PySide6 version in the
# distribution's repositories. The system libraries it needs are declared in
# `Depends:`, so apt installs them. It does NOT include Proton's official
# `proton-drive` command-line client, which must be installed separately
# (https://proton.me/drive/download), same as with every other install method.
#
# Output: dist/protondrive-gui_<version>_<arch>.deb  (amd64 or arm64)
#
# Requirements: python3, pip, dpkg-deb, and the Qt xcb helper libraries
# (libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
#  libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libxkbcommon-x11-0) so the
# frozen app can be inspected while building.
#
# Set DEB_MAINTAINER="Your Name <you@example.com>" to change the contact in the
# package metadata. By default it points at the repository, since there is no
# dedicated support address.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$PROJECT_DIR/build-deb"
PKGROOT="$BUILD_DIR/pkg"
NAME="protondrive-gui"
HOMEPAGE="https://github.com/al3xg0r/protondrive-gui"
MAINTAINER="${DEB_MAINTAINER:-protondrive-gui contributors <$HOMEPAGE>}"

# System packages the frozen app needs at runtime, plus what the install step
# uses to download the official CLI (curl, ca-certificates).
#  - libxcb-cursor0 ... libxkbcommon-x11-0: helper libraries of Qt's "xcb"
#    platform plugin; minimal systems lack them and the window won't open.
#  - libsecret-1-0, dbus-x11: used by the official CLI to keep your login in
#    the system keyring.
DEPENDS="curl, ca-certificates, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-xkb1, libxkbcommon-x11-0, libsecret-1-0, dbus-x11"

c_bold=$'\033[1m'; c_reset=$'\033[0m'
say() { echo "${c_bold}==>${c_reset} $*"; }

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
command -v dpkg-deb >/dev/null 2>&1 || { echo "dpkg-deb is required (run this on Debian/Ubuntu/Mint)" >&2; exit 1; }

VERSION="$(python3 - "$PROJECT_DIR/gui/__init__.py" << 'PY'
import re, sys
print(re.search(r'__version__\s*=\s*"([^"]+)"', open(sys.argv[1]).read()).group(1))
PY
)"
ARCH="$(dpkg --print-architecture)"
OUT="$PROJECT_DIR/dist/${NAME}_${VERSION}_${ARCH}.deb"

say "Setting up a throwaway build environment"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
python3 -m venv "$BUILD_DIR/venv"
# shellcheck disable=SC1091
source "$BUILD_DIR/venv/bin/activate"
pip install --upgrade pip --quiet
pip install --quiet -e "$PROJECT_DIR"
pip install --quiet pyinstaller

say "Freezing the app with PyInstaller (this can take a few minutes)"
# assets/icon.svg is added so the running window can show its icon too.
pyinstaller \
    --noconfirm \
    --windowed \
    --name "$NAME" \
    --add-data "$PROJECT_DIR/assets/icon.svg:assets" \
    --add-data "$PROJECT_DIR/CHANGELOG.md:." \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work" \
    --specpath "$BUILD_DIR" \
    "$PROJECT_DIR/pyinstaller_entry.py"
deactivate

say "Assembling the package tree"
LIBDIR="$PKGROOT/usr/lib/$NAME"
install -d "$LIBDIR" "$PKGROOT/DEBIAN" "$PKGROOT/usr/bin" \
    "$PKGROOT/usr/share/applications" \
    "$PKGROOT/usr/share/icons/hicolor/scalable/apps" \
    "$PKGROOT/usr/share/doc/$NAME"
cp -r "$BUILD_DIR/dist/$NAME/." "$LIBDIR/"

# A small launcher rather than a symlink, so the frozen app always finds its
# own files next to the real executable.
cat > "$PKGROOT/usr/bin/$NAME" << LAUNCHER
#!/bin/sh
exec /usr/lib/$NAME/$NAME "\$@"
LAUNCHER
chmod 755 "$PKGROOT/usr/bin/$NAME"

# The oldest glibc this build can run on, read from the symbol versions the
# frozen files actually use. Declaring it lets apt refuse the package on a
# system that is too old, instead of installing something that won't start.
GLIBC_MIN="$(python3 - "$LIBDIR" << 'PY'
import os, re, subprocess, sys
best = (0, 0)
for folder, _, names in os.walk(sys.argv[1]):
    for name in names:
        path = os.path.join(folder, name)
        if not (name.endswith(".so") or ".so." in name or os.access(path, os.X_OK)):
            continue
        try:
            dump = subprocess.run(["objdump", "-T", path], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        for found in re.finditer(r"GLIBC_(\d+)\.(\d+)", dump):
            best = max(best, (int(found.group(1)), int(found.group(2))))
print(f"{best[0]}.{best[1]}" if best != (0, 0) else "")
PY
)"
if [ -n "$GLIBC_MIN" ]; then
    DEPENDS="libc6 (>= $GLIBC_MIN), $DEPENDS"
    say "Needs glibc $GLIBC_MIN or newer"
fi

install -m 644 "$PROJECT_DIR/assets/icon.svg" \
    "$PKGROOT/usr/share/icons/hicolor/scalable/apps/$NAME.svg"

cat > "$PKGROOT/usr/share/applications/$NAME.desktop" << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=Proton Drive GUI
Comment=Desktop client for Proton Drive
Exec=protondrive-gui
Icon=protondrive-gui
Terminal=false
Categories=Utility;Network;FileTransfer;
DESKTOP

{
    echo "Proton Drive GUI — $HOMEPAGE"
    echo
    cat "$PROJECT_DIR/LICENSE"
} > "$PKGROOT/usr/share/doc/$NAME/copyright"

# Readable by everyone, writable only by the owner (root once packed).
chmod -R u+rwX,go+rX,go-w "$PKGROOT"
chmod 755 "$PKGROOT/DEBIAN"

INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$PKGROOT" | cut -f1)"
# Install step: fetch the official CLI the same way install.sh does, and only
# keep it if its SHA-512 matches the one Proton publishes. Problems here only
# print a message: the app itself is installed either way.
cat > "$PKGROOT/DEBIAN/postinst" << 'POSTINST_EOF'
#!/bin/sh
set -e

CLI_BIN=/usr/local/bin/proton-drive
MARKER=/usr/share/protondrive-gui/cli-installed-by-package
INDEX_URL="${PD_CLI_INDEX_URL:-https://proton.me/download/drive/cli/index.html}"

if [ "$1" != "configure" ]; then
    exit 0
fi

say() { echo "protondrive-gui: $*"; }

if command -v proton-drive >/dev/null 2>&1; then
    say "proton-drive is already installed ($(command -v proton-drive)); leaving it alone."
    exit 0
fi

case "$(dpkg --print-architecture)" in
    amd64) platform=linux/x64 ;;
    arm64) platform=linux/arm64 ;;
    *)
        say "no proton-drive build for this architecture. Install it yourself from https://proton.me/drive/download"
        exit 0
        ;;
esac

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

if ! curl -fsSL --max-time 60 -o "$tmpdir/index.html" "$INDEX_URL"; then
    say "could not reach $INDEX_URL. Install proton-drive yourself from https://proton.me/drive/download"
    exit 0
fi

row="$(grep -F "| $platform " "$tmpdir/index.html" | head -n 1 || true)"
url="$(echo "$row" | grep -oP '(?<=<)https?://[^>]+(?=>)' || true)"
sum="$(echo "$row" | grep -oP '(?<=`)[a-f0-9]{128}(?=`)' || true)"
if [ -z "$url" ] || [ -z "$sum" ]; then
    say "could not read the proton-drive entry for $platform. Install it yourself from https://proton.me/drive/download"
    exit 0
fi

say "downloading proton-drive ($platform)"
if ! curl -fSL --max-time 300 -o "$tmpdir/proton-drive" "$url"; then
    say "the download failed. Install proton-drive yourself from https://proton.me/drive/download"
    exit 0
fi

actual="$(sha512sum "$tmpdir/proton-drive" | awk '{print $1}')"
if [ "$actual" != "$sum" ]; then
    say "CHECKSUM MISMATCH: the download was not installed. Expected $sum, got $actual."
    exit 0
fi

install -m 0755 "$tmpdir/proton-drive" "$CLI_BIN"
mkdir -p "$(dirname "$MARKER")"
: > "$MARKER"
say "installed proton-drive to $CLI_BIN (SHA-512 verified)"
exit 0
POSTINST_EOF

# Removing the package keeps the CLI (you may use it on its own). Purging
# removes the copy this package installed, and nothing else.
cat > "$PKGROOT/DEBIAN/postrm" << 'POSTRM_EOF'
#!/bin/sh
set -e

MARKER=/usr/share/protondrive-gui/cli-installed-by-package

if [ "$1" = "purge" ] && [ -f "$MARKER" ]; then
    rm -f /usr/local/bin/proton-drive "$MARKER"
    rmdir /usr/share/protondrive-gui 2>/dev/null || true
fi
exit 0
POSTRM_EOF
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/postrm"

cat > "$PKGROOT/DEBIAN/control" << CONTROL
Package: $NAME
Version: $VERSION
Architecture: $ARCH
Maintainer: $MAINTAINER
Installed-Size: $INSTALLED_SIZE
Depends: $DEPENDS
Section: utils
Priority: optional
Homepage: $HOMEPAGE
Bugs: $HOMEPAGE/issues
Description: Desktop client for Proton Drive
 Browse, upload, download and organise your Proton Drive files from a desktop
 window, built on top of Proton's official command-line client.
 .
 When installed, the package downloads Proton's command-line client
 (proton-drive) from proton.me and checks its SHA-512 against the published
 value. If the CLI is already installed it is left alone. If anything fails,
 the app still installs and the message says where to get the CLI.
 .
 Not affiliated with Proton AG.
CONTROL

say "Building the .deb"
mkdir -p "$PROJECT_DIR/dist"
dpkg-deb --root-owner-group -Zxz --build "$PKGROOT" "$OUT"

echo
dpkg-deb --info "$OUT" | sed -n '1,/^ Description/p'
echo
say "Done: dist/$(basename "$OUT")  ($(du -h "$OUT" | cut -f1))"
echo "Install with:  sudo apt install ./dist/$(basename "$OUT")"
echo "The package downloads the official proton-drive CLI during installation (needs internet)."
