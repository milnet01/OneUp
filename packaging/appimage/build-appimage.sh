#!/usr/bin/env bash
#
# Build a single-file OneUp AppImage.
#
# PyInstaller freezes the GUI + the icon into ONE self-contained binary (Python
# and Qt included), then appimagetool wraps it with desktop integration. The
# engine travels as source under engine-src/: the window copies it out of the
# bundle and runs it on the machine's own python3, because the bundle's mount
# goes when the window exits and the engine must outlive it (ONEUP-0054 §4.7).
# So the result — OneUp-x86_64.AppImage — needs FUSE (libfuse2) and a python3 of
# 3.13 or newer on the target machine (docs/standards/coding.md §1's floor, which
# every supported openSUSE ships).
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
"$work/venv/bin/pip" install --quiet -r "$here/packaging/appimage/requirements.txt"

# --paths puts the repo root on the analysis path so PyInstaller resolves the
# root shim's `from oneup.gui.app import main` and follows it through the whole
# package. Without it the freeze succeeds and the binary fails at launch with
# ModuleNotFoundError, because the shim's own directory is not the analysis root
# when the entry point is given by absolute path.
"$work/venv/bin/pyinstaller" --noconfirm --clean --onefile --windowed \
    --name oneup \
    --paths "$here" \
    --add-data "$here/update_system.sh:." \
    --add-data "$here/oneup/__init__.py:engine-src/oneup" \
    --add-data "$here/oneup/engine:engine-src/oneup/engine" \
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

# Both tools come from a fixed release and must match the sha256 written here
# (security.md §8.2). The runtime is copied into every shipped AppImage and the tool
# runs inside the build, so the moving `continuous` release they came from before
# meant a build whose output nobody chose (ONEUP-0391). A host appimagetool is not
# used either, for the same reason. To move a pin: change the tag and the checksum
# together, and the row in docs/standards/dependencies.md.
fetch_pinned() {  # url, sha256, destination
    curl -fsSL --connect-timeout 20 --max-time 300 --retry 3 -o "$3" "$1"
    echo "$2  $3" | sha256sum -c --quiet - || {
        echo "build-appimage: checksum mismatch for $1" >&2
        exit 1
    }
}

echo "==> Fetching appimagetool"
tool="$work/appimagetool"
fetch_pinned "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage" ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0 "$tool"
chmod +x "$tool"

# The runtime is fetched here, not by appimagetool: its own download hung with the
# server's socket already closed (ONEUP-0376), and curl bounds the wait.
echo "==> Fetching the AppImage runtime"
runtime="$work/runtime-x86_64"
fetch_pinned "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64" 2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d "$runtime"

echo "==> Packing the AppImage"
out="$here/OneUp-x86_64.AppImage"
# --appimage-extract-and-run lets appimagetool run without host FUSE.
ARCH=x86_64 "$tool" --appimage-extract-and-run --runtime-file "$runtime" "$appdir" "$out"
echo "==> Built: $out"
