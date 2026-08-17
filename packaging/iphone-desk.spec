# PyInstaller spec for a one-file Windows build of iPhone Desk.
from pathlib import Path

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
ICON = ROOT / "iphone_desk" / "assets" / "app.ico"

datas, binaries, hidden = collect_all("pymobiledevice3")
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
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["xonsh", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="iPhoneDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
)
