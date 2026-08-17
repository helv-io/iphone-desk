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
    NoDeviceError,
    TOUCH_BLOCKED_STATUS,
    TrustRequiredError,
    humanize_device_error,
    is_remote_control_unsupported,
)
from iphone_desk.hid_actions import contact, drag, press_named_button, release, tap

logger = logging.getLogger(__name__)

FrameCallback = Callable[[bytes], Awaitable[None] | None]
StatusCallback = Callable[[str], None]

# AMFI action 0 unhides Settings > Privacy & Security > Developer Mode.
# Actions 1 (enable) and 2 (post-restart accept) are intentionally unused.
AMFI_REVEAL_ACTION = 0
AMFI_SERVICE_NAME = "com.apple.amfi.lockdown"

# Parallel DVT stills. One channel is ~4.2 fps; three measured ~7.4 fps on a 15 Pro Max.
# 10 fps is not reachable with takeScreenshot (needs a ~100ms still).
DVT_CAPTURE_WORKERS = 3

DEVELOPER_MODE_OFF_AFTER_REVEAL = (
    "Developer Mode is off. This PC asked iOS to show the toggle. "
    "Enable it under Settings > Privacy & Security > Developer Mode, restart when iOS asks, then Connect."
)
DEVELOPER_MODE_OFF_IN_SETTINGS = (
    "Developer Mode is off. Enable it in Settings > Privacy & Security > Developer Mode, "
    "restart when iOS asks, then Connect."
)

TRANSPORT_USB = "USB"
TRANSPORT_WIFI = "WiFi"
NO_DEVICE_STATUS = (
    "No iPhone found over USB or WiFi. Plug in the cable, or wake the unlocked phone "
    "on the same WiFi so it can advertise."
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
    transport: str = TRANSPORT_USB


def _is_usb(device: Any) -> bool:
    if bool(getattr(device, "is_usb", False)):
        return True
    return str(getattr(device, "connection_type", "")).casefold() == "usb"


def _is_network(device: Any) -> bool:
    if bool(getattr(device, "is_network", False)):
        return True
    return str(getattr(device, "connection_type", "")).casefold() == "network"


def _same_udid(left: str, right: str) -> bool:
    return left.replace("-", "").casefold() == right.replace("-", "").casefold()


def usbmux_connection_type(device: Any) -> str:
    raw = str(getattr(device, "connection_type", "") or "")
    if raw in {"USB", "Network"}:
        return raw
    return "Network" if _is_network(device) else "USB"


def transport_label(device: Any) -> str:
    return TRANSPORT_WIFI if _is_network(device) else TRANSPORT_USB


def pick_usbmux_device(devices: list[Any], serial: Optional[str] = None) -> Optional[Any]:
    """Prefer USB when the same UDID is also visible as a Network device."""
    matches = list(devices)
    if serial:
        matches = [device for device in matches if _same_udid(str(device.serial), serial)]
    if not matches:
        return None
    for device in matches:
        if _is_usb(device):
            return device
    return matches[0]


async def ensure_wifi_connections(lockdown: Any) -> bool:
    """Turn on lockdown WiFi connections after Trust. Soft-fail; never blocks USB."""
    getter = getattr(lockdown, "get_enable_wifi_connections", None)
    if callable(getter):
        try:
            if bool(await _maybe_await(getter())):
                return True
        except Exception as exc:
            logger.warning("get_enable_wifi_connections failed: %s", exc)
    setter = getattr(lockdown, "set_enable_wifi_connections", None)
    if not callable(setter):
        logger.warning("set_enable_wifi_connections is unavailable")
        return False
    try:
        await _maybe_await(setter(True))
        return True
    except Exception as exc:
        logger.warning("set_enable_wifi_connections failed: %s", exc)
        return False


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
            detail="Apple Mobile Device / usbmux is not reachable. Install Apple Mobile Device Support, then replug USB.",
        )

    devices = await list_devices()
    usb = [device for device in devices if _is_usb(device)]
    wifi = [device for device in devices if _is_network(device)]
    labels = [f"{device.serial} ({transport_label(device)})" for device in devices]
    target = pick_usbmux_device(devices)
    if target is None:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=False,
            paired=None,
            developer_mode=None,
            device_labels=labels,
            wifi_present=False,
            detail=NO_DEVICE_STATUS,
        )

    serial = str(target.serial)
    how = transport_label(target)
    try:
        lockdown = await create_using_usbmux(
            serial=serial,
            autopair=False,
            connection_type=usbmux_connection_type(target),
        )
    except NotPairedError:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=bool(usb),
            paired=False,
            developer_mode=None,
            device_labels=labels,
            wifi_present=bool(wifi),
            detail=(
                "The phone is visible but not paired. Unlock it, tap Trust, then Connect. "
                "First Trust is usually USB."
            ),
        )
    except (PairingDialogResponsePendingError, PasswordRequiredError):
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=bool(usb),
            paired=False,
            developer_mode=None,
            device_labels=labels,
            wifi_present=bool(wifi),
            detail="Unlock the iPhone and tap Trust This Computer.",
        )
    except UserDeniedPairingError:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=bool(usb),
            paired=False,
            developer_mode=None,
            device_labels=labels,
            wifi_present=bool(wifi),
            detail="Trust was declined on the phone. Unplug, replug, and tap Trust.",
        )
    except Exception as exc:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=bool(usb),
            paired=None,
            developer_mode=None,
            device_labels=labels,
            wifi_present=bool(wifi),
            detail=f"{how} device seen, lockdown failed: {exc}",
        )

    try:
        paired = bool(getattr(lockdown, "paired", True))
        revealed = False
        if paired:
            revealed = await reveal_developer_mode_option(lockdown)
            await ensure_wifi_connections(lockdown)
        developer_mode: Optional[bool]
        try:
            developer_mode = bool(await lockdown.get_developer_mode_status())
        except Exception:
            developer_mode = None
        name = getattr(lockdown, "display_name", None) or serial
        version = getattr(lockdown, "product_version", "?")
        if usb and wifi:
            over = "USB and WiFi"
        else:
            over = how
        detail = f"Found {name} (iOS {version}) over {over}."
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
            usb_present=bool(usb),
            paired=paired,
            developer_mode=developer_mode,
            device_labels=labels,
            wifi_present=bool(wifi),
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
        self._live: Any = None
        self._lockdown: Any = None
        self._tunnel: Any = None
        self._rsd: Any = None
        self._hid: Any = None
        self._buttons: Any = None
        self._capture: Any = None
        self._dvt: Any = None
        self._dvt_shot: Any = None
        self._dvt_pairs: list[tuple[Any, Any]] = []
        self._dvt_pool: Optional[asyncio.Queue[Any]] = None
        self._touch_cm: Any = None
        self._stream_task: Optional[asyncio.Task[None]] = None
        self._shot_task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()
        self._hid_lock = asyncio.Lock()
        self.touch_available = True
        self._screencapture_oneshot = False
        self._capture_backend = ""
        self._kb_id: Optional[int] = None
        self._keys: set[int] = set()

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
        screenshot_fps: float = 20.0,
        on_frame: Optional[FrameCallback] = None,
        on_live_frame: Optional[Callable[[int, int, bytes], None]] = None,
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
                "Apple Mobile Device / usbmux is not running. Install Apple Mobile Device Support."
            ) from exc

        target = pick_usbmux_device(devices, serial)
        if target is None:
            raise NoDeviceError(NO_DEVICE_STATUS)
        how = transport_label(target)
        status(f"Pairing over {how}...")

        try:
            self._lockdown = await create_using_usbmux(
                serial=str(target.serial),
                autopair=True,
                connection_type=usbmux_connection_type(target),
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
        name = str(getattr(lockdown, "display_name", None) or target.serial)
        udid = str(lockdown.udid)

        await ensure_wifi_connections(lockdown)
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
            on_live_frame=on_live_frame,
            on_status=status,
        )

        self.summary = ConnectedDevice(
            udid=udid,
            name=name,
            product_version=product_version,
            display=display,
            mode=mode,
            touch_available=self.touch_available,
            transport=how,
        )
        status(f"Connected to {name} over {how} (iOS {product_version}) in {mode} mode.")
        return self.summary

    async def _start_screen(
        self,
        *,
        prefer_hevc: bool,
        screenshot_fps: float,
        on_frame: Optional[FrameCallback],
        on_live_frame: Optional[Callable[[int, int, bytes], None]] = None,
        on_status: StatusCallback,
    ) -> str:
        if prefer_hevc:
            try:
                await self._start_hevc(on_status=on_status, on_live_frame=on_live_frame)
                return "hevc"
            except Exception as exc:
                logger.warning("Live HEVC failed, using screenshot loop: %s", exc)
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

    async def _start_hevc(
        self,
        *,
        on_status: StatusCallback,
        on_live_frame: Optional[Callable[[int, int, bytes], None]] = None,
    ) -> None:
        import time
        from collections import deque

        from iphone_desk.frames import rolling_fps
        from iphone_desk.live_video import LiveHevcPump

        first = asyncio.Event()
        stamps: deque[float] = deque(maxlen=24)
        last_report = time.perf_counter()

        def on_live(width: int, height: int, bgra: bytes) -> None:
            nonlocal last_report
            if not first.is_set():
                first.set()
            if on_live_frame is not None:
                on_live_frame(width, height, bgra)
            now = time.perf_counter()
            stamps.append(now)
            if now - last_report >= 1.5:
                last_report = now
                on_status(f"Live {rolling_fps(list(stamps)):.1f} fps")

        on_status("Starting live HEVC decode...")
        pump = LiveHevcPump(self._rsd, on_frame=on_live)
        await pump.start()
        self._live = pump
        on_status("Waiting for the first live frame...")
        try:
            await asyncio.wait_for(first.wait(), timeout=12.0)
        except asyncio.TimeoutError as exc:
            await pump.close()
            self._live = None
            raise DeskError("Live video started but no picture arrived.") from exc

        from pymobiledevice3.remote.core_device.hid_service import (
            IndigoHIDService,
            UniversalHIDServiceService,
        )

        try:
            self._hid = await UniversalHIDServiceService(self._rsd).__aenter__()
            self._buttons = await IndigoHIDService(self._rsd).__aenter__()
            self.touch_available = True
            await self._open_keyboard()
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
        await self._open_keyboard()
        if not await self._open_screenshot_capture(on_status):
            raise DeskError("Could not open screen capture or DVT screenshot.")
        delay = 1.0 / max(fps, 1.0)
        self._shot_task = asyncio.create_task(
            self._screenshot_loop(delay, on_frame, on_status),
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

    async def _open_keyboard(self) -> None:
        self._kb_id = None
        self._keys.clear()
        if self._hid is None:
            return
        create = getattr(self._hid, "create_keyboard_service", None)
        if not callable(create):
            return
        try:
            self._kb_id = int(await _maybe_await(create()))
        except Exception as exc:
            logger.warning("virtual keyboard unavailable: %s", exc)
            self._kb_id = None

    async def _open_screenshot_capture(self, on_status: StatusCallback) -> bool:
        # DVT first: reusable channel, ~230ms/frame on Helvio's 15 Pro Max.
        # ScreenCaptureService returns one PNG then the phone closes the XPC
        # socket. Reconnecting each frame is ~330ms, slower than DVT.
        if await self._open_dvt_screenshot():
            workers = len(self._dvt_pairs) or 1
            self._capture_backend = f"dvt x{workers}"
            on_status(f"Using DVT screenshot ({workers} parallel stills).")
            return True
        try:
            png = await self._screencapture_once()
        except Exception as exc:
            logger.warning("ScreenCaptureService failed: %s", exc)
            png = b""
        if png:
            self._screencapture_oneshot = True
            self._capture_backend = "screencapture"
            on_status("Using ScreenCaptureService (reconnect each frame).")
            return True
        return False

    async def _open_dvt_screenshot(self) -> bool:
        try:
            dvt_cls, shot_cls = _load_dvt_screenshot()
        except Exception as exc:
            logger.warning("DVT screenshot failed: %s", exc)
            return False
        pairs: list[tuple[Any, Any]] = []
        last_exc: Optional[BaseException] = None
        for index in range(DVT_CAPTURE_WORKERS):
            try:
                dvt = await dvt_cls(self._rsd).__aenter__()
                shot = await shot_cls(dvt).__aenter__()
                pairs.append((dvt, shot))
            except Exception as exc:
                last_exc = exc
                logger.warning("DVT worker %s failed: %s", index, exc)
                break
        if not pairs:
            logger.warning("DVT screenshot failed: %s", last_exc)
            return False
        try:
            png = await pairs[0][1].get_screenshot()
            if not png:
                raise DeskError("DVT screenshot returned an empty frame.")
        except Exception as exc:
            logger.warning("DVT screenshot probe failed: %s", exc)
            for dvt, shot in reversed(pairs):
                with contextlib.suppress(Exception):
                    await shot.__aexit__(None, None, None)
                with contextlib.suppress(Exception):
                    await dvt.__aexit__(None, None, None)
            return False
        self._dvt_pairs = pairs
        self._dvt, self._dvt_shot = pairs[0]
        pool: asyncio.Queue[Any] = asyncio.Queue()
        for _dvt, shot in pairs:
            pool.put_nowait(shot)
        self._dvt_pool = pool
        return True

    async def _screencapture_once(self) -> bytes:
        """One PNG. The device tears down this XPC channel afterward."""
        capture_cls = _load_screen_capture()
        capture = await capture_cls(self._rsd).__aenter__()
        try:
            response = await capture.capture_screenshot()
            image = response.get("image") if isinstance(response, dict) else None
            if isinstance(image, (bytes, bytearray)) and image:
                return bytes(image)
            raise DeskError("ScreenCaptureService returned an empty frame.")
        finally:
            with contextlib.suppress(Exception):
                await capture.__aexit__(None, None, None)

    async def _reset_video_and_hid(self) -> None:
        await self._stop_stream_task()
        if self._live is not None:
            with contextlib.suppress(Exception):
                await self._live.close()
            self._live = None
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

    async def _screenshot_loop(
        self,
        delay: float,
        on_frame: Optional[FrameCallback],
        on_status: Optional[StatusCallback] = None,
    ) -> None:
        import time

        from iphone_desk.frames import prepare_preview_frame, remaining_frame_delay

        from collections import deque

        from iphone_desk.frames import rolling_fps

        loop = asyncio.get_running_loop()
        workers = 1
        if self._dvt_pool is not None:
            workers = max(1, self._dvt_pool.qsize())
        frames_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=workers)
        stamps: deque[float] = deque(maxlen=12)
        last_report = time.perf_counter()

        async def _fill() -> None:
            while not self._stop.is_set():
                try:
                    png = await self._capture_png()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("screenshot failed: %s", exc)
                    leftover = remaining_frame_delay(0.05, 10.0)
                    if leftover > 0:
                        with contextlib.suppress(asyncio.TimeoutError):
                            await asyncio.wait_for(self._stop.wait(), timeout=leftover)
                    continue
                try:
                    await asyncio.wait_for(frames_q.put(png), timeout=1.0)
                except asyncio.TimeoutError:
                    if self._stop.is_set():
                        return

        fillers = [asyncio.create_task(_fill(), name=f"iphone-desk-fill-{i}") for i in range(workers)]
        try:
            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(frames_q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    if self._stop.is_set():
                        return
                    continue
                preview = raw
                if raw:
                    try:
                        preview = await loop.run_in_executor(None, prepare_preview_frame, raw)
                    except Exception as exc:
                        logger.warning("preview shrink failed: %s", exc)
                        preview = raw
                if on_frame is not None and preview:
                    result = on_frame(preview)
                    if asyncio.iscoroutine(result):
                        await result
                now = time.perf_counter()
                stamps.append(now)
                if on_status is not None and now - last_report >= 1.5:
                    fps = rolling_fps(list(stamps))
                    backend = self._capture_backend or "screenshot"
                    on_status(f"Mirror {fps:.1f} fps ({backend}).")
                    last_report = now
        finally:
            for task in fillers:
                task.cancel()
            for task in fillers:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def _ensure_dvt_screenshot(self) -> None:
        if self._dvt_shot is not None:
            return
        dvt_cls, shot_cls = _load_dvt_screenshot()
        self._dvt = await dvt_cls(self._rsd).__aenter__()
        self._dvt_shot = await shot_cls(self._dvt).__aenter__()

    async def _capture_png(self) -> bytes:
        if self._dvt_pool is not None:
            shot = await self._dvt_pool.get()
            try:
                return await shot.get_screenshot()
            finally:
                self._dvt_pool.put_nowait(shot)
        if self._dvt_shot is not None:
            return await self._dvt_shot.get_screenshot()
        if self._screencapture_oneshot:
            return await self._screencapture_once()
        if self._capture is not None:
            try:
                response = await self._capture.capture_screenshot()
                image = response.get("image")
                if isinstance(image, (bytes, bytearray)) and image:
                    return bytes(image)
            except Exception as exc:
                logger.warning("ScreenCaptureService frame failed, trying DVT: %s", exc)
                self._capture = None
        await self._ensure_dvt_screenshot()
        return await self._dvt_shot.get_screenshot()

    async def _hid_or_raise(self) -> Any:
        if self._hid is None:
            raise DeskError(TOUCH_BLOCKED_STATUS if not self.touch_available else "Not connected.")
        return self._hid

    async def tap_hid(self, x: int, y: int) -> None:
        hid = await self._hid_or_raise()
        try:
            async with self._hid_lock:
                await tap(hid, x, y)
        except Exception as exc:
            if is_remote_control_unsupported(exc):
                self.touch_available = False
                raise DeskError(TOUCH_BLOCKED_STATUS) from exc
            raise DeskError(humanize_device_error(exc)) from exc

    async def contact_hid(self, x: int, y: int) -> None:
        hid = await self._hid_or_raise()
        try:
            async with self._hid_lock:
                await contact(hid, x, y)
        except Exception as exc:
            if is_remote_control_unsupported(exc):
                self.touch_available = False
                raise DeskError(TOUCH_BLOCKED_STATUS) from exc
            raise DeskError(humanize_device_error(exc)) from exc

    async def release_hid(self, x: int, y: int) -> None:
        hid = await self._hid_or_raise()
        try:
            async with self._hid_lock:
                await release(hid, x, y)
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

    async def key_down(self, usage: int) -> None:
        self._keys.add(int(usage))
        await self._send_keys()

    async def key_up(self, usage: int) -> None:
        self._keys.discard(int(usage))
        await self._send_keys()

    async def keys_clear(self) -> None:
        if not self._keys:
            return
        self._keys.clear()
        await self._send_keys()

    async def keys_replace(self, usages: list[int]) -> None:
        self._keys = {int(usage) for usage in usages}
        await self._send_keys()

    async def _send_keys(self) -> None:
        if self._hid is None or self._kb_id is None:
            return
        send = getattr(self._hid, "send_keyboard", None)
        if not callable(send):
            return
        try:
            async with self._hid_lock:
                await _maybe_await(send(self._kb_id, list(self._keys)))
        except Exception as exc:
            if is_remote_control_unsupported(exc):
                logger.warning("keyboard blocked: %s", exc)
                return
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
        if self._live is not None:
            with contextlib.suppress(Exception):
                await self._live.close()
            self._live = None

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

        for dvt, shot in reversed(self._dvt_pairs):
            with contextlib.suppress(Exception):
                await _aclose(shot)
            with contextlib.suppress(Exception):
                await _aclose(dvt)
        self._dvt_pairs = []
        self._dvt_pool = None
        self._dvt_shot = None
        self._dvt = None
        for obj in (self._capture, self._buttons, self._hid):
            with contextlib.suppress(Exception):
                await _aclose(obj)
        self._capture = self._buttons = self._hid = None
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
        self._screencapture_oneshot = False
        self._capture_backend = ""
        self._kb_id = None
        self._keys.clear()
        self._stop = asyncio.Event()
