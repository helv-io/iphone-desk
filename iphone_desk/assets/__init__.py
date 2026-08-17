"""Packaged icon paths."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def app_icon_path() -> Optional[Path]:
    folder = Path(__file__).resolve().parent
    for name in ("app.ico", "app.png"):
        path = folder / name
        if path.is_file():
            return path
    return None
