"""User-facing errors for connect and session setup."""

from __future__ import annotations


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
