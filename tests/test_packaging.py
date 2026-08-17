from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_file_exists() -> None:
    desktop = ROOT / "packaging" / "iphone-desk.desktop"
    text = desktop.read_text(encoding="utf-8")
    assert desktop.is_file()
    assert "Name=iPhone Desk" in text
    assert "Exec=iPhoneDesk" in text
    assert "Icon=iphone-desk" in text
    assert "Type=Application" in text


def test_build_appimage_script_is_executable() -> None:
    script = ROOT / "packaging" / "build-appimage.sh"
    assert script.is_file()
    tracked = subprocess.check_output(
        ["git", "ls-files", "-s", "--", "packaging/build-appimage.sh"],
        cwd=ROOT,
        text=True,
    )
    assert tracked.startswith("100755")
    if sys.platform != "win32":
        assert script.stat().st_mode & stat.S_IXUSR
    text = script.read_text(encoding="utf-8")
    assert "libqxcb" in text
    assert "linux-x86_64.AppImage" in text
    assert ".venv" in text
    assert "usr/lib/iPhoneDesk" in text


def test_release_workflow_publishes_both_assets_once() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "windows-x64.zip" in text
    assert "linux-x86_64.AppImage" in text
    assert "linux-appimage:" in text
    assert "\n  release:" in text
    assert text.count("action-gh-release") == 1
    windows_job = text.split("linux-appimage:")[0]
    assert "action-gh-release" not in windows_job
    assert "workflow_dispatch" in text
    assert "APPIMAGE_EXTRACT_AND_RUN" in text
