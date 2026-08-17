"""User-facing errors for connect and session setup."""

from __future__ import annotations

from typing import Iterable


class DeskError(Exception):
    """Something the UI can show as a single status line."""


class DriverMissingError(DeskError):
    pass


class NoUsbDeviceError(DeskError):
    pass


class TrustRequiredError(DeskError):
    pass


class DeveloperModeRequiredError(DeskError):
    pass


class IosVersionError(DeskError):
    pass


TOUCH_BLOCKED_STATUS = (
    "Screen works. Taps are blocked on this iOS (live remote-control video was rejected)."
)

REMOTE_CONTROL_FALLBACK_STATUS = (
    "This iPhone rejected live remote-control video. Screenshot mode can still show the screen."
)


def _exception_text(exc: BaseException) -> str:
    parts = [str(exc)]
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(repr(current))
        if getattr(current, "args", None):
            parts.extend(str(arg) for arg in current.args)
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def is_remote_control_unsupported(exc: BaseException) -> bool:
    """True when Apple rejected startmediastream (code 9021 / iOS 27 required)."""
    text = _exception_text(exc).lower()
    if "remote control requires" in text:
        return True
    if "ios 27" in text:
        return True
    if "9021" in text and ("startmediastream" in text or "coredevice" in text):
        return True
    return False


def _looks_like_coredevice_dump(text: str) -> bool:
    lowered = text.lower()
    markers: Iterable[str] = (
        "bplist",
        "userinfowithnssecurecoding",
        "coredevice.error",
        "failed to invoke:",
        "nskeyedarchiver",
    )
    return any(marker in lowered for marker in markers)


def humanize_device_error(exc: BaseException) -> str:
    """Short status text. Never forward a raw CoreDevice plist dump to the UI."""
    if is_remote_control_unsupported(exc):
        return REMOTE_CONTROL_FALLBACK_STATUS
    text = str(exc).strip() or exc.__class__.__name__
    if _looks_like_coredevice_dump(text):
        return "The phone rejected a CoreDevice request. Details are in the log, not shown here."
    return text
