"""First-run checklist copy and status helpers (no device I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


CHECKLIST_STEPS: tuple[str, ...] = (
    "Apple Mobile Device Support",
    "USB",
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
