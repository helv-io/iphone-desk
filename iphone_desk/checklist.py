"""First-run checklist copy and status helpers (no device I/O)."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from typing import Optional


def _system_name(system: str | None = None) -> str:
    return (system or platform.system()).strip().lower()


def phone_helper_label(system: str | None = None) -> str:
    """First checklist row: the USB mux helper on this OS."""
    if _system_name(system) == "linux":
        return "usbmuxd"
    return "Apple Mobile Device Support"


def phone_helper_missing_detail(system: str | None = None) -> str:
    """Setup-screen detail when the helper is not reachable."""
    if _system_name(system) == "linux":
        return (
            "usbmuxd is not reachable. Install it with: sudo apt install usbmuxd "
            "(Debian/Ubuntu), then replug USB."
        )
    return (
        "Apple Mobile Device / usbmux is not reachable. "
        "Install Apple Mobile Device Support, then replug USB."
    )


def phone_helper_missing_error(system: str | None = None) -> str:
    """Connect error when the helper is not running."""
    if _system_name(system) == "linux":
        return "usbmuxd is not running. Install it with: sudo apt install usbmuxd (Debian/Ubuntu)."
    return "Apple Mobile Device / usbmux is not running. Install Apple Mobile Device Support."


def checklist_steps(system: str | None = None) -> tuple[str, ...]:
    return (
        phone_helper_label(system),
        "USB / WiFi",
        "Trust",
        "Developer Mode",
        "Connect",
    )


CHECKLIST_STEPS: tuple[str, ...] = checklist_steps()


@dataclass(frozen=True)
class ChecklistStatus:
    apple_mobile_device: bool
    usb_present: bool
    paired: Optional[bool]
    developer_mode: Optional[bool]
    device_labels: list[str] = field(default_factory=list)
    detail: str = ""
    wifi_present: bool = False

    def transport_present(self) -> bool:
        return self.usb_present or self.wifi_present

    def ready_to_connect(self) -> bool:
        return self.apple_mobile_device and self.transport_present()


def transport_step_label(usb_present: bool, wifi_present: bool) -> str:
    if usb_present and wifi_present:
        return "USB + WiFi"
    if usb_present:
        return "USB"
    if wifi_present:
        return "WiFi"
    return "USB / WiFi"


def format_step_state(
    apple_mobile_device: bool,
    usb_present: bool,
    paired: Optional[bool],
    developer_mode: Optional[bool],
    wifi_present: bool = False,
    system: str | None = None,
) -> list[tuple[str, str]]:
    """Return (label, state) pairs for the UI. state is ok, wait, or fail."""

    def _tri(value: Optional[bool], waiting: str, ok: str, fail: str) -> str:
        if value is None:
            return waiting
        return ok if value else fail

    steps = checklist_steps(system)
    return [
        (
            steps[0],
            "ok" if apple_mobile_device else "fail",
        ),
        (
            transport_step_label(usb_present, wifi_present),
            "ok" if usb_present or wifi_present else "wait",
        ),
        (
            steps[2],
            _tri(paired, "wait", "ok", "wait"),
        ),
        (
            steps[3],
            _tri(developer_mode, "wait", "ok", "fail"),
        ),
        (steps[4], "wait"),
    ]
