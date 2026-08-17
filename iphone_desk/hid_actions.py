"""Compose tap, drag, and scroll using pymobiledevice3 HID helpers.

These functions only call documented ``UniversalHIDServiceService`` methods
(``send_touchscreen``) and the public contact/release constants. They do not
invent HID report layouts.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from iphone_desk.coords import HID_MAX, clamp_hid, scroll_wheel_to_drag

# Same values pymobiledevice3 exports as TOUCHSCREEN_STATE_CONTACT / RELEASE.
TOUCH_CONTACT = 0xC2
TOUCH_RELEASE = 0x02


class TouchScreen(Protocol):
    async def send_touchscreen(self, state: int, x: int, y: int, service_id: int = 257) -> None: ...


def normalize_point(x: int, y: int) -> tuple[int, int]:
    return clamp_hid(x), clamp_hid(y)


async def contact(service: TouchScreen, x: int, y: int) -> None:
    """Finger down or finger moved. Same HID state as a live drag sample."""
    x, y = normalize_point(x, y)
    await service.send_touchscreen(TOUCH_CONTACT, x, y)


async def release(service: TouchScreen, x: int, y: int) -> None:
    """Finger up at ``(x, y)``."""
    x, y = normalize_point(x, y)
    await service.send_touchscreen(TOUCH_RELEASE, x, y)


async def tap(service: TouchScreen, x: int, y: int, *, hold: float = 0.05) -> None:
    """One CONTACT then RELEASE at the same HID point."""
    x, y = normalize_point(x, y)
    await service.send_touchscreen(TOUCH_CONTACT, x, y)
    if hold > 0:
        await asyncio.sleep(hold)
    await service.send_touchscreen(TOUCH_RELEASE, x, y)


async def drag(
    service: TouchScreen,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    steps: int = 16,
    duration: float = 0.25,
) -> None:
    """Stream CONTACT reports from start to end, then RELEASE."""
    x1, y1 = normalize_point(x1, y1)
    x2, y2 = normalize_point(x2, y2)
    steps = max(1, int(steps))
    frame = duration / steps if duration > 0 else 0.0
    for i in range(steps):
        t = i / steps
        x = round(x1 + (x2 - x1) * t)
        y = round(y1 + (y2 - y1) * t)
        await service.send_touchscreen(TOUCH_CONTACT, x, y)
        if frame > 0:
            await asyncio.sleep(frame)
    await service.send_touchscreen(TOUCH_CONTACT, x2, y2)
    await service.send_touchscreen(TOUCH_RELEASE, x2, y2)


async def scroll_from_wheel(
    service: TouchScreen,
    hid_x: int,
    hid_y: int,
    wheel_delta_y: int,
    *,
    distance: int = 5000,
) -> None:
    """Turn a mouse-wheel tick into a short drag."""
    x1, y1, x2, y2 = scroll_wheel_to_drag(hid_x, hid_y, wheel_delta_y, distance=distance)
    if (x1, y1) == (x2, y2):
        return
    await drag(service, x1, y1, x2, y2, steps=8, duration=0.12)


# Named buttons used by ``developer core-device hid button``.
# (usage_page, usage_code, hold_seconds) from pymobiledevice3's ButtonName table.
BUTTONS: dict[str, tuple[int, int, float]] = {
    "home": (0x0C, 0x40, 0.05),
    "lock": (0x0C, 0x30, 0.5),
    "siri": (0x0C, 0x30, 0.85),
    "volume-up": (0x0C, 0xE9, 0.05),
    "volume-down": (0x0C, 0xEA, 0.05),
}

HID_BUTTON_DOWN = 1
HID_BUTTON_UP = 2


class ButtonService(Protocol):
    async def send_button(self, usage_page: int, usage_code: int, state: int) -> None: ...


async def press_named_button(service: ButtonService, name: str) -> None:
    """Press a named hardware button through Indigo HID."""
    key = name.strip().lower()
    if key not in BUTTONS:
        raise ValueError(f"unknown button: {name}")
    usage_page, usage_code, hold = BUTTONS[key]
    await service.send_button(usage_page, usage_code, HID_BUTTON_DOWN)
    if hold > 0:
        await asyncio.sleep(hold)
    await service.send_button(usage_page, usage_code, HID_BUTTON_UP)


def drag_is_tap(x1: int, y1: int, x2: int, y2: int, *, threshold: int = 400) -> bool:
    """Treat a tiny pointer move as a tap instead of a drag."""
    return abs(x2 - x1) <= threshold and abs(y2 - y1) <= threshold


# Keep HID_MAX imported for callers that want the documented range.
__all__ = [
    "BUTTONS",
    "HID_BUTTON_DOWN",
    "HID_BUTTON_UP",
    "HID_MAX",
    "TOUCH_CONTACT",
    "TOUCH_RELEASE",
    "contact",
    "drag",
    "drag_is_tap",
    "normalize_point",
    "press_named_button",
    "release",
    "scroll_from_wheel",
    "tap",
]
