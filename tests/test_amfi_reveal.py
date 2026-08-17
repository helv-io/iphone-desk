from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from iphone_desk.checklist import phone_helper_missing_detail, phone_helper_missing_error
from iphone_desk.device import (
    DEVELOPER_MODE_OFF_AFTER_REVEAL,
    DeviceSession,
    probe_checklist,
    reveal_developer_mode_option,
)
from iphone_desk.errors import DeveloperModeRequiredError, DriverMissingError


class FakeAmfiService:
    instances: list[FakeAmfiService] = []
    reveal_calls: list[Any] = []
    enable_calls: list[Any] = []
    accept_calls: list[Any] = []
    fail_reveal = False

    def __init__(self, lockdown: Any) -> None:
        self.lockdown = lockdown
        type(self).instances.append(self)

    async def reveal_developer_mode_option_in_ui(self) -> None:
        type(self).reveal_calls.append(self.lockdown)
        if type(self).fail_reveal:
            raise RuntimeError("amfi reveal failed")

    async def enable_developer_mode(self, enable_post_restart: bool = True) -> None:
        type(self).enable_calls.append(enable_post_restart)
        raise AssertionError("enable_developer_mode must not be called")

    async def enable_developer_mode_post_restart(self) -> None:
        type(self).accept_calls.append(True)
        raise AssertionError("enable_developer_mode_post_restart must not be called")

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.reveal_calls = []
        cls.enable_calls = []
        cls.accept_calls = []
        cls.fail_reveal = False


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
        self.plist_sends: list[dict[str, Any]] = []

    async def get_developer_mode_status(self) -> bool:
        return self._developer_mode

    async def close(self) -> None:
        self.closed = True

    async def start_lockdown_service(self, name: str) -> FakeLockdown:
        self.service_name = name
        return self

    async def send_recv_plist(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.plist_sends.append(payload)
        return {"success": True}


class FakeUsbDevice:
    serial = "00008030-001"
    is_usb = True
    connection_type = "USB"


def _install_pymd3(monkeypatch: pytest.MonkeyPatch, *, lockdown: FakeLockdown) -> None:
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

    async def list_devices() -> list[FakeUsbDevice]:
        return [FakeUsbDevice()]

    async def create_using_usbmux(**_kwargs: Any) -> FakeLockdown:
        return lockdown

    lockdown_mod = types.ModuleType("pymobiledevice3.lockdown")
    lockdown_mod.create_using_usbmux = create_using_usbmux  # type: ignore[attr-defined]
    usbmux_mod = types.ModuleType("pymobiledevice3.usbmux")
    usbmux_mod.create_mux = create_mux  # type: ignore[attr-defined]
    usbmux_mod.list_devices = list_devices  # type: ignore[attr-defined]
    amfi_mod = types.ModuleType("pymobiledevice3.services.amfi")
    amfi_mod.AmfiService = FakeAmfiService  # type: ignore[attr-defined]
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


@pytest.fixture
def amfi(monkeypatch: pytest.MonkeyPatch) -> type[FakeAmfiService]:
    FakeAmfiService.reset()
    monkeypatch.setattr("iphone_desk.device._load_amfi_service", lambda: FakeAmfiService)
    return FakeAmfiService


@pytest.mark.asyncio
async def test_reveal_uses_named_method_not_enable(amfi: type[FakeAmfiService]) -> None:
    lockdown = FakeLockdown()
    assert await reveal_developer_mode_option(lockdown) is True
    assert amfi.reveal_calls == [lockdown]
    assert amfi.enable_calls == []
    assert amfi.accept_calls == []


@pytest.mark.asyncio
async def test_reveal_plist_fallback_sends_action_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    class PlistOnlyAmfi:
        DEVELOPER_MODE_REVEAL = 0
        SERVICE_NAME = "com.apple.amfi.lockdown"

        def __init__(self, lockdown: FakeLockdown) -> None:
            self._lockdown = lockdown

    monkeypatch.setattr("iphone_desk.device._load_amfi_service", lambda: PlistOnlyAmfi)
    lockdown = FakeLockdown()
    assert await reveal_developer_mode_option(lockdown) is True
    assert lockdown.plist_sends == [{"action": 0}]


@pytest.mark.asyncio
async def test_probe_reveals_when_paired(
    monkeypatch: pytest.MonkeyPatch, amfi: type[FakeAmfiService]
) -> None:
    lockdown = FakeLockdown(paired=True, developer_mode=False)
    _install_pymd3(monkeypatch, lockdown=lockdown)
    status = await probe_checklist()
    assert status.paired is True
    assert status.developer_mode is False
    assert amfi.reveal_calls == [lockdown]
    assert amfi.enable_calls == []
    assert "asked iOS to show Developer Mode" in status.detail


@pytest.mark.asyncio
async def test_probe_survives_reveal_failure(
    monkeypatch: pytest.MonkeyPatch, amfi: type[FakeAmfiService]
) -> None:
    amfi.fail_reveal = True
    lockdown = FakeLockdown(paired=True, developer_mode=False)
    _install_pymd3(monkeypatch, lockdown=lockdown)
    status = await probe_checklist()
    assert status.developer_mode is False
    assert "Privacy & Security" in status.detail
    assert status.apple_mobile_device is True


@pytest.mark.asyncio
async def test_connect_reveals_then_raises_when_developer_mode_off(
    monkeypatch: pytest.MonkeyPatch, amfi: type[FakeAmfiService]
) -> None:
    lockdown = FakeLockdown(paired=True, developer_mode=False)
    _install_pymd3(monkeypatch, lockdown=lockdown)
    session = DeviceSession()
    with pytest.raises(DeveloperModeRequiredError) as caught:
        await session.connect(prefer_hevc=False)
    assert str(caught.value) == DEVELOPER_MODE_OFF_AFTER_REVEAL
    assert amfi.reveal_calls == [lockdown]
    assert amfi.enable_calls == []
    await session.close()


def test_device_module_never_enables_or_accepts_developer_mode() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath("iphone_desk", "device.py").read_text()
    assert "reveal_developer_mode_option_in_ui" in text
    assert "enable_developer_mode" not in text
    assert "DEVELOPER_MODE_ENABLE" not in text
    assert "DEVELOPER_MODE_ACCEPT" not in text
    assert "phone_helper_missing_detail" in text
    assert "phone_helper_missing_error" in text


def _install_pymd3_without_mux(monkeypatch: pytest.MonkeyPatch) -> type[Exception]:
    exceptions = types.ModuleType("pymobiledevice3.exceptions")
    failed = type("ConnectionFailedToUsbmuxdError", (Exception,), {})
    setattr(exceptions, "ConnectionFailedToUsbmuxdError", failed)
    for name in (
        "NotPairedError",
        "PairingDialogResponsePendingError",
        "PasswordRequiredError",
        "UserDeniedPairingError",
        "AlreadyMountedError",
        "DeveloperModeIsNotEnabledError",
    ):
        setattr(exceptions, name, type(name, (Exception,), {}))

    async def create_mux() -> Any:
        raise failed("no mux")

    async def list_devices() -> list[Any]:
        raise failed("no mux")

    async def create_using_usbmux(**_kwargs: Any) -> Any:
        raise failed("no mux")

    lockdown_mod = types.ModuleType("pymobiledevice3.lockdown")
    lockdown_mod.create_using_usbmux = create_using_usbmux  # type: ignore[attr-defined]
    usbmux_mod = types.ModuleType("pymobiledevice3.usbmux")
    usbmux_mod.create_mux = create_mux  # type: ignore[attr-defined]
    usbmux_mod.list_devices = list_devices  # type: ignore[attr-defined]
    root = types.ModuleType("pymobiledevice3")
    for name, mod in {
        "pymobiledevice3": root,
        "pymobiledevice3.exceptions": exceptions,
        "pymobiledevice3.lockdown": lockdown_mod,
        "pymobiledevice3.usbmux": usbmux_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return failed


@pytest.mark.asyncio
async def test_probe_helper_missing_uses_os_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_pymd3_without_mux(monkeypatch)
    status = await probe_checklist()
    assert status.apple_mobile_device is False
    assert status.detail == phone_helper_missing_detail()


@pytest.mark.asyncio
async def test_connect_helper_missing_uses_os_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_pymd3_without_mux(monkeypatch)
    session = DeviceSession()
    with pytest.raises(DriverMissingError) as caught:
        await session.connect(prefer_hevc=False)
    assert str(caught.value) == phone_helper_missing_error()
    await session.close()
