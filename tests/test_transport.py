from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from iphone_desk.device import (
    NO_DEVICE_STATUS,
    DeviceSession,
    pick_usbmux_device,
    probe_checklist,
    usbmux_connection_type,
)
from iphone_desk.errors import DeveloperModeRequiredError, NoDeviceError, NoUsbDeviceError
from iphone_desk.video_modes import VIDEO_MODE_DVT


class FakeMuxDevice:
    def __init__(self, serial: str, connection_type: str) -> None:
        self.serial = serial
        self.connection_type = connection_type
        self.is_usb = connection_type == "USB"
        self.is_network = connection_type == "Network"


class FakeLockdown:
    def __init__(
        self,
        *,
        paired: bool = True,
        developer_mode: bool = False,
        product_version: str = "18.5",
        display_name: str = "Helvio",
    ) -> None:
        self.paired = paired
        self.product_version = product_version
        self.display_name = display_name
        self.udid = "00008030-001"
        self._developer_mode = developer_mode
        self.closed = False
        self.wifi_sets: list[bool] = []

    async def get_developer_mode_status(self) -> bool:
        return self._developer_mode

    async def set_enable_wifi_connections(self, value: bool) -> None:
        self.wifi_sets.append(bool(value))
        raise AssertionError("set_enable_wifi_connections must not be called")

    async def close(self) -> None:
        self.closed = True


def _install_pymd3(
    monkeypatch: pytest.MonkeyPatch,
    *,
    lockdown: FakeLockdown,
    devices: list[FakeMuxDevice],
    create_calls: list[dict[str, Any]],
) -> None:
    exceptions = types.ModuleType("pymobiledevice3.exceptions")
    for name in (
        "ConnectionFailedToUsbmuxdError",
        "NotPairedError",
        "PairingDialogResponsePendingError",
        "PasswordRequiredError",
        "UserDeniedPairingError",
        "AlreadyMountedError",
        "DeveloperModeIsNotEnabledError",
    ):
        setattr(exceptions, name, type(name, (Exception,), {}))

    async def create_mux() -> Any:
        mux = types.SimpleNamespace()

        async def close() -> None:
            return None

        mux.close = close
        return mux

    async def list_devices() -> list[FakeMuxDevice]:
        return list(devices)

    async def create_using_usbmux(**kwargs: Any) -> FakeLockdown:
        create_calls.append(dict(kwargs))
        return lockdown

    lockdown_mod = types.ModuleType("pymobiledevice3.lockdown")
    lockdown_mod.create_using_usbmux = create_using_usbmux  # type: ignore[attr-defined]
    usbmux_mod = types.ModuleType("pymobiledevice3.usbmux")
    usbmux_mod.create_mux = create_mux  # type: ignore[attr-defined]
    usbmux_mod.list_devices = list_devices  # type: ignore[attr-defined]
    amfi_mod = types.ModuleType("pymobiledevice3.services.amfi")

    class UnusedAmfi:
        def __init__(self, _lockdown: Any) -> None:
            raise AssertionError("AMFI is not under test here")

    amfi_mod.AmfiService = UnusedAmfi  # type: ignore[attr-defined]
    root = types.ModuleType("pymobiledevice3")
    services = types.ModuleType("pymobiledevice3.services")

    for name, mod in {
        "pymobiledevice3": root,
        "pymobiledevice3.exceptions": exceptions,
        "pymobiledevice3.lockdown": lockdown_mod,
        "pymobiledevice3.usbmux": usbmux_mod,
        "pymobiledevice3.services": services,
        "pymobiledevice3.services.amfi": amfi_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)


def test_picker_uses_usb_and_ignores_network() -> None:
    usb = FakeMuxDevice("00008030-001", "USB")
    wifi = FakeMuxDevice("00008030-001", "Network")
    picked = pick_usbmux_device([wifi, usb], "00008030-001")
    assert picked is usb
    assert usbmux_connection_type(picked) == "USB"


def test_picker_rejects_network_only() -> None:
    wifi = FakeMuxDevice("00008030-001", "Network")
    assert pick_usbmux_device([wifi]) is None


def test_no_usb_error_is_no_device_error() -> None:
    assert NoUsbDeviceError is NoDeviceError
    assert issubclass(NoDeviceError, Exception)


@pytest.mark.asyncio
async def test_connect_uses_usb_when_both_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    lockdown = FakeLockdown(developer_mode=False)
    calls: list[dict[str, Any]] = []
    _install_pymd3(
        monkeypatch,
        lockdown=lockdown,
        devices=[
            FakeMuxDevice("00008030-001", "Network"),
            FakeMuxDevice("00008030-001", "USB"),
        ],
        create_calls=calls,
    )
    monkeypatch.setattr("iphone_desk.device.reveal_developer_mode_option", _async_true)
    session = DeviceSession()
    statuses: list[str] = []
    with pytest.raises(DeveloperModeRequiredError):
        await session.connect(video_mode=VIDEO_MODE_DVT, on_status=statuses.append)
    assert calls[0]["connection_type"] == "USB"
    assert lockdown.wifi_sets == []
    assert any("Pairing over USB" in item for item in statuses)
    await session.close()


@pytest.mark.asyncio
async def test_connect_ignores_network_only(monkeypatch: pytest.MonkeyPatch) -> None:
    lockdown = FakeLockdown(developer_mode=False)
    calls: list[dict[str, Any]] = []
    _install_pymd3(
        monkeypatch,
        lockdown=lockdown,
        devices=[FakeMuxDevice("00008030-001", "Network")],
        create_calls=calls,
    )
    session = DeviceSession()
    with pytest.raises(NoDeviceError) as caught:
        await session.connect(video_mode=VIDEO_MODE_DVT)
    assert str(caught.value) == NO_DEVICE_STATUS
    assert calls == []
    await session.close()


@pytest.mark.asyncio
async def test_connect_without_devices_is_usb_only(monkeypatch: pytest.MonkeyPatch) -> None:
    lockdown = FakeLockdown()
    _install_pymd3(monkeypatch, lockdown=lockdown, devices=[], create_calls=[])
    session = DeviceSession()
    with pytest.raises(NoDeviceError) as caught:
        await session.connect(video_mode=VIDEO_MODE_DVT)
    assert str(caught.value) == NO_DEVICE_STATUS
    assert "WiFi" not in str(caught.value)
    await session.close()


@pytest.mark.asyncio
async def test_probe_ignores_network_device(monkeypatch: pytest.MonkeyPatch) -> None:
    lockdown = FakeLockdown(paired=True, developer_mode=True)
    calls: list[dict[str, Any]] = []
    _install_pymd3(
        monkeypatch,
        lockdown=lockdown,
        devices=[FakeMuxDevice("00008030-001", "Network")],
        create_calls=calls,
    )
    status = await probe_checklist()
    assert status.usb_present is False
    assert not status.ready_to_connect()
    assert calls == []
    assert status.detail == NO_DEVICE_STATUS


@pytest.mark.asyncio
async def test_probe_uses_usb_when_both_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    lockdown = FakeLockdown(paired=True, developer_mode=True)
    calls: list[dict[str, Any]] = []
    _install_pymd3(
        monkeypatch,
        lockdown=lockdown,
        devices=[
            FakeMuxDevice("00008030-001", "Network"),
            FakeMuxDevice("00008030-001", "USB"),
        ],
        create_calls=calls,
    )
    monkeypatch.setattr("iphone_desk.device.reveal_developer_mode_option", _async_true)
    status = await probe_checklist()
    assert status.usb_present is True
    assert calls[0]["connection_type"] == "USB"
    assert "USB" in status.detail
    assert "WiFi" not in status.detail
    assert lockdown.wifi_sets == []


@pytest.mark.asyncio
async def test_probe_empty_is_usb_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_pymd3(monkeypatch, lockdown=FakeLockdown(), devices=[], create_calls=[])
    status = await probe_checklist()
    assert status.detail == NO_DEVICE_STATUS
    assert not status.ready_to_connect()


def test_product_code_does_not_enable_wifi() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath("iphone_desk", "device.py").read_text()
    assert "set_enable_wifi_connections" not in text
    assert "get_enable_wifi_connections" not in text
    assert "ensure_wifi_connections" not in text


async def _async_true(_lockdown: Any) -> bool:
    return True
