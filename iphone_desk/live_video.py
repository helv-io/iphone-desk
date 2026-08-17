"""Decode the iPhone remote-control HEVC stream to BGRA frames.

Apple's serve-web page needs WebCodecs HEVC. Qt WebEngine on Windows does
not decode that, so the old viewer showed a blank canvas while HID still
worked. This pump is the same RTP path as pymobiledevice3's VNC server:
start_video_stream, depacketize Annex-B AUs, decode with PyAV, emit BGRA.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

LiveFrameCallback = Callable[[int, int, bytes], None]

_HEVC_NAL_IDR_W_RADL = 19
_HEVC_NAL_IDR_N_LP = 20
_HEVC_NAL_CRA = 21
_HEVC_NAL_VPS = 32
_HEVC_NAL_SPS = 33
_HEVC_NAL_PPS = 34


def _is_key_nal(nal_type: int) -> bool:
    return nal_type in (_HEVC_NAL_IDR_W_RADL, _HEVC_NAL_IDR_N_LP, _HEVC_NAL_CRA)


def build_rtcp_rr(local_ssrc: int, remote_ssrc: int, highest_seq: int) -> bytes:
    """RFC 3550 receiver report plus empty SDES. The phone reaps the stream without this."""
    rr = struct.pack(
        "!BBHII BBBB IIII",
        0x81,
        0xC9,
        7,
        local_ssrc & 0xFFFFFFFF,
        remote_ssrc & 0xFFFFFFFF,
        0,
        0,
        0,
        0,
        highest_seq & 0xFFFFFFFF,
        0,
        0,
        0,
    )
    sdes = struct.pack("!BBHI BBBB", 0x81, 0xCA, 2, local_ssrc & 0xFFFFFFFF, 0x01, 0x00, 0x00, 0x00)
    return rr + sdes


def build_rtcp_pli(local_ssrc: int, remote_ssrc: int) -> bytes:
    return struct.pack(
        "!BBHII",
        0x81,
        0xCE,
        2,
        local_ssrc & 0xFFFFFFFF,
        remote_ssrc & 0xFFFFFFFF,
    )


class LiveHevcPump:
    """Own one DisplayService video session and push downscaled BGRA frames."""

    def __init__(self, rsd: Any, *, on_frame: LiveFrameCallback, display_id: int = 1) -> None:
        self._rsd = rsd
        self._on_frame = on_frame
        self._display_id = display_id
        self._sender_ip = rsd.service.address[0]
        self._svc: Any = None
        self._session_id: Optional[uuid.UUID] = None
        self._transport: Any = None
        self._transcoder: Any = None
        self._recv_task: Optional[asyncio.Task[None]] = None
        self._rr_task: Optional[asyncio.Task[None]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._local_ssrc = 0
        self._remote_ssrc = 0
        self._rtcp_dest: Optional[tuple[str, int]] = None
        self._rtp_highest_seq = 0
        self._width = 0
        self._height = 0
        self._closed = False

    @property
    def size(self) -> tuple[int, int]:
        return self._width, self._height

    async def start(self) -> None:
        from pymobiledevice3.remote.core_device.display_service import DisplayService
        from pymobiledevice3.remote.core_device.screen_stream import open_media_receiver

        self._loop = asyncio.get_running_loop()
        svc = DisplayService(self._rsd)
        await svc.connect()
        transport = None
        try:
            transport, receiver_ip = open_media_receiver(svc, (8 * 1024 * 1024, 4 * 1024 * 1024))
            answer = await svc.start_video_stream(
                receiver_ip=receiver_ip,
                receiver_port=transport.port,
                sender_ip=self._sender_ip,
                display_id=self._display_id,
                client_session_id=uuid.uuid4(),
                allow_rtcp_fb=False,
                ltrp_enabled=False,
            )
        except Exception:
            if transport is not None:
                with contextlib.suppress(Exception):
                    transport.close()
            with contextlib.suppress(Exception):
                await svc.close()
            raise
        sid = answer["connection"]["options"]["avcMediaStreamOptionClientSessionID"]["uuid"]
        if not isinstance(sid, uuid.UUID):
            sid = uuid.UUID(str(sid))
        cfg = answer["connection"].get("streamConfig", {})
        source_port = int(cfg.get("SourcePort", 0) or 0)
        self._local_ssrc = int(cfg.get("RemoteSSRC", 0) or 0)
        self._remote_ssrc = int(cfg.get("LocalSSRC", 0) or 0)
        self._rtcp_dest = (self._sender_ip, source_port) if source_port else None
        self._svc = svc
        self._session_id = sid
        self._transport = transport
        logger.info(
            "live HEVC up: %sx%s sender_port=%s",
            cfg.get("CustomWidth"),
            cfg.get("CustomHeight"),
            source_port,
        )
        self._recv_task = asyncio.create_task(self._recv_loop(transport), name="iphone-desk-hevc-rtp")
        self._rr_task = asyncio.create_task(self._rr_loop(transport), name="iphone-desk-hevc-rr")

    async def close(self) -> None:
        self._closed = True
        for task in (self._recv_task, self._rr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._recv_task = None
        self._rr_task = None
        if self._transcoder is not None:
            with contextlib.suppress(Exception):
                self._transcoder.close()
            self._transcoder = None
        if self._transport is not None:
            with contextlib.suppress(Exception):
                self._transport.close()
            self._transport = None
        if self._svc is not None and self._session_id is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._svc.stop_media_stream(self._session_id), timeout=3.0)
        if self._svc is not None:
            with contextlib.suppress(Exception):
                await self._svc.close()
        self._svc = None
        self._session_id = None

    def _on_decoded(self, bgra: bytes) -> None:
        width = self._width
        height = self._height
        if self._transcoder is not None:
            width = int(getattr(self._transcoder, "width", width) or width)
            height = int(getattr(self._transcoder, "height", height) or height)
        if width <= 0 or height <= 0:
            return
        self._width = width
        self._height = height
        try:
            from iphone_desk.frames import shrink_bgra

            width, height, preview = shrink_bgra(bgra, width, height)
        except Exception:
            logger.debug("live preview shrink failed", exc_info=True)
            preview = bgra
        loop = self._loop
        if loop is None or self._closed:
            return
        try:
            loop.call_soon_threadsafe(self._deliver, width, height, preview)
        except Exception:
            logger.debug("live frame marshal failed", exc_info=True)

    def _deliver(self, width: int, height: int, bgra: bytes) -> None:
        if self._closed:
            return
        with contextlib.suppress(Exception):
            self._on_frame(width, height, bgra)

    def _on_decode_error(self) -> None:
        loop = self._loop
        if loop is None or self._closed:
            return
        with contextlib.suppress(Exception):
            loop.call_soon_threadsafe(self._request_keyframe)

    def _request_keyframe(self) -> None:
        if self._closed or self._transport is None or self._rtcp_dest is None:
            return
        if not (self._local_ssrc and self._remote_ssrc):
            return
        payload = build_rtcp_pli(self._local_ssrc, self._remote_ssrc)

        async def _send() -> None:
            try:
                await self._transport.sendto(payload, *self._rtcp_dest)
            except Exception:
                logger.debug("live PLI send failed", exc_info=True)

        asyncio.create_task(_send())

    async def _rr_loop(self, transport: Any) -> None:
        while not self._closed:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                return
            if self._rtcp_dest is None or not (self._local_ssrc and self._remote_ssrc):
                continue
            try:
                await transport.sendto(
                    build_rtcp_rr(self._local_ssrc, self._remote_ssrc, self._rtp_highest_seq),
                    *self._rtcp_dest,
                )
            except asyncio.CancelledError:
                return
            except OSError:
                return

    async def _recv_loop(self, transport: Any) -> None:
        from pymobiledevice3.remote.core_device.screen_stream import depacketize_hevc

        fu_buffer = bytearray()
        current_au: list[bytes] = []
        last_seq: Optional[int] = None
        au_corrupt = False
        au_is_key = False
        nals: list[bytes] = []
        cached_vps: Optional[bytes] = None
        cached_sps: Optional[bytes] = None
        cached_pps: Optional[bytes] = None
        while not self._closed:
            try:
                data = await transport.recv()
            except (OSError, asyncio.CancelledError):
                return
            if len(data) < 12:
                continue
            payload_type = data[1] & 0x7F
            if 64 <= payload_type <= 95:
                continue
            marker = (data[1] >> 7) & 1
            cc = data[0] & 0x0F
            header_len = 12 + cc * 4
            if data[0] & 0x10:
                ext_len = int.from_bytes(data[header_len + 2 : header_len + 4], "big")
                header_len += 4 + ext_len * 4
            payload = data[header_len:]
            seq = int.from_bytes(data[2:4], "big")
            cur_ext = self._rtp_highest_seq
            cycles = (cur_ext >> 16) & 0xFFFF
            last_seq16 = cur_ext & 0xFFFF
            if seq < last_seq16 and (last_seq16 - seq) > 0x8000:
                cycles = (cycles + 1) & 0xFFFF
            new_ext = (cycles << 16) | seq
            if cur_ext == 0 or ((new_ext - cur_ext) & 0xFFFFFFFF) < 0x80000000:
                self._rtp_highest_seq = new_ext
            if last_seq is not None and seq != ((last_seq + 1) & 0xFFFF):
                fu_buffer.clear()
                au_corrupt = True
            if last_seq is None or ((seq - last_seq) & 0xFFFF) < 0x8000:
                last_seq = seq
            nals.clear()
            depacketize_hevc(payload, fu_buffer, nals)
            for nal in nals:
                if not nal:
                    continue
                nal_type = (nal[0] >> 1) & 0x3F
                if nal_type == _HEVC_NAL_VPS:
                    cached_vps = bytes(nal)
                elif nal_type == _HEVC_NAL_SPS:
                    cached_sps = bytes(nal)
                elif nal_type == _HEVC_NAL_PPS:
                    cached_pps = bytes(nal)
                elif _is_key_nal(nal_type):
                    au_is_key = True
                current_au.append(nal)
            if not marker:
                continue
            if current_au and not au_corrupt:
                self._feed_au(
                    current_au,
                    au_is_key=au_is_key,
                    vps=cached_vps,
                    sps=cached_sps,
                    pps=cached_pps,
                )
            current_au = []
            au_is_key = False
            au_corrupt = False

    def _feed_au(
        self,
        nals: list[bytes],
        *,
        au_is_key: bool,
        vps: Optional[bytes],
        sps: Optional[bytes],
        pps: Optional[bytes],
    ) -> None:
        if self._transcoder is None:
            if not au_is_key or vps is None or sps is None or pps is None:
                return
            try:
                from pymobiledevice3.remote.core_device.hevc_av import HevcToBgraTranscoder

                self._transcoder = HevcToBgraTranscoder(
                    vps,
                    sps,
                    pps,
                    on_frame=self._on_decoded,
                    on_decode_error=self._on_decode_error,
                )
                self._width = int(self._transcoder.width)
                self._height = int(self._transcoder.height)
                logger.info("HEVC decoder ready: %dx%d", self._width, self._height)
            except Exception:
                logger.exception("HEVC decoder failed to start")
                self._transcoder = None
                return
        annexb = b"".join(b"\x00\x00\x00\x01" + nal for nal in nals)
        try:
            self._transcoder.feed(annexb)
        except Exception:
            logger.debug("HEVC feed failed", exc_info=True)
            self._on_decode_error()
