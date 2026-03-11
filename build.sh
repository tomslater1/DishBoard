#!/usr/bin/env bash
# DishBoard build script
# Usage: ./build.sh
# Produces: dist/DishBoard-vX.XX.dmg  (ad-hoc signed, ready to share)

set -euo pipefail

# ── Read version from Python source ──────────────────────────────────────────
VERSION=$(python3 -c "from utils.version import APP_VERSION; print(APP_VERSION)")
VERSION_CLEAN="${VERSION#v}"   # strip leading "v" → "0.44"
echo "▶ Building DishBoard ${VERSION}"

# ── Safety: refuse to build if dev artifacts exist in the root ───────────────
for f in dishboard.db config.json; do
    if [ -f "$f" ]; then
        echo "⚠  Warning: dev artifact '$f' found in project root."
        echo "   It will NOT be bundled (paths.py routes it to ~/Library/Application Support/)."
        echo "   If you want to clean it first, run: rm $f"
    fi
done

# ── Clean previous build ──────────────────────────────────────────────────────
echo "▶ Cleaning dist/ and build/..."
rm -rf dist/ build/

# ── PyInstaller ───────────────────────────────────────────────────────────────
echo "▶ Running PyInstaller..."
pyinstaller DishBoard.spec --clean -y

APP="dist/DishBoard.app"

# ── Verify no secrets inside the bundle ──────────────────────────────────────
echo "▶ Verifying bundle contents..."
FAIL=0
for f in "Contents/MacOS/dishboard.db" "Contents/Resources/dishboard.db"; do
    if [ -f "$APP/$f" ]; then
        echo "❌ ERROR: $f found inside .app bundle — aborting!"
        FAIL=1
    fi
done
if [ $FAIL -ne 0 ]; then
    exit 1
fi
echo "   ✓ No dev artifacts inside bundle"

# ── Ad-hoc code sign ─────────────────────────────────────────────────────────
echo "▶ Ad-hoc code signing..."
codesign --force --deep --sign - "$APP"
echo "   ✓ Signed (ad-hoc)"

# ── Create DMG ───────────────────────────────────────────────────────────────
DMG_NAME="DishBoard-${VERSION}.dmg"
echo "▶ Creating $DMG_NAME..."
hdiutil create \
    -volname "DishBoard" \
    -srcfolder "$APP" \
    -ov -format UDZO \
    "dist/$DMG_NAME"

# ── Done ──────────────────────────────────────────────────────────────────────
SIZE=$(du -sh "dist/$DMG_NAME" | cut -f1)
APP_SIZE=$(du -sh "$APP" | cut -f1)
echo ""
echo "✅ Build complete!"
echo "   App:  $APP ($APP_SIZE)"
echo "   DMG:  dist/$DMG_NAME ($SIZE)"
echo ""
echo "Next steps:"
echo "  1. Test: double-click dist/DishBoard.app"
echo "  2. Share: upload dist/$DMG_NAME to GitHub Releases as tag ${VERSION}"
echo "  3. Update GITHUB_REPO in utils/updater.py if not already set"
