#!/usr/bin/env bash
# Build Alan Graham Video Editor for macOS (.app bundle)
# Run this script ON A MAC (Apple Silicon or Intel).

set -euo pipefail
cd "$(dirname "$0")"

echo "Installing build dependencies..."
python3 -m pip install -r requirements.txt -r build_requirements.txt --quiet

echo "Building Alan Graham Video Editor.app ..."
python3 -m PyInstaller --noconfirm --clean alan_graham_video_editor_mac.spec

APP_PATH="dist/Alan Graham Video Editor.app"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Build failed: $APP_PATH not found."
  exit 1
fi

# Ad-hoc sign so Gatekeeper is less likely to block local runs (optional).
if command -v codesign >/dev/null 2>&1; then
  echo "Applying ad-hoc code signature..."
  BIN="$APP_PATH/Contents/MacOS/Alan Graham Video Editor"
  if [[ -f "$BIN" ]]; then
    codesign --force --sign - "$BIN" || true
  fi
  codesign --force --deep --sign - "$APP_PATH" || true
fi

ZIP_PATH="dist/Alan-Graham-Video-Editor-macOS.zip"
echo "Creating client zip: $ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"

echo ""
echo "Done."
echo "  App:  $APP_PATH"
echo "  Zip:  $ZIP_PATH   (send this to the Mac client)"
echo ""
echo "Client: unzip, then double-click Alan Graham Video Editor.app"
echo "If blocked: System Settings → Privacy & Security → Open Anyway"
