from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iphone_desk.device import DeviceSession
from iphone_desk.errors import TOUCH_BLOCKED_STATUS

HELVIO_STARTMEDIASTREAM = (
    "Failed to invoke: com.apple.coredevice.feature.startmediastream. "
    "Got error: {'CoreDevice.error': {'code': 9021, "
    "'userInfo': {'NSLocalizedDescription': "
    "'Remote control requires iOS 27.0 or later on this device.'}}}"
)


class FakeService:
    opened: list[str] = []

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, rsd: Any) -> FakeService:
        self.rsd = rsd
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

    @classmethod
    def reset(cls) -> None:
        cls.opened = []


def test_screenshot_mode_source_does_not_open_touch_session() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("iphone_desk", "device.py").read_text()
    start = text.index("async def _start_screenshot_mode")
    end = text.index("async def _open_indigo_buttons")
    body = text[start:end]
    assert "touch_session(" not in body
    assert "ScreenStreamServer(" not in body
    assert "start_video_stream(" not in body
    assert "from pymobiledevice3" not in body


@pytest.mark.asyncio
async def test_screenshot_connect_does_not_open_touch_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeService.reset()
    capture = FakeService("capture")
    indigo = FakeService("indigo")
    hid = FakeService("hid")
    touch_calls: list[Any] = []

    def touch_session(rsd: Any) -> None:
        touch_calls.append(rsd)
        raise AssertionError("touch_session must not be used in screenshot mode")

    monkeypatch.setattr("iphone_desk.device._load_screen_capture", lambda: capture)
    monkeypatch.setattr("iphone_desk.device._load_indigo_hid", lambda: indigo)
    monkeypatch.setattr("iphone_desk.device._load_universal_hid", lambda: hid)
    monkeypatch.setattr(
        "iphone_desk.device._load_dvt_screenshot",
        lambda: (_ for _ in ()).throw(AssertionError("DVT should not be needed")),
    )

    statuses: list[str] = []
    session = DeviceSession()
    session._rsd = object()
    await session._start_screenshot_mode(8.0, None, statuses.append)

    assert touch_calls == []
    assert "capture" in FakeService.opened
    assert "indigo" in FakeService.opened
    assert "hid" in FakeService.opened
    assert session._shot_task is not None
    assert session.touch_available is True
    await session.close()


@pytest.mark.asyncio
async def test_startmediastream_ios27_falls_back_to_screenshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []

    async def boom(self: DeviceSession, *, on_status: Any) -> None:
        raise RuntimeError(HELVIO_STARTMEDIASTREAM)

    async def shots(self: DeviceSession, fps: float, on_frame: Any, on_status: Any) -> None:
        started.append("screenshot")
        on_status("screenshot ready")

    monkeypatch.setattr(DeviceSession, "_start_hevc", boom)
    monkeypatch.setattr(DeviceSession, "_start_screenshot_mode", shots)

    statuses: list[str] = []
    session = DeviceSession()
    mode = await session._start_screen(
        prefer_hevc=True,
        screenshot_fps=8.0,
        on_frame=None,
        on_status=statuses.append,
    )
    assert mode == "screenshot"
    assert started == ["screenshot"]
    assert any("screenshot" in item.lower() for item in statuses)
    assert all("bplist" not in item for item in statuses)
    assert all("9021" not in item for item in statuses)


@pytest.mark.asyncio
async def test_screenshot_only_skips_hevc_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = 0
    started: list[str] = []

    async def probe(self: DeviceSession) -> None:
        nonlocal probes
        probes += 1

    async def shots(self: DeviceSession, fps: float, on_frame: Any, on_status: Any) -> None:
        started.append("screenshot")

    monkeypatch.setattr(DeviceSession, "_probe_remote_control_video", probe)
    monkeypatch.setattr(DeviceSession, "_start_screenshot_mode", shots)
    session = DeviceSession()
    mode = await session._start_screen(
        prefer_hevc=False,
        screenshot_fps=8.0,
        on_frame=None,
        on_status=lambda _m: None,
    )
    assert mode == "screenshot"
    assert probes == 0
    assert started == ["screenshot"]


@pytest.mark.asyncio
async def test_tap_without_hid_stays_human(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DeviceSession()
    session.touch_available = False
    with pytest.raises(Exception) as caught:
        await session.tap_hid(1, 2)
    assert str(caught.value) == TOUCH_BLOCKED_STATUS
    assert "bplist" not in str(caught.value)
