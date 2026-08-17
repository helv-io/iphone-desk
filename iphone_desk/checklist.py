"""First-run checklist copy and status helpers (no device I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


CHECKLIST_STEPS: tuple[str, ...] = (
    "Install Apple Mobile Device Support (iTunes or the Apple Devices app) so Windows can talk to the phone over USB.",
    "Plug the iPhone in with a USB cable. USB is the supported path for 0.1.0. Wi-Fi is a later stretch goal.",
    "Unlock the iPhone and tap Trust This Computer if iOS asks.",
    "Enable Developer Mode: Settings > Privacy & Security > Developer Mode, then restart when iOS asks.",
    "Click Connect. iPhone Desk will pair if needed, mount Apple's Developer Disk Image, and open a userspace tunnel.",
)


WHAT_THIS_IS = (
    "iPhone Desk shows a phone you own and have already trusted on this PC. "
    "It uses Apple's public developer services through pymobiledevice3. "
    "It is not Apple iPhone Mirroring, not Continuity, and not an Apple ID pairing app. "
    "It does not jailbreak the phone, does not bypass the passcode, and will not control a device that has not tapped Trust."
)


@dataclass(frozen=True)
class ChecklistStatus:
    apple_mobile_device: bool
    usb_present: bool
    paired: Optional[bool]
    developer_mode: Optional[bool]
    device_labels: list[str] = field(default_factory=list)
    detail: str = ""

    def ready_to_connect(self) -> bool:
        return self.apple_mobile_device and self.usb_present


def format_step_state(
    apple_mobile_device: bool,
    usb_present: bool,
    paired: Optional[bool],
    developer_mode: Optional[bool],
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
            CHECKLIST_STEPS[1],
            "ok" if usb_present else "wait",
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
