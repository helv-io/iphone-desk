from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from iphone_desk.device import (
    NO_DEVICE_STATUS,
    DeviceSession,
    ensure_wifi_connections,
    pick_usbmux_device,
    probe_checklist,
    transport_label,
    usbmux_connection_type,
)
from iphone_desk.errors import DeveloperModeRequiredError, NoDeviceError, NoUsbDeviceError


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
        wifi_on: bool = False,
        wifi_setter: bool = True,
    ) -> None:
        self.paired = paired
        self.product_version = product_version
        self.display_name = display_name
        self.udid = "00008030-001"
        self._developer_mode = developer_mode
        self._wifi_on = wifi_on
        self._wifi_setter = wifi_setter
        self.wifi_sets: list[bool] = []
        self.closed = False

    async def get_developer_mode_status(self) -> bool:
        return self._developer_mode

    async def get_enable_wifi_connections(self) -> bool:
        return self._wifi_on

    async def set_enable_wifi_connections(self, value: bool) -> None:
        if not self._wifi_setter:
            raise RuntimeError("wifi setter exploded")
        self.wifi_sets.append(bool(value))
        self._wifi_on = bool(value)

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


def test_picker_prefers_usb_over_network_for_same_serial() -> None:
    usb = FakeMuxDevice("00008030-001", "USB")
    wifi = FakeMuxDevice("00008030-001", "Network")
    picked = pick_usbmux_device([wifi, usb], "00008030-001")
    assert picked is usb
    assert usbmux_connection_type(picked) == "USB"
    assert transport_label(wifi) == "WiFi"


def test_picker_uses_network_when_only_network_is_present() -> None:
    wifi = FakeMuxDevice("00008030-001", "Network")
    picked = pick_usbmux_device([wifi])
    assert picked is wifi
    assert usbmux_connection_type(picked) == "Network"


def test_no_usb_error_is_no_device_error() -> None:
    assert NoUsbDeviceError is NoDeviceError
    assert issubclass(NoDeviceError, Exception)


@pytest.mark.asyncio
async def test_ensure_wifi_connections_sets_when_off() -> None:
    lockdown = FakeLockdown(wifi_on=False)
    assert await ensure_wifi_connections(lockdown) is True
    assert lockdown.wifi_sets == [True]


@pytest.mark.asyncio
async def test_ensure_wifi_connections_skips_when_already_on() -> None:
    lockdown = FakeLockdown(wifi_on=True)
    assert await ensure_wifi_connections(lockdown) is True
    assert lockdown.wifi_sets == []


@pytest.mark.asyncio
async def test_ensure_wifi_connections_soft_fails() -> None:
    lockdown = FakeLockdown(wifi_on=False, wifi_setter=False)
    assert await ensure_wifi_connections(lockdown) is False
    bare = types.SimpleNamespace()
    assert await ensure_wifi_connections(bare) is False


@pytest.mark.asyncio
async def test_connect_uses_network_when_only_network_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lockdown = FakeLockdown(developer_mode=False)
    calls: list[dict[str, Any]] = []
    _install_pymd3(
        monkeypatch,
        lockdown=lockdown,
        devices=[FakeMuxDevice("00008030-001", "Network")],
        create_calls=calls,
    )
    monkeypatch.setattr("iphone_desk.device.reveal_developer_mode_option", _async_true)
    session = DeviceSession()
    statuses: list[str] = []
    with pytest.raises(DeveloperModeRequiredError):
        await session.connect(prefer_hevc=False, on_status=statuses.append)
    assert calls[0]["connection_type"] == "Network"
    assert lockdown.wifi_sets == [True]
    assert any("Pairing over WiFi" in item for item in statuses)
    await session.close()


@pytest.mark.asyncio
async def test_connect_prefers_usb_when_both_visible(monkeypatch: pytest.MonkeyPatch) -> None:
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
        await session.connect(prefer_hevc=False, on_status=statuses.append)
    assert calls[0]["connection_type"] == "USB"
    assert lockdown.wifi_sets == [True]
    assert any("Pairing over USB" in item for item in statuses)
    await session.close()


@pytest.mark.asyncio
async def test_wifi_enable_missing_does_not_break_usb(monkeypatch: pytest.MonkeyPatch) -> None:
    lockdown = FakeLockdown(developer_mode=False)
    lockdown.set_enable_wifi_connections = None
    lockdown.get_enable_wifi_connections = None
    calls: list[dict[str, Any]] = []
    _install_pymd3(
        monkeypatch,
        lockdown=lockdown,
        devices=[FakeMuxDevice("00008030-001", "USB")],
        create_calls=calls,
    )
    monkeypatch.setattr("iphone_desk.device.reveal_developer_mode_option", _async_true)
    session = DeviceSession()
    with pytest.raises(DeveloperModeRequiredError):
        await session.connect(prefer_hevc=False)
    assert calls[0]["connection_type"] == "USB"
    await session.close()


@pytest.mark.asyncio
async def test_connect_without_devices_mentions_usb_and_wifi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lockdown = FakeLockdown()
    _install_pymd3(monkeypatch, lockdown=lockdown, devices=[], create_calls=[])
    session = DeviceSession()
    with pytest.raises(NoDeviceError) as caught:
        await session.connect(prefer_hevc=False)
    assert "USB" in str(caught.value)
    assert "WiFi" in str(caught.value)
    assert "wake" in str(caught.value).lower()
    await session.close()


@pytest.mark.asyncio
async def test_probe_accepts_network_device(monkeypatch: pytest.MonkeyPatch) -> None:
    lockdown = FakeLockdown(paired=True, developer_mode=True)
    calls: list[dict[str, Any]] = []
    _install_pymd3(
        monkeypatch,
        lockdown=lockdown,
        devices=[FakeMuxDevice("00008030-001", "Network")],
        create_calls=calls,
    )
    monkeypatch.setattr("iphone_desk.device.reveal_developer_mode_option", _async_true)
    status = await probe_checklist()
    assert status.usb_present is False
    assert status.wifi_present is True
    assert status.ready_to_connect()
    assert status.paired is True
    assert calls[0]["connection_type"] == "Network"
    assert lockdown.wifi_sets == [True]
    assert "WiFi" in status.detail
    assert any(label.endswith("(WiFi)") for label in status.device_labels)


@pytest.mark.asyncio
async def test_probe_prefers_usb_when_both_visible(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert status.wifi_present is True
    assert calls[0]["connection_type"] == "USB"
    assert "USB and WiFi" in status.detail


@pytest.mark.asyncio
async def test_probe_empty_mentions_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_pymd3(monkeypatch, lockdown=FakeLockdown(), devices=[], create_calls=[])
    status = await probe_checklist()
    assert status.detail == NO_DEVICE_STATUS
    assert not status.ready_to_connect()


async def _async_true(_lockdown: Any) -> bool:
    return True
