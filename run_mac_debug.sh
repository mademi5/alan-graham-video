#!/usr/bin/env bash
# Run the built .app from Terminal and print crash output.
set -euo pipefail
cd "$(dirname "$0")"

APP="dist/Alan Graham Video Editor.app"
BIN="$APP/Contents/MacOS/Alan Graham Video Editor"

if [[ ! -f "$BIN" ]]; then
  echo "App binary not found. Run ./build_mac.sh first."
  exit 1
fi

echo "Removing quarantine flag (if any)..."
xattr -cr "$APP" 2>/dev/null || true

echo ""
echo "Launching from Terminal (errors will appear below)..."
echo "----------------------------------------"
"$BIN"
EXIT=$?
echo "----------------------------------------"
echo "Exit code: $EXIT"

if [[ $EXIT -ne 0 ]]; then
  echo ""
  echo "If you see Tcl/Tk or _tkinter errors above, rebuild after git pull."
fi
