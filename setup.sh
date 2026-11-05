#!/usr/bin/env bash
# One-time setup for the LCLS drive migration kit, part 1 (run it as: ./gdm setup,
# which then runs install-claude-lcls.sh for Claude Code).
#
# Installs, inside this folder only:
#   .sandbox/bin/uv       runs the kit's Python tools and the SLAC search skills
#   .sandbox/python/      a private copy of Python, fetched by uv
#   .sandbox/bin/rclone   stores the Google logins
# The SLAC Confluence and Jira search skills already ship in .claude/skills/.
# Needs only curl and unzip, which every Mac has. Safe to run again.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX="$KIT/.sandbox"
mkdir -p "$SANDBOX/bin" "$SANDBOX/downloads" "$SANDBOX/config/rclone" "$SANDBOX/cache" \
         "$KIT/results"
chmod 700 "$SANDBOX/config"

# --- uv -------------------------------------------------------------------
if [ -x "$SANDBOX/bin/uv" ]; then
  echo "uv: already installed"
else
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh -o "$SANDBOX/downloads/uv-install.sh"
  env UV_INSTALL_DIR="$SANDBOX/bin" UV_NO_MODIFY_PATH=1 sh "$SANDBOX/downloads/uv-install.sh" >/dev/null 2>&1
fi

# --- rclone ---------------------------------------------------------------
if [ -x "$SANDBOX/bin/rclone" ]; then
  echo "rclone: already installed"
else
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64)  platform="osx-arm64" ;;
    Darwin-x86_64) platform="osx-amd64" ;;
    Linux-x86_64)  platform="linux-amd64" ;;
    Linux-aarch64) platform="linux-arm64" ;;
    *) echo "Unsupported computer: $(uname -s) $(uname -m)" >&2; exit 1 ;;
  esac
  echo "Installing rclone ($platform)..."
  curl -LsSf "https://downloads.rclone.org/rclone-current-$platform.zip" -o "$SANDBOX/downloads/rclone.zip"
  rm -rf "$SANDBOX/downloads/rclone-unzip"
  unzip -q "$SANDBOX/downloads/rclone.zip" -d "$SANDBOX/downloads/rclone-unzip"
  cp "$SANDBOX"/downloads/rclone-unzip/*/rclone "$SANDBOX/bin/rclone"
  chmod +x "$SANDBOX/bin/rclone"
fi

# --- Python (private copy inside .sandbox/python) ----------------------------
# Always the kit's own Python, never whatever else is on the computer
export UV_CACHE_DIR="$SANDBOX/cache/uv"
export UV_PYTHON_INSTALL_DIR="$SANDBOX/python"
export UV_PYTHON_PREFERENCE=only-managed
export UV_NO_CONFIG=1
echo "Python: making sure the kit's own copy is installed..."
"$SANDBOX/bin/uv" python install 3.12 >/dev/null 2>&1

echo
echo "Tools installed:"
echo "  $("$SANDBOX/bin/uv" --version)"
echo "  $("$SANDBOX/bin/rclone" version | head -1)"
echo "  Python $("$SANDBOX/bin/uv" run --no-project python -c 'import platform; print(platform.python_version())')"
