from pathlib import Path

from iphone_desk import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_version_is_040() -> None:
    assert __version__ == "0.4.0"
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'version = "0.4.0"' in pyproject
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert "## [0.4.0]" in changelog
    assert "## [0.3.0]" in changelog
    assert "Connect over WiFi after the first USB Trust" in changelog


def test_readme_is_usb_only_and_documents_modes() -> None:
    text = (ROOT / "README.md").read_text()
    assert "USB only" in text
    assert "Video mode" in text
    assert "HEVC live" in text
    assert "DVT screenshots" in text
    assert "Core Device stills" in text
    assert "Lockdown screenshotr" in text
    assert "WiFi" not in text
    assert "wireless" not in text.casefold()
