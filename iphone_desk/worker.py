"""Run the asyncio device session on a background thread."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal, Slot

from iphone_desk.device import ConnectedDevice, DeviceSession, probe_checklist
from iphone_desk.errors import DeskError, humanize_device_error

logger = logging.getLogger(__name__)


class DeviceWorker(QObject):
    status = Signal(str)
    checklist = Signal(object)
    connected = Signal(object)
    frame = Signal(bytes)
    hevc_ready = Signal(str)
    failed = Signal(str)
    disconnected = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[DeviceSession] = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, name="iphone-desk-device", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self) -> None:
        loop = self._loop
        if loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
        try:
            fut.result(timeout=8)
        except Exception:
            logger.exception("device worker shutdown failed")
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=4)
        self._thread = None
        self._loop = None

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()
        loop.close()

    def _submit(self, coro: Any) -> None:
        if self._loop is None:
            self.failed.emit("Device worker is not running.")
            return
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    @Slot()
    def refresh_checklist(self) -> None:
        self._submit(self._refresh_checklist())

    @Slot(bool)
    def connect_device(self, prefer_hevc: bool) -> None:
        self._submit(self._connect(prefer_hevc))

    @Slot()
    def disconnect_device(self) -> None:
        self._submit(self._disconnect())

    @Slot(int, int)
    def tap(self, x: int, y: int) -> None:
        self._submit(self._call_hid("tap", x, y))

    @Slot(int, int, int, int)
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._submit(self._call_hid("drag", x1, y1, x2, y2))

    @Slot(str)
    def button(self, name: str) -> None:
        self._submit(self._call_hid("button", name))

    async def _refresh_checklist(self) -> None:
        try:
            status = await probe_checklist()
        except Exception as exc:
            self.failed.emit(humanize_device_error(exc))
            return
        self.checklist.emit(status)
        if status.detail:
            self.status.emit(status.detail)

    async def _connect(self, prefer_hevc: bool) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        session = DeviceSession()

        def on_status(message: str) -> None:
            self.status.emit(message)

        def on_frame(png: bytes) -> None:
            self.frame.emit(png)

        try:
            summary = await session.connect(
                prefer_hevc=prefer_hevc,
                on_frame=on_frame,
                on_status=on_status,
            )
        except DeskError as exc:
            await session.close()
            self.failed.emit(humanize_device_error(exc))
            return
        except Exception as exc:
            await session.close()
            logger.exception("connect failed")
            self.failed.emit(humanize_device_error(exc))
            return
        self._session = session
        self.connected.emit(summary)
        if session.hevc_url:
            self.hevc_ready.emit(session.hevc_url)

    async def _disconnect(self) -> None:
        if self._session is None:
            self.disconnected.emit()
            return
        await self._session.close()
        self._session = None
        self.disconnected.emit()
        self.status.emit("Disconnected.")

    async def _shutdown(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _call_hid(self, kind: str, *args: Any) -> None:
        session = self._session
        if session is None:
            return
        try:
            if kind == "tap":
                await session.tap_hid(int(args[0]), int(args[1]))
            elif kind == "drag":
                await session.drag_hid(int(args[0]), int(args[1]), int(args[2]), int(args[3]))
            elif kind == "button":
                await session.press_button(str(args[0]))
        except Exception as exc:
            self.status.emit(f"Input failed: {humanize_device_error(exc)}")

    def current_summary(self) -> Optional[ConnectedDevice]:
        if self._session is None:
            return None
        return self._session.summary
