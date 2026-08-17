"""Latest-wins HEVC to BGRA decode.

Based on pymobiledevice3 ``hevc_av.HevcToBgraTranscoder`` (commit 7cfde64,
June 2026). That module is the serve-vnc Windows/Linux PyAV path. This
wrapper keeps the same feed / on_frame / close surface, drops queued
access units so the UI never paints a backlog, and can force software
libav or try a hardware hwaccel first.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import sys
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

LiveFrameCallback = Callable[[bytes], None]


def _hwaccel_names() -> list[str]:
    if sys.platform == "win32":
        return ["d3d11va", "dxva2"]
    if sys.platform.startswith("linux"):
        return ["vaapi", "vdpau"]
    return []


def _parse_sps_size(sps: bytes) -> tuple[int, int]:
    try:
        from pymobiledevice3.remote.core_device.hevc_rps import parse_sps, remove_emulation_prevention

        state = parse_sps(remove_emulation_prevention(sps[2:]))
        width = int(state.pic_width_in_luma_samples)
        height = int(state.pic_height_in_luma_samples)
        if width > 0 and height > 0:
            return width, height
    except Exception as exc:
        logger.debug("SPS size parse failed: %s", exc)
    return 0, 0


def _open_codec(decoder: str) -> Any:
    import av
    import av.codec

    if decoder != "software":
        for name in _hwaccel_names():
            codec = _try_hw_codec(av, name)
            if codec is not None:
                logger.info("HEVC decoder: PyAV %s", name)
                return codec
    codec = av.codec.CodecContext.create("hevc", "r")
    logger.info("HEVC decoder: PyAV software")
    return codec


def _try_hw_codec(av_mod: Any, name: str) -> Any:
    try:
        hwaccel = getattr(getattr(av_mod, "codec", None), "hwaccel", None)
        factory = getattr(hwaccel, "HWAccel", None) if hwaccel is not None else None
        if factory is None:
            return None
        accel = factory(device_type=name)
        codec = av_mod.codec.CodecContext.create("hevc", "r")
        setter = getattr(codec, "hwaccel", None)
        if setter is None:
            with contextlib.suppress(Exception):
                codec.options = {"hwaccel": name}
            return codec
        try:
            codec.hwaccel = accel
        except Exception:
            with contextlib.suppress(Exception):
                codec = av_mod.codec.CodecContext.create("hevc", "r", hwaccel=accel)
        return codec
    except Exception as exc:
        logger.debug("PyAV hwaccel %s unavailable: %s", name, exc)
        return None


class LatestHevcTranscoder:
    """Annex-B HEVC to raw BGRA. Latest access unit wins."""

    def __init__(
        self,
        vps: bytes,
        sps: bytes,
        pps: bytes,
        *,
        on_frame: LiveFrameCallback,
        on_decode_error: Optional[Callable[[], None]] = None,
        decoder: str = "auto",
    ) -> None:
        self.width, self.height = _parse_sps_size(sps)
        self._on_frame = on_frame
        self._on_decode_error = on_decode_error
        self._codec = _open_codec(decoder)
        self._pending: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="iphone-desk-hevc", daemon=True)
        try:
            import av

            ps_annexb = b"".join(b"\x00\x00\x00\x01" + nal for nal in (vps, sps, pps))
            with contextlib.suppress(Exception):
                list(self._codec.decode(av.Packet(ps_annexb)))
        except Exception as exc:
            logger.debug("HEVC parameter-set seed failed: %s", exc)
        self._thread.start()

    def feed(self, annexb: bytes) -> None:
        if self._stop.is_set():
            return
        while True:
            try:
                self._pending.put_nowait(annexb)
                return
            except queue.Full:
                with contextlib.suppress(queue.Empty):
                    self._pending.get_nowait()

    def close(self) -> None:
        self._stop.set()
        with contextlib.suppress(Exception):
            self._pending.put_nowait(None)
        self._thread.join(timeout=2.0)
        closer = getattr(self._codec, "close", None)
        if callable(closer):
            with contextlib.suppress(Exception):
                closer()

    def _emit(self, frame: Any) -> None:
        width = self.width or int(getattr(frame, "width", 0) or 0)
        height = self.height or int(getattr(frame, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return
        bgra_frame = frame.reformat(width=width, height=height, format="bgra")
        plane = bgra_frame.planes[0]
        ba = bytearray(bytes(plane))
        ba[3::4] = b"\xff" * (len(ba) // 4)
        self.width = width
        self.height = height
        self._on_frame(bytes(ba))

    def _fire_error(self) -> None:
        cb = self._on_decode_error
        if cb is None:
            return
        with contextlib.suppress(Exception):
            cb()

    def _run(self) -> None:
        import av
        import av.error

        while not self._stop.is_set():
            try:
                item = self._pending.get(timeout=0.05)
            except queue.Empty:
                continue
            if item is None:
                return
            try:
                frames = list(self._codec.decode(av.Packet(item)))
            except av.error.InvalidDataError as exc:
                logger.debug("HEVC AU rejected: %s", exc)
                self._fire_error()
                continue
            except Exception as exc:
                logger.warning("HEVC decode failed: %s", exc)
                self._fire_error()
                continue
            if not frames:
                self._fire_error()
                continue
            for frame in frames:
                try:
                    self._emit(frame)
                except Exception as exc:
                    logger.warning("HEVC emit failed: %s", exc)
                    self._fire_error()
