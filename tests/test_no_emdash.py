from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "iphone_desk.egg-info",
    "dist",
    "build",
    "AppDir",
    "squashfs-root",
}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".txt",
    ".bat",
    ".ps1",
    ".sh",
    ".yml",
    ".yaml",
    ".desktop",
    ".spec",
    ".gitignore",
}


def test_repo_text_has_no_em_dash() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES and path.name != "LICENSE":
            continue
        text = path.read_text(encoding="utf-8")
        if "\u2014" in text or "\u2013" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
