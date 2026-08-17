#!/usr/bin/env bash
# Build dist/iPhoneDesk/ (PyInstaller onedir) and wrap it as
# dist/iPhoneDesk-<ver>-linux-x86_64.AppImage.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export APPIMAGE_EXTRACT_AND_RUN="${APPIMAGE_EXTRACT_AND_RUN:-1}"
export NO_STRIP="${NO_STRIP:-1}"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing .venv. Create it with: python3.12 -m venv .venv" >&2
  exit 1
fi

"$PYTHON" -m pip install -e ".[dist]"

SPEC="$ROOT/packaging/iphone-desk.spec"
"$PYTHON" -m PyInstaller --noconfirm --clean "$SPEC"

ONEDIR="$ROOT/dist/iPhoneDesk"
BIN="$ONEDIR/iPhoneDesk"
if [[ ! -x "$BIN" ]]; then
  echo "Expected $BIN" >&2
  exit 1
fi

_copy_qt_plugins_from_venv() {
  local pyside dest_root src_plugins dest_plugins
  pyside="$("$PYTHON" -c 'import pathlib, PySide6; print(pathlib.Path(PySide6.__file__).resolve().parent)')"
  if [[ -d "$ONEDIR/_internal/PySide6" ]]; then
    dest_root="$ONEDIR/_internal/PySide6"
  elif [[ -d "$ONEDIR/PySide6" ]]; then
    dest_root="$ONEDIR/PySide6"
  else
    dest_root="$ONEDIR/_internal/PySide6"
    mkdir -p "$dest_root"
  fi
  if [[ -d "$pyside/Qt/plugins" ]]; then
    src_plugins="$pyside/Qt/plugins"
    dest_plugins="$dest_root/Qt/plugins"
  elif [[ -d "$pyside/plugins" ]]; then
    src_plugins="$pyside/plugins"
    dest_plugins="$dest_root/plugins"
  else
    echo "No PySide6 plugins directory in the venv" >&2
    return 1
  fi
  mkdir -p "$dest_plugins"
  cp -a "$src_plugins/." "$dest_plugins/"
}

if ! find "$ONEDIR" -name 'libqxcb.so' | grep -q .; then
  echo "PyInstaller onedir is missing libqxcb.so; copying Qt platform plugins from the venv"
  _copy_qt_plugins_from_venv
fi
if ! find "$ONEDIR" -name 'libqxcb.so' | grep -q .; then
  echo "Still missing libqxcb.so after copying from the venv" >&2
  exit 1
fi

VERSION="${VERSION:-$("$PYTHON" -c 'from iphone_desk import __version__; print(__version__)')}"
APPIMAGE_NAME="iPhoneDesk-${VERSION}-linux-x86_64.AppImage"
APPDIR="$ROOT/dist/iPhoneDesk.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/iPhoneDesk" "$APPDIR/usr/lib"

# Keep the onedir together. PyInstaller resolves _internal next to the binary.
# linuxdeploy may also copy the bootloader to usr/bin; AppRun must not use that copy.
cp -a "$ONEDIR/." "$APPDIR/usr/lib/iPhoneDesk/"

ICON_SRC="$ROOT/iphone_desk/assets/app.png"
if [[ ! -f "$ICON_SRC" ]]; then
  echo "Missing $ICON_SRC" >&2
  exit 1
fi
ICON_DEST="$ROOT/dist/iphone-desk.png"
cp "$ICON_SRC" "$ICON_DEST"
DESKTOP="$ROOT/packaging/iphone-desk.desktop"

# Stage Qt libs where linuxdeploy-plugin-qt looks (usr/lib) without
# flattening the PyInstaller onedir the binary needs next to itself.
while IFS= read -r so; do
  cp -n "$so" "$APPDIR/usr/lib/" 2>/dev/null || true
done < <(find "$APPDIR/usr/lib/iPhoneDesk" \( -name 'libQt6*.so*' -o -name 'libpyside6*.so*' -o -name 'libshiboken6*.so*' \))

TOOLS="${IPHONE_DESK_LINUXDEPLOY:-$ROOT/packaging/.tools}"
mkdir -p "$TOOLS"
_fetch() {
  local url="$1" dest="$2"
  if [[ -x "$dest" ]]; then
    return 0
  fi
  curl -fsSL --retry 4 --retry-delay 2 -o "$dest" "$url"
  chmod +x "$dest"
}

_fetch "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage" \
  "$TOOLS/linuxdeploy-x86_64.AppImage"
_fetch "https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-x86_64.AppImage" \
  "$TOOLS/linuxdeploy-plugin-qt-x86_64.AppImage"
_fetch "https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage" \
  "$TOOLS/linuxdeploy-plugin-appimage-x86_64.AppImage"

QMAKE="$("$PYTHON" -c 'import pathlib, PySide6; p = pathlib.Path(PySide6.__file__).resolve().parent / "Qt" / "libexec" / "qmake"; print(p if p.is_file() else "")')"
if [[ -n "$QMAKE" ]]; then
  export QMAKE
fi
export EXTRA_PLATFORM_PLUGINS="${EXTRA_PLATFORM_PLUGINS:-libqwayland-generic.so;libqwayland-egl.so}"
export LINUXDEPLOY="$TOOLS/linuxdeploy-x86_64.AppImage"
export OUTPUT="$APPIMAGE_NAME"

run_linuxdeploy() {
  "$TOOLS/linuxdeploy-x86_64.AppImage" --appimage-extract-and-run "$@"
}

ONEDIR_BIN="$APPDIR/usr/lib/iPhoneDesk/iPhoneDesk"

run_linuxdeploy \
  --appdir "$APPDIR" \
  --executable "$ONEDIR_BIN" \
  --desktop-file "$DESKTOP" \
  --icon-file "$ICON_DEST"

if ! run_linuxdeploy --appdir "$APPDIR" --plugin qt; then
  echo "linuxdeploy-plugin-qt failed; continuing with PyInstaller Qt plugins already in the onedir"
fi

# Point linuxdeploy at libqxcb.so so it also collects host xcb libs the plugin needs.
XCB="$(find "$APPDIR" -name 'libqxcb.so' -print -quit)"
if [[ -z "$XCB" ]]; then
  echo "AppDir is missing libqxcb.so" >&2
  exit 1
fi

run_linuxdeploy \
  --appdir "$APPDIR" \
  --executable "$ONEDIR_BIN" \
  --desktop-file "$DESKTOP" \
  --icon-file "$ICON_DEST" \
  --library "$XCB"

# Write AppRun after linuxdeploy so it is not replaced. Always exec the
# onedir binary, not a bootloader copy that linuxdeploy may put in usr/bin.
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
set -e
HERE="$(dirname "$(readlink -f "$0")")"
export APPDIR="${APPDIR:-$HERE}"
exec "$HERE/usr/lib/iPhoneDesk/iPhoneDesk" "$@"
EOF
chmod +x "$APPDIR/AppRun"

"$TOOLS/linuxdeploy-plugin-appimage-x86_64.AppImage" --appimage-extract-and-run --appdir "$APPDIR"

if [[ -f "$APPIMAGE_NAME" ]]; then
  mv -f "$APPIMAGE_NAME" "$ROOT/dist/$APPIMAGE_NAME"
elif [[ -f "$ROOT/$APPIMAGE_NAME" ]]; then
  mv -f "$ROOT/$APPIMAGE_NAME" "$ROOT/dist/$APPIMAGE_NAME"
fi

OUT="$ROOT/dist/$APPIMAGE_NAME"
if [[ ! -f "$OUT" ]]; then
  echo "Expected $OUT" >&2
  find "$ROOT" "$ROOT/dist" -maxdepth 2 -name '*.AppImage' -print >&2 || true
  exit 1
fi
chmod +x "$OUT"

EXTRACT="$(mktemp -d)"
cleanup() { rm -rf "$EXTRACT"; }
trap cleanup EXIT
(
  cd "$EXTRACT"
  "$OUT" --appimage-extract >/dev/null
)
if ! find "$EXTRACT/squashfs-root" -name 'libqxcb.so' | grep -q .; then
  echo "AppImage is missing libqxcb.so" >&2
  exit 1
fi

ls -l "$BIN" "$OUT"
echo "Built $OUT"
