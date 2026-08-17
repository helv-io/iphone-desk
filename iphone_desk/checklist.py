"""First-run checklist copy and status helpers (no device I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


CHECKLIST_STEPS: tuple[str, ...] = (
    "Apple Mobile Device Support",
    "USB / WiFi",
    "Trust",
    "Developer Mode",
    "Connect",
)


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
) -> list[tuple[str, str]]:
    """Return (label, state) pairs for the UI. state is ok, wait, or fail."""

    def _tri(value: Optional[bool], waiting: str, ok: str, fail: str) -> str:
        if value is None:
            return waiting
        return ok if value else fail

    return [
        (
            CHECKLIST_STEPS[0],
            "ok" if apple_mobile_device else "fail",
        ),
        (
            transport_step_label(usb_present, wifi_present),
            "ok" if usb_present or wifi_present else "wait",
        ),
        (
            CHECKLIST_STEPS[2],
            _tri(paired, "wait", "ok", "wait"),
        ),
        (
            CHECKLIST_STEPS[3],
            _tri(developer_mode, "wait", "ok", "fail"),
        ),
        (CHECKLIST_STEPS[4], "wait"),
    ]
