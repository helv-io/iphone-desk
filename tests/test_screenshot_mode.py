from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iphone_desk.device import DeviceSession
from iphone_desk.errors import TOUCH_BLOCKED_STATUS
from iphone_desk.video_modes import (
    VIDEO_MODE_AUTO,
    VIDEO_MODE_CORE,
    VIDEO_MODE_DVT,
    VIDEO_MODE_HEVC,
    VIDEO_MODE_SCREENSHOTR,
)

HELVIO_STARTMEDIASTREAM = (
    "Failed to invoke: com.apple.coredevice.feature.startmediastream. "
    "Got error: {'CoreDevice.error': {'code': 9021, "
    "'userInfo': {'NSLocalizedDescription': "
    "'Remote control requires iOS 27.0 or later on this device.'}}}"
)

FORBIDDEN = ("touch_session(", "ScreenStreamServer(", "start_video_stream(", "startmediastream")


def _fn_body(name: str) -> str:
    text = Path(__file__).resolve().parents[1].joinpath("iphone_desk", "device.py").read_text()
    start = text.index(f"async def {name}")
    nxt = text.find("\n    async def ", start + 1)
    return text[start:nxt] if nxt != -1 else text[start:]


def test_still_mode_sources_do_not_open_stream() -> None:
    for name in ("_start_dvt_stills", "_start_core_stills", "_start_screenshotr", "_screenshot_loop"):
        body = _fn_body(name)
        for token in FORBIDDEN:
            assert token not in body, f"{name} contains {token}"
        assert "from pymobiledevice3" not in body


class FakeService:
    opened: list[str] = []

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, rsd: Any = None, lockdown: Any = None) -> FakeService:
        self.rsd = rsd
        self.lockdown = lockdown
        return self

    async def __aenter__(self) -> FakeService:
        type(self).opened.append(self.name)
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def capture_screenshot(self) -> dict[str, bytes]:
        return {"image": b"\x89PNG"}

    async def get_screenshot(self) -> bytes:
        return b"\x89PNG"

    async def take_screenshot(self) -> bytes:
        return b"\x89PNG"

    @classmethod
    def reset(cls) -> None:
        cls.opened = []


@pytest.mark.asyncio
async def test_dvt_mode_does_not_open_touch_session(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeService.reset()
    indigo = FakeService("indigo")
    hid = FakeService("hid")
    dvt = FakeService("dvt")
    shot = FakeService("shot")
    monkeypatch.setattr("iphone_desk.device._load_dvt_screenshot", lambda: (dvt, shot))
    monkeypatch.setattr("iphone_desk.device._load_indigo_hid", lambda: indigo)
    monkeypatch.setattr("iphone_desk.device._load_universal_hid", lambda: hid)
    monkeypatch.setattr(
        "iphone_desk.device._load_screen_capture",
        lambda: (_ for _ in ()).throw(AssertionError("Core Device is a different mode")),
    )

    statuses: list[str] = []
    session = DeviceSession()
    session._rsd = object()
    await session._start_named_mode(VIDEO_MODE_DVT, statuses.append)

    assert "dvt" in FakeService.opened
    assert "shot" in FakeService.opened
    assert session._shot_task is not None
    assert session._picture_mode == VIDEO_MODE_DVT
    await session.close()


@pytest.mark.asyncio
async def test_explicit_hevc_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []

    async def boom(self: DeviceSession, *, on_status: Any) -> None:
        raise RuntimeError(HELVIO_STARTMEDIASTREAM)

    async def shots(self: DeviceSession, on_status: Any) -> None:
        started.append("dvt")

    monkeypatch.setattr(DeviceSession, "_start_hevc", boom)
    monkeypatch.setattr(DeviceSession, "_start_dvt_stills", shots)
    session = DeviceSession()
    with pytest.raises(RuntimeError, match="9021"):
        await session._start_screen(VIDEO_MODE_HEVC, lambda _m: None)
    assert started == []


@pytest.mark.asyncio
async def test_auto_falls_back_and_names_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []

    async def boom(self: DeviceSession, *, on_status: Any) -> None:
        raise RuntimeError(HELVIO_STARTMEDIASTREAM)

    async def dvt(self: DeviceSession, on_status: Any) -> None:
        started.append("dvt")
        on_status("dvt ready")

    monkeypatch.setattr(DeviceSession, "_start_hevc", boom)
    monkeypatch.setattr(DeviceSession, "_start_dvt_stills", dvt)
    statuses: list[str] = []
    session = DeviceSession()
    mode = await session._start_screen(VIDEO_MODE_AUTO, statuses.append)
    assert mode == VIDEO_MODE_DVT
    assert started == ["dvt"]
    assert any("DVT screenshots" in item for item in statuses)


@pytest.mark.asyncio
async def test_core_mode_uses_screencapture(monkeypatch: pytest.MonkeyPatch) -> None:
    class OneShotCapture:
        opened = 0
        closed = 0

        def __call__(self, rsd: Any) -> OneShotCapture:
            return self

        async def __aenter__(self) -> OneShotCapture:
            type(self).opened += 1
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            type(self).closed += 1

        async def capture_screenshot(self) -> dict[str, bytes]:
            return {"image": b"\x89PNG"}

    monkeypatch.setattr(
        "iphone_desk.device._load_dvt_screenshot",
        lambda: (_ for _ in ()).throw(AssertionError("DVT is a different mode")),
    )
    monkeypatch.setattr("iphone_desk.device._load_screen_capture", lambda: OneShotCapture())

    session = DeviceSession()
    session._rsd = object()
    statuses: list[str] = []
    await session._start_named_mode(VIDEO_MODE_CORE, statuses.append)
    assert session._screencapture_oneshot is True
    assert session._capture_backend == "screencapture"
    assert OneShotCapture.opened == 1
    assert OneShotCapture.closed == 1
    frame = await session._capture_still()
    assert frame.startswith(b"\x89PNG")
    assert OneShotCapture.opened == 2
    assert any("Core Device" in item or "screen-capture" in item for item in statuses)
    await session.close()


@pytest.mark.asyncio
async def test_screenshotr_mode_uses_lockdown(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeShot:
        def __init__(self, lockdown: Any) -> None:
            self.lockdown = lockdown

        async def take_screenshot(self) -> bytes:
            return b"\x89PNG"

    monkeypatch.setattr("iphone_desk.device._load_screenshotr", lambda: FakeShot)
    session = DeviceSession()
    session._lockdown = object()
    statuses: list[str] = []
    await session._start_named_mode(VIDEO_MODE_SCREENSHOTR, statuses.append)
    assert session._capture_backend == "screenshotr"
    assert session._picture_mode == VIDEO_MODE_SCREENSHOTR
    frame = await session._capture_still()
    assert frame.startswith(b"\x89PNG")
    await session.close()


@pytest.mark.asyncio
async def test_switch_restores_previous_mode_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []

    async def dvt(self: DeviceSession, on_status: Any) -> None:
        started.append("dvt")
        self._picture_mode = VIDEO_MODE_DVT

    async def boom(self: DeviceSession, *, on_status: Any) -> None:
        started.append("hevc")
        raise RuntimeError(HELVIO_STARTMEDIASTREAM)

    async def stop(self: DeviceSession) -> None:
        self._picture_mode = ""

    monkeypatch.setattr(DeviceSession, "_start_dvt_stills", dvt)
    monkeypatch.setattr(DeviceSession, "_start_hevc", boom)
    monkeypatch.setattr(DeviceSession, "_stop_picture", stop)
    session = DeviceSession()
    session._rsd = object()
    session._picture_mode = VIDEO_MODE_DVT
    session.summary = None
    with pytest.raises(RuntimeError, match="9021"):
        await session.switch_picture(VIDEO_MODE_HEVC)
    assert started == ["hevc", "dvt"]


@pytest.mark.asyncio
async def test_tap_without_hid_stays_human() -> None:
    session = DeviceSession()
    session.touch_available = False
    with pytest.raises(Exception) as caught:
        await session.tap_hid(1, 2)
    assert str(caught.value) == TOUCH_BLOCKED_STATUS
    assert "bplist" not in str(caught.value)
