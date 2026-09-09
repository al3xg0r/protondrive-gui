#!/usr/bin/env bash
set -euo pipefail

# Builds a self-contained AppImage for Proton Drive GUI.
#
# This packages only the GUI itself (Python + PySide6, frozen with
# PyInstaller) — NOT the official proton-drive CLI. The AppImage still
# expects to find `proton-drive` on PATH at runtime, same as every other
# install method here (run ./install.sh first, or install the CLI
# yourself from https://proton.me/drive/download).
#
# Output: dist/ProtonDriveGUI-<arch>.AppImage
#
# Requirements: python3, pip, curl. Only tested on x86_64/aarch64 Linux.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$PROJECT_DIR/build-appimage"
APPDIR="$BUILD_DIR/AppDir"
ARCH="$(uname -m)"

c_bold=$'\033[1m'; c_reset=$'\033[0m'
say() { echo "${c_bold}==>${c_reset} $*"; }

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }

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
pyinstaller \
    --noconfirm \
    --windowed \
    --name protondrive-gui \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work" \
    --specpath "$BUILD_DIR" \
    "$PROJECT_DIR/pyinstaller_entry.py"

say "Assembling the AppDir"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -r "$BUILD_DIR/dist/protondrive-gui/." "$APPDIR/usr/bin/"
cp "$PROJECT_DIR/assets/icon.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/protondrive-gui.svg"
cp "$APPDIR/usr/share/icons/hicolor/scalable/apps/protondrive-gui.svg" "$APPDIR/protondrive-gui.svg"

cat > "$APPDIR/usr/share/applications/protondrive-gui.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Proton Drive GUI
Comment=Unofficial desktop client for Proton Drive
Exec=protondrive-gui
Icon=protondrive-gui
Terminal=false
Categories=Utility;Network;FileTransfer;
EOF
cp "$APPDIR/usr/share/applications/protondrive-gui.desktop" "$APPDIR/protondrive-gui.desktop"

cat > "$APPDIR/AppRun" << 'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
export LD_LIBRARY_PATH="$HERE/usr/bin:${LD_LIBRARY_PATH:-}"
exec "$HERE/usr/bin/protondrive-gui" "$@"
EOF
chmod +x "$APPDIR/AppRun"

say "Fetching appimagetool (cached in $BUILD_DIR after the first run)"
APPIMAGETOOL="$BUILD_DIR/appimagetool"
if [ ! -x "$APPIMAGETOOL" ]; then
    curl -fSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

say "Building the AppImage"
mkdir -p "$PROJECT_DIR/dist"
# --appimage-extract-and-run avoids needing FUSE (not always available,
# e.g. in containers/CI), which appimagetool itself would otherwise need
# since it's distributed as an AppImage too.
"$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" \
    "$PROJECT_DIR/dist/ProtonDriveGUI-${ARCH}.AppImage"

deactivate

echo
say "Done: dist/ProtonDriveGUI-${ARCH}.AppImage"
echo "Still requires the official proton-drive CLI on PATH at runtime —"
echo "this AppImage only bundles the GUI itself, same as every other install method here."
