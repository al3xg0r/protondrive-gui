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
# Requirements: python3, pip, curl, and the Qt xcb helper libraries
# (libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
#  libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libxkbcommon-x11-0),
# which are copied into the AppImage. Only tested on x86_64/aarch64 Linux.

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

# The Qt "xcb" platform plugin needs these helper libraries. Minimal systems
# (and the AppImage catalog's test environment) don't ship them, so without
# bundling the app can't open a window there. Core graphics libraries
# (libGL, libEGL, libxcb, libwayland-*, libdrm) are deliberately NOT bundled:
# they should come from the host to match its graphics driver.
say "Bundling Qt xcb helper libraries"
if [ -d "$APPDIR/usr/bin/_internal" ]; then
    LIBDIR="$APPDIR/usr/bin/_internal"   # PyInstaller >= 6
else
    LIBDIR="$APPDIR/usr/bin"             # PyInstaller < 6
fi
XCB_LIBS=(
    libxcb-cursor.so.0
    libxcb-icccm.so.4
    libxcb-image.so.0
    libxcb-keysyms.so.1
    libxcb-render-util.so.0
    libxcb-shape.so.0
    libxcb-xkb.so.1
    libxkbcommon-x11.so.0
)
LDCONFIG="$(command -v ldconfig || echo /sbin/ldconfig)"
for lib in "${XCB_LIBS[@]}"; do
    src="$("$LDCONFIG" -p | awk -v l="$lib" '$1 == l && /x86-64|AArch64/ { print $NF; exit }')"
    if [ -z "$src" ]; then
        echo "error: $lib not found on the build machine (install its package first)" >&2
        exit 1
    fi
    cp -L "$src" "$LIBDIR/"
done

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
export LD_LIBRARY_PATH="$HERE/usr/bin:$HERE/usr/bin/_internal:${LD_LIBRARY_PATH:-}"
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
