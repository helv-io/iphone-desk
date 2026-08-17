"""Parse ``get-display-info`` payloads from pymobiledevice3 CoreDevice."""

from __future__ import annotations

from typing import Any, Optional

from iphone_desk.coords import Size


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _size_from_mapping(data: dict[str, Any]) -> Optional[Size]:
    width = _as_int(data.get("width") or data.get("Width") or data.get("pixelWidth"))
    height = _as_int(data.get("height") or data.get("Height") or data.get("pixelHeight"))
    if width and height and width > 0 and height > 0:
        return Size(width, height)
    return None


def _size_from_value(value: Any) -> Optional[Size]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        width = _as_int(value[0])
        height = _as_int(value[1])
        if width and height and width > 0 and height > 0:
            return Size(width, height)
        return None
    if isinstance(value, dict):
        return _size_from_mapping(value)
    return None


def parse_display_size(info: dict[str, Any]) -> Size:
    """Read pixel size from a CoreDevice ``get-display-info`` dict.

    Documented shape is ``displays[0].currentMode.size = [width, height]``.
    Older or slightly different keys are accepted so a firmware rename does
    not blank the viewer.
    """
    displays = info.get("displays") or info.get("Displays") or ()
    if isinstance(displays, dict):
        displays = list(displays.values())
    if not isinstance(displays, (list, tuple)):
        displays = ()

    candidates: list[Any] = list(displays)
    if not candidates:
        candidates = [info]

    for display in candidates:
        if not isinstance(display, dict):
            continue
        mode = display.get("currentMode") or display.get("CurrentMode") or display
        if isinstance(mode, dict):
            size = _size_from_value(mode.get("size") or mode.get("Size"))
            if size is not None:
                return size
            size = _size_from_mapping(mode)
            if size is not None:
                return size
        size = _size_from_value(display.get("size") or display.get("Size"))
        if size is not None:
            return size
        size = _size_from_mapping(display)
        if size is not None:
            return size

    raise ValueError("get-display-info did not include a usable pixel size")
