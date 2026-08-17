"""Talk to a trusted iPhone through pymobiledevice3's public Python API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional

from packaging.version import Version

from iphone_desk.checklist import ChecklistStatus
from iphone_desk.coords import Size
from iphone_desk.display import parse_display_size
from iphone_desk.errors import (
    DeskError,
    DeveloperModeRequiredError,
    DriverMissingError,
    IosVersionError,
    NoUsbDeviceError,
    TOUCH_BLOCKED_STATUS,
    TrustRequiredError,
    humanize_device_error,
    is_remote_control_unsupported,
)
from iphone_desk.hid_actions import drag, press_named_button, tap

logger = logging.getLogger(__name__)

FrameCallback = Callable[[bytes], Awaitable[None] | None]
StatusCallback = Callable[[str], None]

# AMFI action 0 unhides Settings > Privacy & Security > Developer Mode.
# Actions 1 (enable) and 2 (post-restart accept) are intentionally unused.
AMFI_REVEAL_ACTION = 0
AMFI_SERVICE_NAME = "com.apple.amfi.lockdown"

DEVELOPER_MODE_OFF_AFTER_REVEAL = (
    "Developer Mode is off. This PC asked iOS to show the toggle. "
    "Enable it under Settings > Privacy & Security > Developer Mode, restart when iOS asks, then Connect."
)
DEVELOPER_MODE_OFF_IN_SETTINGS = (
    "Developer Mode is off. Enable it in Settings > Privacy & Security > Developer Mode, "
    "restart when iOS asks, then Connect."
)


def _load_amfi_service() -> Any:
    from pymobiledevice3.services.amfi import AmfiService

    return AmfiService


def _load_display_service() -> Any:
    from pymobiledevice3.remote.core_device.display_service import DisplayService

    return DisplayService


def _load_screen_capture() -> Any:
    from pymobiledevice3.remote.core_device.screen_capture_service import ScreenCaptureService

    return ScreenCaptureService


def _load_indigo_hid() -> Any:
    from pymobiledevice3.remote.core_device.hid_service import IndigoHIDService

    return IndigoHIDService


def _load_universal_hid() -> Any:
    from pymobiledevice3.remote.core_device.hid_service import UniversalHIDServiceService

    return UniversalHIDServiceService


def _load_dvt_screenshot() -> tuple[Any, Any]:
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.screenshot import Screenshot

    return DvtProvider, Screenshot


async def _maybe_await(result: Any) -> Any:
    if asyncio.iscoroutine(result):
        return await result
    return result


async def reveal_developer_mode_option(lockdown: Any) -> bool:
    """Ask iOS to show Developer Mode in Settings (AMFI action 0). Never enables it."""
    try:
        amfi_cls = _load_amfi_service()
    except Exception as exc:
        logger.warning("AmfiService is unavailable; cannot reveal Developer Mode: %s", exc)
        return False

    try:
        service = amfi_cls(lockdown)
        reveal = getattr(service, "reveal_developer_mode_option_in_ui", None)
        if callable(reveal):
            await _maybe_await(reveal())
            return True
        await _reveal_developer_mode_via_plist(lockdown, service)
        return True
    except Exception as exc:
        logger.warning("AMFI reveal (action 0) failed: %s", exc)
        return False


async def _reveal_developer_mode_via_plist(lockdown: Any, service: Any) -> None:
    """Older pymobiledevice3 builds only expose the raw AMFI plist send."""
    action = getattr(service, "DEVELOPER_MODE_REVEAL", AMFI_REVEAL_ACTION)
    if action != AMFI_REVEAL_ACTION:
        action = AMFI_REVEAL_ACTION
    name = getattr(service, "SERVICE_NAME", AMFI_SERVICE_NAME)
    conn = await _maybe_await(lockdown.start_lockdown_service(name))
    await _maybe_await(conn.send_recv_plist({"action": action}))


@dataclass(frozen=True)
class ConnectedDevice:
    udid: str
    name: str
    product_version: str
    display: Size
    mode: str
    touch_available: bool = True


def _usb_devices(devices: list[Any]) -> list[Any]:
    return [device for device in devices if getattr(device, "is_usb", False)]


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def probe_checklist() -> ChecklistStatus:
    """Read usbmux, pairing, and Developer Mode without opening a tunnel."""
    from pymobiledevice3.exceptions import (
        ConnectionFailedToUsbmuxdError,
        NotPairedError,
        PairingDialogResponsePendingError,
        PasswordRequiredError,
        UserDeniedPairingError,
    )
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.usbmux import create_mux, list_devices

    try:
        mux = await create_mux()
        await mux.close()
    except ConnectionFailedToUsbmuxdError:
        return ChecklistStatus(
            apple_mobile_device=False,
            usb_present=False,
            paired=None,
            developer_mode=None,
            detail="Apple Mobile Device / usbmux is not reachable. Install iTunes or Apple Devices, then replug USB.",
        )

    devices = await list_devices()
    usb = _usb_devices(devices)
    labels = [f"{device.serial} ({device.connection_type})" for device in usb]
    if not usb:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=False,
            paired=None,
            developer_mode=None,
            device_labels=labels,
            detail="No USB iPhone yet. Plug the cable in and unlock the phone.",
        )

    serial = usb[0].serial
    try:
        lockdown = await create_using_usbmux(
            serial=serial,
            autopair=False,
            connection_type="USB",
        )
    except NotPairedError:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=True,
            paired=False,
            developer_mode=None,
            device_labels=labels,
            detail="The phone is visible but not paired. Unlock it, tap Trust, then Connect.",
        )
    except (PairingDialogResponsePendingError, PasswordRequiredError):
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=True,
            paired=False,
            developer_mode=None,
            device_labels=labels,
            detail="Unlock the iPhone and tap Trust This Computer.",
        )
    except UserDeniedPairingError:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=True,
            paired=False,
            developer_mode=None,
            device_labels=labels,
            detail="Trust was declined on the phone. Unplug, replug, and tap Trust.",
        )
    except Exception as exc:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=True,
            paired=None,
            developer_mode=None,
            device_labels=labels,
            detail=f"USB device seen, lockdown failed: {exc}",
        )

    try:
        paired = bool(getattr(lockdown, "paired", True))
        revealed = False
        if paired:
            revealed = await reveal_developer_mode_option(lockdown)
        developer_mode: Optional[bool]
        try:
            developer_mode = bool(await lockdown.get_developer_mode_status())
        except Exception:
            developer_mode = None
        name = getattr(lockdown, "display_name", None) or serial
        version = getattr(lockdown, "product_version", "?")
        detail = f"Found {name} (iOS {version})."
        if developer_mode is False:
            if revealed:
                detail += (
                    " This PC asked iOS to show Developer Mode. Enable it under "
                    "Settings > Privacy & Security > Developer Mode, then restart when iOS asks."
                )
            else:
                detail += " Developer Mode is off. Turn it on under Settings > Privacy & Security."
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=True,
            paired=paired,
            developer_mode=developer_mode,
            device_labels=labels,
            detail=detail,
        )
    finally:
        with contextlib.suppress(Exception):
            await lockdown.close()


class DeviceSession:
    """Own the lockdown client, userspace tunnel, screen, and HID session."""

    def __init__(self) -> None:
        self.summary: Optional[ConnectedDevice] = None
        self.hevc_url: Optional[str] = None
        self._lockdown: Any = None
        self._tunnel: Any = None
        self._rsd: Any = None
        self._hid: Any = None
        self._buttons: Any = None
        self._capture: Any = None
        self._dvt: Any = None
        self._dvt_shot: Any = None
        self._touch_cm: Any = None
        self._stream_task: Optional[asyncio.Task[None]] = None
        self._shot_task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()
        self._hid_lock = asyncio.Lock()
        self.touch_available = True

    @property
    def display(self) -> Size:
        if self.summary is None:
            return Size(390, 844)
        return self.summary.display

    async def connect(
        self,
        *,
        serial: Optional[str] = None,
        prefer_hevc: bool = True,
        screenshot_fps: float = 8.0,
        on_frame: Optional[FrameCallback] = None,
        on_status: Optional[StatusCallback] = None,
    ) -> ConnectedDevice:
        from pymobiledevice3.exceptions import (
            AlreadyMountedError,
            ConnectionFailedToUsbmuxdError,
            DeveloperModeIsNotEnabledError,
            NotPairedError,
            PairingDialogResponsePendingError,
            PasswordRequiredError,
            UserDeniedPairingError,
        )
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.usbmux import list_devices

        def status(message: str) -> None:
            logger.info(message)
            if on_status is not None:
                on_status(message)

        try:
            devices = await list_devices()
        except ConnectionFailedToUsbmuxdError as exc:
            raise DriverMissingError(
                "Apple Mobile Device / usbmux is not running. Install iTunes or Apple Devices."
            ) from exc

        usb = _usb_devices(devices)
        if not usb:
            raise NoUsbDeviceError("No USB iPhone found. Plug it in and unlock it.")
        target = serial or usb[0].serial
        status(f"Pairing with {target} over USB...")

        try:
            self._lockdown = await create_using_usbmux(
                serial=target,
                autopair=True,
                connection_type="USB",
                pair_timeout=90,
            )
        except PairingDialogResponsePendingError as exc:
            raise TrustRequiredError("Unlock the iPhone and tap Trust This Computer.") from exc
        except UserDeniedPairingError as exc:
            raise TrustRequiredError("The phone declined Trust. Replug and accept the dialog.") from exc
        except PasswordRequiredError as exc:
            raise TrustRequiredError("Unlock the iPhone, then try Connect again.") from exc
        except NotPairedError as exc:
            raise TrustRequiredError("The phone is not paired with this PC.") from exc

        lockdown = self._lockdown
        product_version = str(lockdown.product_version)
        name = str(getattr(lockdown, "display_name", None) or target)
        udid = str(lockdown.udid)

        revealed = await reveal_developer_mode_option(lockdown)
        try:
            developer_mode = bool(await lockdown.get_developer_mode_status())
        except Exception:
            developer_mode = Version(product_version) < Version("16.0")
        if not developer_mode:
            raise DeveloperModeRequiredError(
                DEVELOPER_MODE_OFF_AFTER_REVEAL if revealed else DEVELOPER_MODE_OFF_IN_SETTINGS
            )

        from pymobiledevice3.remote.core_device.device_info import DeviceInfoService
        from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
        from pymobiledevice3.services.mobile_image_mounter import auto_mount

        status("Mounting the Developer Disk Image (cached under ~/.pymobiledevice3)...")
        try:
            await auto_mount(lockdown)
        except AlreadyMountedError:
            status("Developer Disk Image already mounted.")
        except DeveloperModeIsNotEnabledError as exc:
            raise DeveloperModeRequiredError(
                DEVELOPER_MODE_OFF_AFTER_REVEAL if revealed else DEVELOPER_MODE_OFF_IN_SETTINGS
            ) from exc

        if Version(product_version) < Version("17.0"):
            raise IosVersionError(
                f"iOS {product_version} is below 17. CoreDevice screen and HID need iOS 17 or later."
            )

        status("Opening a no-admin userspace RSD tunnel...")
        self._tunnel = UserspaceRsdTunnel(serial=udid, autopair=True)
        self._rsd = await self._tunnel.aopen()

        status("Reading display size via get-display-info...")
        async with DeviceInfoService(self._rsd) as info:
            raw = await info.get_display_info()
        display = parse_display_size(raw)

        mode = await self._start_screen(
            prefer_hevc=prefer_hevc,
            screenshot_fps=screenshot_fps,
            on_frame=on_frame,
            on_status=status,
        )

        self.summary = ConnectedDevice(
            udid=udid,
            name=name,
            product_version=product_version,
            display=display,
            mode=mode,
            touch_available=self.touch_available,
        )
        status(f"Connected to {name} (iOS {product_version}) in {mode} mode.")
        return self.summary

    async def _start_screen(
        self,
        *,
        prefer_hevc: bool,
        screenshot_fps: float,
        on_frame: Optional[FrameCallback],
        on_status: StatusCallback,
    ) -> str:
        if prefer_hevc:
            try:
                await self._start_hevc(on_status=on_status)
                return "hevc"
            except Exception as exc:
                logger.warning("HEVC serve-web failed, using screenshot loop: %s", exc)
                await self._reset_video_and_hid()
                if is_remote_control_unsupported(exc):
                    on_status(
                        "Live remote-control video was rejected by this iPhone. Using the screenshot loop."
                    )
                else:
                    on_status("Live HEVC was not available. Using the screenshot loop.")
                await self._start_screenshot_mode(screenshot_fps, on_frame, on_status)
                return "screenshot"
        await self._start_screenshot_mode(screenshot_fps, on_frame, on_status)
        return "screenshot"

    async def _start_hevc(self, *, on_status: StatusCallback) -> None:
        from pymobiledevice3.remote.core_device.hid_service import (
            IndigoHIDService,
            UniversalHIDServiceService,
        )
        from pymobiledevice3.remote.core_device.screen_stream import ScreenStreamServer

        await self._probe_remote_control_video()

        port = _pick_free_port()
        server = ScreenStreamServer(
            self._rsd,
            bind="127.0.0.1",
            http_port=port,
            audio_default_on=False,
            ltrp_enabled=False,
        )
        self._stream_task = asyncio.create_task(server.serve(), name="iphone-desk-serve-web")
        try:
            await self._watch_hevc_task(self._stream_task, timeout=2.0)
        except Exception:
            await self._stop_stream_task()
            raise
        self.hevc_url = f"http://127.0.0.1:{port}/"
        on_status(f"Live HEVC viewer at {self.hevc_url}")
        try:
            self._hid = await UniversalHIDServiceService(self._rsd).__aenter__()
            self._buttons = await IndigoHIDService(self._rsd).__aenter__()
            self.touch_available = True
        except Exception as exc:
            if is_remote_control_unsupported(exc):
                self.touch_available = False
                on_status(TOUCH_BLOCKED_STATUS)
                return
            raise

    async def _probe_remote_control_video(self) -> None:
        """Call start_video_stream so a 9021 / iOS 27 reject fails before serve-web."""
        display_cls = _load_display_service()
        display = display_cls(self._rsd)
        await display.__aenter__()
        try:
            start = getattr(display, "start_video_stream", None)
            if not callable(start):
                return
            sender_ip = "127.0.0.1"
            address = getattr(getattr(self._rsd, "service", None), "address", None)
            if address:
                sender_ip = str(address[0])
            answer = await _maybe_await(
                start(receiver_ip="127.0.0.1", receiver_port=9, sender_ip=sender_ip)
            )
            stop = getattr(display, "stop_media_stream", None)
            if callable(stop) and isinstance(answer, dict):
                try:
                    client_session_id = answer["connection"]["options"]["avcMediaStreamOptionClientSessionID"][
                        "uuid"
                    ]
                    await _maybe_await(stop(client_session_id))
                except Exception:
                    logger.debug("stop after startmediastream probe failed", exc_info=True)
        finally:
            with contextlib.suppress(Exception):
                await display.__aexit__(None, None, None)

    async def _watch_hevc_task(self, task: asyncio.Task[None], *, timeout: float) -> None:
        done, _pending = await asyncio.wait({task}, timeout=timeout)
        if task not in done:
            return
        if task.cancelled():
            raise DeskError("Live HEVC was cancelled before the viewer was ready.")
        exc = task.exception()
        if exc is not None:
            raise exc
        raise DeskError("Live HEVC ended before the viewer was ready.")

    async def _start_screenshot_mode(
        self,
        fps: float,
        on_frame: Optional[FrameCallback],
        on_status: StatusCallback,
    ) -> None:
        # Screenshot-only: never open touch_session / ScreenStreamServer / startmediastream.
        on_status("Starting screenshot loop (no live video stream)...")
        await self._open_indigo_buttons(on_status)
        await self._open_touch_without_stream(on_status)
        if not await self._open_screenshot_capture(on_status):
            raise DeskError("Could not open screen capture or DVT screenshot.")
        delay = 1.0 / max(fps, 1.0)
        self._shot_task = asyncio.create_task(
            self._screenshot_loop(delay, on_frame),
            name="iphone-desk-screenshots",
        )

    async def _open_indigo_buttons(self, on_status: StatusCallback) -> None:
        try:
            indigo_cls = _load_indigo_hid()
            self._buttons = await indigo_cls(self._rsd).__aenter__()
        except Exception as exc:
            logger.warning("Indigo HID buttons unavailable: %s", exc)
            self._buttons = None
            on_status("Hardware buttons are unavailable on this session.")

    async def _open_touch_without_stream(self, on_status: StatusCallback) -> None:
        """Open Universal HID only. Do not start a media stream to authenticate it."""
        try:
            hid_cls = _load_universal_hid()
            self._hid = await hid_cls(self._rsd).__aenter__()
            self.touch_available = True
        except Exception as exc:
            logger.warning("Universal HID open failed: %s", exc)
            self._hid = None
            self.touch_available = False
            on_status(TOUCH_BLOCKED_STATUS)

    async def _open_screenshot_capture(self, on_status: StatusCallback) -> bool:
        try:
            capture_cls = _load_screen_capture()
            self._capture = await capture_cls(self._rsd).__aenter__()
            return True
        except Exception as exc:
            logger.warning("ScreenCaptureService failed: %s", exc)
            self._capture = None
            on_status("ScreenCaptureService failed. Using DVT screenshot.")
        try:
            await self._ensure_dvt_screenshot()
            return True
        except Exception as exc:
            logger.warning("DVT screenshot failed: %s", exc)
            return False

    async def _reset_video_and_hid(self) -> None:
        await self._stop_stream_task()
        self.hevc_url = None
        for attr in ("_hid", "_buttons", "_touch_cm"):
            obj = getattr(self, attr)
            setattr(self, attr, None)
            if obj is None:
                continue
            with contextlib.suppress(Exception):
                closer = getattr(obj, "__aexit__", None)
                if closer is not None:
                    await closer(None, None, None)

    async def _stop_stream_task(self) -> None:
        task = self._stream_task
        self._stream_task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _screenshot_loop(self, delay: float, on_frame: Optional[FrameCallback]) -> None:
        while not self._stop.is_set():
            try:
                png = await self._capture_png()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("screenshot failed: %s", exc)
                await asyncio.sleep(delay)
                continue
            if on_frame is not None and png:
                result = on_frame(png)
                if asyncio.iscoroutine(result):
                    await result
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue

    async def _ensure_dvt_screenshot(self) -> None:
        if self._dvt_shot is not None:
            return
        dvt_cls, shot_cls = _load_dvt_screenshot()
        self._dvt = await dvt_cls(self._rsd).__aenter__()
        self._dvt_shot = await shot_cls(self._dvt).__aenter__()

    async def _capture_png(self) -> bytes:
        if self._capture is not None:
            try:
                response = await self._capture.capture_screenshot()
                image = response.get("image")
                if isinstance(image, (bytes, bytearray)):
                    return bytes(image)
            except Exception as exc:
                logger.warning("ScreenCaptureService frame failed, trying DVT: %s", exc)
                self._capture = None
        await self._ensure_dvt_screenshot()
        return await self._dvt_shot.get_screenshot()

    async def tap_hid(self, x: int, y: int) -> None:
        if self._hid is None:
            raise DeskError(TOUCH_BLOCKED_STATUS if not self.touch_available else "Not connected.")
        try:
            async with self._hid_lock:
                await tap(self._hid, x, y)
        except Exception as exc:
            if is_remote_control_unsupported(exc):
                self.touch_available = False
                raise DeskError(TOUCH_BLOCKED_STATUS) from exc
            raise DeskError(humanize_device_error(exc)) from exc

    async def drag_hid(self, x1: int, y1: int, x2: int, y2: int) -> None:
        if self._hid is None:
            raise DeskError(TOUCH_BLOCKED_STATUS if not self.touch_available else "Not connected.")
        try:
            async with self._hid_lock:
                await drag(self._hid, x1, y1, x2, y2)
        except Exception as exc:
            if is_remote_control_unsupported(exc):
                self.touch_available = False
                raise DeskError(TOUCH_BLOCKED_STATUS) from exc
            raise DeskError(humanize_device_error(exc)) from exc

    async def press_button(self, name: str) -> None:
        if self._buttons is None:
            raise DeskError("Hardware buttons are not available.")
        try:
            async with self._hid_lock:
                await press_named_button(self._buttons, name)
        except Exception as exc:
            raise DeskError(humanize_device_error(exc)) from exc

    async def close(self) -> None:
        self._stop.set()
        for task in (self._shot_task, self._stream_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._shot_task = None
        self._stream_task = None

        async def _aclose(obj: Any) -> None:
            if obj is None:
                return
            closer = getattr(obj, "__aexit__", None)
            if closer is not None:
                await closer(None, None, None)
                return
            close = getattr(obj, "close", None) or getattr(obj, "aclose", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result

        for obj in (self._dvt_shot, self._dvt, self._capture, self._buttons, self._hid):
            with contextlib.suppress(Exception):
                await _aclose(obj)
        self._dvt_shot = self._dvt = self._capture = self._buttons = self._hid = None
        if self._touch_cm is not None:
            with contextlib.suppress(Exception):
                await self._touch_cm.__aexit__(None, None, None)
            self._touch_cm = None
        if self._tunnel is not None:
            with contextlib.suppress(Exception):
                await self._tunnel.aclose()
            self._tunnel = None
            self._rsd = None
        if self._lockdown is not None:
            with contextlib.suppress(Exception):
                await self._lockdown.close()
            self._lockdown = None
        self.summary = None
        self.hevc_url = None
        self.touch_available = True
        self._stop = asyncio.Event()
