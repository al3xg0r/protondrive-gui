#!/usr/bin/env bash
set -euo pipefail

# One-shot setup for Proton Drive GUI + the official Proton Drive CLI.
#
# What this does, in order:
#   1. Installs system packages needed by the GUI (libxcb-cursor0) and by
#      the official CLI itself (libsecret, dbus-x11) via your distro's
#      package manager (asks for sudo once).
#   2. Downloads the official proton-drive CLI binary for your platform
#      from Proton's own release index, verifies its SHA-512 checksum,
#      and installs it to ~/.local/bin.
#   3. Sets up a Python virtualenv for this GUI and installs it into it.
#   4. Installs a desktop launcher (.desktop entry) so you can start the
#      app from your application menu instead of a terminal.
#
# Safe to re-run — every step skips work that's already done.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_BIN="$HOME/.local/bin"
CLI_INDEX_URL="https://proton.me/download/drive/cli/index.html"

c_bold=$'\033[1m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_red=$'\033[31m'; c_reset=$'\033[0m'
say()  { echo "${c_bold}==>${c_reset} $*"; }
ok()   { echo "${c_green}✓${c_reset} $*"; }
warn() { echo "${c_yellow}!${c_reset} $*"; }
die()  { echo "${c_red}✗ $*${c_reset}" >&2; exit 1; }

# -- 1. system packages -----------------------------------------------------

install_system_deps() {
    say "Checking system packages (GUI needs libxcb-cursor0; the official CLI needs libsecret + dbus-x11)"

    if command -v apt >/dev/null 2>&1; then
        local pkgs=(libxcb-cursor0 libsecret-1-0 dbus-x11 curl python3-venv)
        local missing=()
        for p in "${pkgs[@]}"; do
            dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
        done
        if [ ${#missing[@]} -eq 0 ]; then
            ok "All system packages already installed"
        else
            say "Installing: ${missing[*]} (needs sudo)"
            sudo apt update
            sudo apt install -y "${missing[@]}"
        fi
    elif command -v dnf >/dev/null 2>&1; then
        say "Installing (dnf will skip anything already present; needs sudo)"
        sudo dnf install -y xcb-util-cursor libsecret dbus-x11 curl python3
    elif command -v pacman >/dev/null 2>&1; then
        say "Installing (pacman will skip anything already present; needs sudo)"
        sudo pacman -S --needed --noconfirm xcb-util-cursor libsecret dbus curl python
    else
        warn "Unrecognized package manager — install these yourself if the app fails to start:"
        warn "  GUI: an xcb-cursor package (e.g. libxcb-cursor0)"
        warn "  CLI: libsecret and a D-Bus session (e.g. dbus-x11)"
    fi
}

# -- 2. proton-drive CLI ------------------------------------------------------

detect_platform() {
    local os arch suffix=""
    os="$(uname -s)"
    arch="$(uname -m)"
    [ "$os" = "Linux" ] || die "This installer is Linux-only (detected: $os). See proton.me/drive/download for other platforms."

    if command -v apk >/dev/null 2>&1 || { [ -f /etc/os-release ] && grep -qi alpine /etc/os-release; }; then
        suffix="-musl"
    fi

    case "$arch" in
        x86_64|amd64) echo "linux-x64${suffix}" ;;
        aarch64|arm64) echo "linux-arm64${suffix}" ;;
        *) die "Unsupported CPU architecture: $arch" ;;
    esac
}

fetch_release_row() {
    # $1: platform key in the table, e.g. "linux/x64"
    curl -fsSL "$CLI_INDEX_URL" | grep -F "| $1 "
}

download_cli_for_platform() {
    # $1: platform key with a slash, e.g. "linux/x64"
    local platform="$1" row url checksum tmpfile actual
    row="$(fetch_release_row "$platform")"
    [ -n "$row" ] || die "Couldn't find '$platform' on Proton's release index — check $CLI_INDEX_URL manually."

    url="$(echo "$row" | grep -oP '(?<=<)https://[^>]+(?=>)')"
    checksum="$(echo "$row" | grep -oP '(?<=`)[a-f0-9]{128}(?=`)')"
    [ -n "$url" ] && [ -n "$checksum" ] || die "Couldn't parse the release index — its format may have changed."

    say "Downloading proton-drive ($platform) from proton.me \u2026"
    tmpfile="$(mktemp)"
    curl -fSL --progress-bar -o "$tmpfile" "$url"

    say "Verifying SHA-512 checksum \u2026"
    actual="$(sha512sum "$tmpfile" | awk '{print $1}')"
    if [ "$actual" != "$checksum" ]; then
        rm -f "$tmpfile"
        die "Checksum mismatch! Expected $checksum, got $actual. Refusing to install a corrupted/tampered download."
    fi
    ok "Checksum verified"

    mkdir -p "$LOCAL_BIN"
    chmod +x "$tmpfile"
    mv "$tmpfile" "$LOCAL_BIN/proton-drive"
}

install_cli() {
    if command -v proton-drive >/dev/null 2>&1; then
        ok "proton-drive already on PATH ($(command -v proton-drive)) — skipping download"
        return
    fi
    if [ -x "$LOCAL_BIN/proton-drive" ]; then
        ok "proton-drive already installed at $LOCAL_BIN/proton-drive — skipping download"
    else
        local plat
        plat="$(detect_platform)"
        download_cli_for_platform "${plat/-/\/}"

        # Some x64 CPUs (older/embedded, no AVX2) crash the default build
        # with "Illegal instruction" (exit code 132). If that happens,
        # transparently retry with the baseline build instead of leaving
        # the user to figure it out — this exact problem has come up
        # during testing.
        if [ "$plat" = "linux-x64" ]; then
            set +e
            "$LOCAL_BIN/proton-drive" --help >/dev/null 2>&1
            local code=$?
            set -e
            if [ "$code" -eq 132 ] || [ "$code" -eq 133 ]; then
                warn "Default build crashed (Illegal instruction) — falling back to x64-baseline"
                download_cli_for_platform "linux/x64-baseline"
            fi
        fi
    fi

    case ":$PATH:" in
        *":$LOCAL_BIN:"*) ;;
        *)
            warn "$LOCAL_BIN isn't on your PATH yet."
            warn "Add this to ~/.bashrc (or your shell's equivalent) and restart your terminal:"
            warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            ;;
    esac
}

# -- 3. python env for the GUI -----------------------------------------------

setup_python_env() {
    say "Setting up the Python environment for the GUI"
    cd "$PROJECT_DIR"
    if [ ! -d .venv ]; then
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -e .
    deactivate
    ok "GUI installed into $PROJECT_DIR/.venv"
}

# -- 4. desktop launcher -------------------------------------------------------

install_launcher() {
    say "Installing the desktop launcher"
    "$PROJECT_DIR/scripts/install-desktop-entry.sh"
}

# -- main ---------------------------------------------------------------------

main() {
    say "Proton Drive GUI — one-shot setup"
    install_system_deps
    install_cli
    setup_python_env
    install_launcher

    echo
    ok "All done!"
    echo
    if ! command -v proton-drive >/dev/null 2>&1 && [ ! -x "$LOCAL_BIN/proton-drive" ]; then
        : # already died earlier if this failed
    elif command -v proton-drive >/dev/null 2>&1; then
        say "Next: authenticate once — 'proton-drive auth login'"
    else
        say "Next: authenticate once — '$LOCAL_BIN/proton-drive auth login'"
    fi
    say "Then launch 'Proton Drive GUI' from your application menu, or run: $PROJECT_DIR/.venv/bin/protondrive-gui"
}

main "$@"
