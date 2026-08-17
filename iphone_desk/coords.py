"""Map window pixels to CoreDevice HID coordinates (UInt16 0..65535).

pymobiledevice3 documents this space for
``developer core-device universal-hid-service tap/drag``:
(0, 0) is top-left and (65535, 65535) is bottom-right, independent of
the phone's pixel resolution. Convert from pixels with
``developer core-device get-display-info`` then scale linearly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

HID_MAX = 65535
HID_MIN = 0


@dataclass(frozen=True)
class Size:
    width: int
    height: int


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.right and self.y <= py <= self.bottom


def clamp_hid(value: int) -> int:
    return max(HID_MIN, min(HID_MAX, int(value)))


def pixel_to_hid(px: float, py: float, width: int, height: int) -> tuple[int, int]:
    """Scale a pixel on a ``width`` x ``height`` display into HID 0..65535."""
    if width <= 0 or height <= 0:
        raise ValueError("display width and height must be positive")
    hid_x = round(px * HID_MAX / width)
    hid_y = round(py * HID_MAX / height)
    return clamp_hid(hid_x), clamp_hid(hid_y)


def hid_to_pixel(hid_x: int, hid_y: int, width: int, height: int) -> tuple[float, float]:
    """Inverse of :func:`pixel_to_hid` (used by tests)."""
    if width <= 0 or height <= 0:
        raise ValueError("display width and height must be positive")
    return hid_x * width / HID_MAX, hid_y * height / HID_MAX


def phone_corner_radius(width: float, height: float) -> float:
    """Corner radius for a modern iPhone screen (~55pt on a 430pt-wide phone)."""
    short = min(width, height)
    if short <= 0:
        return 0.0
    return short * 0.128


def fitted_image_rect(widget_w: float, widget_h: float, image_w: float, image_h: float) -> Rect:
    """Letterbox ``image`` inside ``widget`` while keeping aspect ratio."""
    if widget_w <= 0 or widget_h <= 0:
        return Rect(0.0, 0.0, 0.0, 0.0)
    if image_w <= 0 or image_h <= 0:
        return Rect(0.0, 0.0, widget_w, widget_h)
    scale = min(widget_w / image_w, widget_h / image_h)
    width = image_w * scale
    height = image_h * scale
    x = (widget_w - width) / 2.0
    y = (widget_h - height) / 2.0
    return Rect(x, y, width, height)


def widget_to_image_pixel(
    widget_x: float,
    widget_y: float,
    widget_w: float,
    widget_h: float,
    image_w: float,
    image_h: float,
) -> Optional[tuple[float, float]]:
    """Map a click on a letterboxed widget to image pixels, or None if in the margin."""
    dest = fitted_image_rect(widget_w, widget_h, image_w, image_h)
    if dest.width <= 0 or dest.height <= 0 or not dest.contains(widget_x, widget_y):
        return None
    px = (widget_x - dest.x) / dest.width * image_w
    py = (widget_y - dest.y) / dest.height * image_h
    return px, py


def widget_to_hid(
    widget_x: float,
    widget_y: float,
    widget_w: float,
    widget_h: float,
    display_w: int,
    display_h: int,
) -> Optional[tuple[int, int]]:
    """Map a window click through letterboxing into HID coordinates."""
    mapped = widget_to_image_pixel(
        widget_x, widget_y, widget_w, widget_h, float(display_w), float(display_h)
    )
    if mapped is None:
        return None
    return pixel_to_hid(mapped[0], mapped[1], display_w, display_h)


def scroll_wheel_to_drag(
    hid_x: int,
    hid_y: int,
    wheel_delta_y: int,
    *,
    distance: int = 5000,
) -> tuple[int, int, int, int]:
    """Map a mouse-wheel tick to a short vertical HID drag.

    Positive ``wheel_delta_y`` is scroll-up (Qt ``angleDelta().y()``). That
    becomes a downward swipe so the page moves up. Negative is scroll-down
    and becomes an upward swipe.
    """
    hid_x = clamp_hid(hid_x)
    hid_y = clamp_hid(hid_y)
    if wheel_delta_y == 0 or distance <= 0:
        return hid_x, hid_y, hid_x, hid_y
    delta = distance if wheel_delta_y > 0 else -distance
    end_y = clamp_hid(hid_y + delta)
    return hid_x, hid_y, hid_x, end_y
