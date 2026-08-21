#!/usr/bin/env bash
set -euo pipefail

# Installs a .desktop launcher for Proton Drive GUI into your
# application menu, so you can start it with a click (dock/menu/search)
# instead of a terminal.
#
# Usage:
#   ./scripts/install-desktop-entry.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="$PROJECT_DIR/.venv/bin"
DESKTOP_FILE="$HOME/.local/share/applications/protondrive-gui.desktop"

if [ ! -x "$VENV_BIN/protondrive-gui" ]; then
    echo "Couldn't find $VENV_BIN/protondrive-gui" >&2
    echo "Set up the project first:" >&2
    echo "  python -m venv .venv && source .venv/bin/activate && pip install -e ." >&2
    exit 1
fi

mkdir -p "$HOME/.local/share/applications"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Proton Drive GUI
Comment=Unofficial desktop client for Proton Drive
Exec=$VENV_BIN/protondrive-gui
Icon=$PROJECT_DIR/assets/icon.svg
Terminal=false
Categories=Utility;Network;FileTransfer;
StartupWMClass=protondrive-gui
EOF

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" || true
fi

echo "Installed: $DESKTOP_FILE"
echo "It should now show up in your application menu / launcher search."
echo "If it doesn't appear right away, try logging out and back in."
