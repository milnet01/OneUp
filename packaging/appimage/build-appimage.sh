#!/usr/bin/env bash
#
# Build a single-file OneUp AppImage.
#
# PyInstaller freezes the GUI + the engine script + the icon into ONE self-
# contained binary (Python and Qt included), then appimagetool wraps it with
# desktop integration. The result — OneUp-x86_64.AppImage — needs nothing
# installed on the target machine except FUSE to run it (libfuse2).
#
# Usage:  packaging/appimage/build-appimage.sh
# Deps :  python3 (+venv), curl, and libfuse2 on the build host.
set -euo pipefail

here=$(cd "$(dirname "$0")/../.." && pwd)     # repo root
app_id="za.co.antsprojectshub.OneUp"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "==> Freezing OneUp with PyInstaller"
python3 -m venv "$work/venv"
"$work/venv/bin/pip" install --quiet --upgrade pip
"$work/venv/bin/pip" install --quiet pyinstaller PySide6

"$work/venv/bin/pyinstaller" --noconfirm --clean --onefile --windowed \
    --name oneup \
    --add-data "$here/update_system.sh:." \
    --add-data "$here/data/$app_id.svg:data" \
    --distpath "$work/dist" --workpath "$work/build" --specpath "$work" \
    "$here/updater.py"

echo "==> Assembling the AppDir"
appdir="$work/OneUp.AppDir"
install -Dm0755 "$work/dist/oneup" "$appdir/usr/bin/oneup"
install -Dm0644 "$here/data/$app_id.svg" \
    "$appdir/usr/share/icons/hicolor/scalable/apps/$app_id.svg"
install -Dm0644 "$here/data/$app_id.svg"          "$appdir/$app_id.svg"
install -Dm0644 "$here/data/$app_id.desktop" \
    "$appdir/usr/share/applications/$app_id.desktop"
install -Dm0644 "$here/data/$app_id.desktop"      "$appdir/$app_id.desktop"
install -Dm0644 "$here/data/$app_id.metainfo.xml" \
    "$appdir/usr/share/metainfo/$app_id.metainfo.xml"
ln -sf "$app_id.svg" "$appdir/.DirIcon"

cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
HERE=$(dirname "$(readlink -f "$0")")
exec "$HERE/usr/bin/oneup" "$@"
EOF
chmod +x "$appdir/AppRun"

echo "==> Fetching appimagetool (if needed)"
tool=$(command -v appimagetool || true)
if [ -z "$tool" ]; then
    tool="$work/appimagetool"
    curl -fsSL -o "$tool" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$tool"
fi

echo "==> Packing the AppImage"
out="$here/OneUp-x86_64.AppImage"
# --appimage-extract-and-run lets appimagetool run without host FUSE.
ARCH=x86_64 "$tool" --appimage-extract-and-run "$appdir" "$out"
echo "==> Built: $out"
