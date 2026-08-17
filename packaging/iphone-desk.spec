# PyInstaller spec: onedir bundle. A one-file Qt app was failing to start on Windows.
import sys
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).resolve().parent
if sys.platform == "win32":
    ICON = ROOT / "iphone_desk" / "assets" / "app.ico"
else:
    ICON = ROOT / "iphone_desk" / "assets" / "app.png"
    if not ICON.is_file():
        ICON = ROOT / "iphone_desk" / "assets" / "app.ico"


def _qt_plugin_binaries() -> list[tuple[str, str]]:
    """Keep xcb/Wayland (and Windows) Qt platform plugins in the onedir."""
    collected: list[tuple[str, str]] = []
    try:
        import PySide6
    except Exception:
        return collected
    root = Path(PySide6.__file__).resolve().parent
    groups = (
        "platforms",
        "xcbglintegrations",
        "wayland-shell-integration",
        "wayland-graphics-integration-client",
        "wayland-decoration-client",
        "platforminputcontexts",
        "imageformats",
        "iconengines",
        "styles",
        "tls",
    )
    for base in (root / "Qt" / "plugins", root / "plugins"):
        dest_prefix = "PySide6/Qt/plugins" if "Qt" in base.parts else "PySide6/plugins"
        for group in groups:
            folder = base / group
            if not folder.is_dir():
                continue
            dest = f"{dest_prefix}/{group}"
            for item in folder.iterdir():
                if item.is_file():
                    collected.append((str(item), dest))
    libdir = root / "Qt" / "lib"
    if libdir.is_dir():
        for pattern in (
            "libQt6XcbQpa*",
            "libQt6WaylandClient*",
            "libQt6WlShellIntegration*",
            "libQt6WaylandEglClientHwIntegration*",
        ):
            for item in libdir.glob(pattern):
                collected.append((str(item), "PySide6/Qt/lib"))
    return collected

datas, binaries, hidden = collect_all("pymobiledevice3")
try:
    av_datas, av_bins, av_hidden = collect_all("av")
    datas += av_datas
    binaries += av_bins
    hidden += av_hidden
except Exception:
    pass
datas += collect_data_files("iphone_desk")
binaries += _qt_plugin_binaries()
asset_dir = ROOT / "iphone_desk" / "assets"
if asset_dir.is_dir():
    datas.append((str(asset_dir), "iphone_desk/assets"))

a = Analysis(
    [str(ROOT / "iphone_desk" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden
    + [
        "iphone_desk",
        "iphone_desk.__main__",
        "iphone_desk.assets",
        "iphone_desk.keyboard",
        "iphone_desk.window",
        "iphone_desk.worker",
        "iphone_desk.device",
        "iphone_desk.live_video",
        "iphone_desk.frames",
        "av",
        "PIL",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        "shiboken6",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "xonsh",
        "IPython",
        "matplotlib",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="iPhoneDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="iPhoneDesk",
)
