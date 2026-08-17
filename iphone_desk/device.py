"""Talk to a trusted iPhone through pymobiledevice3's public Python API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, Optional

from packaging.version import Version

from iphone_desk.checklist import (
    ChecklistStatus,
    phone_helper_missing_detail,
    phone_helper_missing_error,
)
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
from iphone_desk.video_modes import (
    AUTO_FALLBACK_ORDER,
    VIDEO_MODE_AUTO,
    VIDEO_MODE_CORE,
    VIDEO_MODE_DVT,
    VIDEO_MODE_HEVC,
    VIDEO_MODE_SCREENSHOTR,
    normalize_hevc_decoder,
    normalize_video_mode,
    video_mode_label,
)

logger = logging.getLogger(__name__)

FrameCallback = Callable[[bytes], Awaitable[None] | None]
LiveFrameCallback = Callable[[int, int, bytes], None]
StatusCallback = Callable[[str], None]

# AMFI action 0 unhides Settings > Privacy & Security > Developer Mode.
# Actions 1 (enable) and 2 (post-restart accept) are intentionally unused.
AMFI_REVEAL_ACTION = 0
AMFI_SERVICE_NAME = "com.apple.amfi.lockdown"

# Parallel DVT stills. One channel is ~4.2 fps; three measured ~7.4 fps on a 15 Pro Max.
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
NO_DEVICE_STATUS = "No USB iPhone found. Plug in the cable, unlock the phone, and tap Trust if asked."


def _load_amfi_service() -> Any:
    from pymobiledevice3.services.amfi import AmfiService

    return AmfiService


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


def _load_screenshotr() -> Any:
    from pymobiledevice3.services.screenshot import ScreenshotService

    return ScreenshotService


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


def _same_udid(left: str, right: str) -> bool:
    return left.replace("-", "").casefold() == right.replace("-", "").casefold()


def usbmux_connection_type(_device: Any) -> str:
    """USB-only picker. Network usbmux devices are never accepted."""
    return "USB"


def pick_usbmux_device(devices: list[Any], serial: Optional[str] = None) -> Optional[Any]:
    """Return the first USB usbmux device. Ignore Network entries."""
    matches = [device for device in devices if _is_usb(device)]
    if serial:
        matches = [device for device in matches if _same_udid(str(device.serial), serial)]
    if not matches:
        return None
    return matches[0]


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
            detail=phone_helper_missing_detail(),
        )

    devices = await list_devices()
    usb = [device for device in devices if _is_usb(device)]
    labels = [str(device.serial) for device in usb]
    target = pick_usbmux_device(devices)
    if target is None:
        return ChecklistStatus(
            apple_mobile_device=True,
            usb_present=False,
            paired=None,
            developer_mode=None,
            device_labels=labels,
            detail=NO_DEVICE_STATUS,
        )

    serial = str(target.serial)
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
        detail = f"Found {name} (iOS {version}) over USB."
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
        self._live: Any = None
        self._lockdown: Any = None
        self._tunnel: Any = None
        self._rsd: Any = None
        self._hid: Any = None
        self._buttons: Any = None
        self._dvt: Any = None
        self._dvt_shot: Any = None
        self._dvt_pairs: list[tuple[Any, Any]] = []
        self._dvt_pool: Optional[asyncio.Queue[Any]] = None
        self._screenshotr: Any = None
        self._shot_task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()
        self._hid_lock = asyncio.Lock()
        self.touch_available = True
        self._screencapture_oneshot = False
        self._capture_backend = ""
        self._picture_mode = ""
        self._hevc_decoder = "auto"
        self._kb_id: Optional[int] = None
        self._keys: set[int] = set()
        self._on_frame: Optional[FrameCallback] = None
        self._on_live_frame: Optional[LiveFrameCallback] = None
        self._screenshot_fps = 20.0

    @property
    def display(self) -> Size:
        if self.summary is None:
            return Size(390, 844)
        return self.summary.display

    async def connect(
        self,
        *,
        serial: Optional[str] = None,
        video_mode: str = VIDEO_MODE_AUTO,
        hevc_decoder: str = "auto",
        screenshot_fps: float = 20.0,
        on_frame: Optional[FrameCallback] = None,
        on_live_frame: Optional[LiveFrameCallback] = None,
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

        self._on_frame = on_frame
        self._on_live_frame = on_live_frame
        self._screenshot_fps = screenshot_fps
        self._hevc_decoder = normalize_hevc_decoder(hevc_decoder)
        wanted = normalize_video_mode(video_mode)

        try:
            devices = await list_devices()
        except ConnectionFailedToUsbmuxdError as exc:
            raise DriverMissingError(phone_helper_missing_error()) from exc

        target = pick_usbmux_device(devices, serial)
        if target is None:
            raise NoDeviceError(NO_DEVICE_STATUS)
        status("Pairing over USB...")

        try:
            self._lockdown = await create_using_usbmux(
                serial=str(target.serial),
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
        name = str(getattr(lockdown, "display_name", None) or target.serial)
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

        await self._open_indigo_buttons(status)
        await self._open_touch_without_stream(status)
        await self._open_keyboard()

        mode = await self._start_screen(wanted, status)

        self.summary = ConnectedDevice(
            udid=udid,
            name=name,
            product_version=product_version,
            display=display,
            mode=mode,
            touch_available=self.touch_available,
            transport=TRANSPORT_USB,
        )
        status(f"Connected to {name} over USB (iOS {product_version}) in {video_mode_label(mode)}.")
        return self.summary

    async def switch_picture(
        self,
        video_mode: str,
        *,
        hevc_decoder: Optional[str] = None,
        on_status: Optional[StatusCallback] = None,
    ) -> str:
        """Reconnect only the picture path. Trust, tunnel, and HID stay."""

        def status(message: str) -> None:
            logger.info(message)
            if on_status is not None:
                on_status(message)

        if self._rsd is None:
            raise DeskError("Not connected.")
        if hevc_decoder is not None:
            self._hevc_decoder = normalize_hevc_decoder(hevc_decoder)
        wanted = normalize_video_mode(video_mode)
        previous = self._picture_mode or (self.summary.mode if self.summary is not None else "")
        status(f"Switching picture to {video_mode_label(wanted)}...")
        await self._stop_picture()
        try:
            mode = await self._start_screen(wanted, status)
        except Exception:
            if previous and previous != wanted:
                with contextlib.suppress(Exception):
                    await self._start_screen(previous, status)
                    if self.summary is not None:
                        self.summary = replace(
                            self.summary, mode=previous, touch_available=self.touch_available
                        )
            raise
        if self.summary is not None:
            self.summary = replace(self.summary, mode=mode, touch_available=self.touch_available)
        status(f"Picture is {video_mode_label(mode)}.")
        return mode

    async def _start_screen(self, video_mode: str, on_status: StatusCallback) -> str:
        wanted = normalize_video_mode(video_mode)
        if wanted == VIDEO_MODE_AUTO:
            last_error: Optional[BaseException] = None
            for candidate in AUTO_FALLBACK_ORDER:
                try:
                    await self._start_named_mode(candidate, on_status)
                    on_status(f"Auto stuck on {video_mode_label(candidate)}.")
                    return candidate
                except Exception as exc:
                    last_error = exc
                    logger.warning("Auto candidate %s failed: %s", candidate, exc)
                    await self._stop_picture()
                    on_status(f"Auto skipped {video_mode_label(candidate)}: {humanize_device_error(exc)}")
            last = humanize_device_error(last_error or DeskError("unknown"))
            raise DeskError(f"Auto found no working picture path. Last error: {last}")
        await self._start_named_mode(wanted, on_status)
        return wanted

    async def _start_named_mode(self, mode: str, on_status: StatusCallback) -> None:
        if mode == VIDEO_MODE_HEVC:
            await self._start_hevc(on_status=on_status)
            return
        if mode == VIDEO_MODE_DVT:
            await self._start_dvt_stills(on_status)
            return
        if mode == VIDEO_MODE_CORE:
            await self._start_core_stills(on_status)
            return
        if mode == VIDEO_MODE_SCREENSHOTR:
            await self._start_screenshotr(on_status)
            return
        raise DeskError(f"Unknown video mode: {mode}")

    async def _start_hevc(self, *, on_status: StatusCallback) -> None:
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
            if self._on_live_frame is not None:
                self._on_live_frame(width, height, bgra)
            now = time.perf_counter()
            stamps.append(now)
            if now - last_report >= 1.5:
                last_report = now
                on_status(f"Live {rolling_fps(list(stamps)):.1f} fps")

        on_status(f"Starting HEVC live ({self._hevc_decoder} decode)...")
        pump = LiveHevcPump(
            self._rsd,
            on_frame=on_live,
            decoder=self._hevc_decoder,
        )
        await pump.start()
        self._live = pump
        self._picture_mode = VIDEO_MODE_HEVC
        self._capture_backend = "hevc"
        if pump.media_summary:
            on_status(f"Device media: {pump.media_summary}")
        on_status("Waiting for the first live frame...")
        try:
            await asyncio.wait_for(first.wait(), timeout=12.0)
        except asyncio.TimeoutError as exc:
            await pump.close()
            self._live = None
            raise DeskError("Live video started but no picture arrived.") from exc

    async def _start_dvt_stills(self, on_status: StatusCallback) -> None:
        on_status("Starting DVT screenshots...")
        if not await self._open_dvt_screenshot():
            raise DeskError("DVT screenshot did not open.")
        workers = len(self._dvt_pairs) or 1
        self._capture_backend = f"dvt x{workers}"
        self._picture_mode = VIDEO_MODE_DVT
        on_status(f"Using DVT screenshot ({workers} parallel stills).")
        self._start_still_loop()

    async def _start_core_stills(self, on_status: StatusCallback) -> None:
        on_status("Starting Core Device stills...")
        png = await self._screencapture_once()
        if not png:
            raise DeskError("Core Device screen-capture returned an empty frame.")
        self._screencapture_oneshot = True
        self._capture_backend = "screencapture"
        self._picture_mode = VIDEO_MODE_CORE
        on_status("Using Core Device screen-capture (reconnect each frame).")
        await self._emit_still(png)
        self._start_still_loop()

    async def _start_screenshotr(self, on_status: StatusCallback) -> None:
        on_status("Starting lockdown screenshotr...")
        if self._lockdown is None:
            raise DeskError("Lockdown is not connected.")
        try:
            service_cls = _load_screenshotr()
            service = service_cls(lockdown=self._lockdown)
            raw = await service.take_screenshot()
        except Exception as exc:
            raise DeskError(f"Lockdown screenshotr failed: {humanize_device_error(exc)}") from exc
        if not raw:
            raise DeskError("Lockdown screenshotr returned an empty frame.")
        self._screenshotr = service
        self._capture_backend = "screenshotr"
        self._picture_mode = VIDEO_MODE_SCREENSHOTR
        on_status("Using lockdown screenshotr.")
        await self._emit_still(raw)
        self._start_still_loop()

    def _start_still_loop(self) -> None:
        delay = 1.0 / max(self._screenshot_fps, 1.0)
        self._shot_task = asyncio.create_task(
            self._screenshot_loop(delay),
            name="iphone-desk-screenshots",
        )

    async def _open_indigo_buttons(self, on_status: StatusCallback) -> None:
        if self._buttons is not None:
            return
        try:
            indigo_cls = _load_indigo_hid()
            self._buttons = await indigo_cls(self._rsd).__aenter__()
        except Exception as exc:
            logger.warning("Indigo HID buttons unavailable: %s", exc)
            self._buttons = None
            on_status("Hardware buttons are unavailable on this session.")

    async def _open_touch_without_stream(self, on_status: StatusCallback) -> None:
        """Open Universal HID only. Do not start a media stream to authenticate it."""
        if self._hid is not None:
            return
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
        if self._kb_id is not None:
            return
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
            png = await self._dvt_take(pairs[0][1])
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
        await self._emit_still(png)
        return True

    async def _dvt_take(self, shot: Any) -> bytes:
        jpeg = getattr(shot, "get_screenshot_jpeg", None) or getattr(shot, "take_screenshot_jpeg", None)
        if callable(jpeg):
            with contextlib.suppress(Exception):
                data = await _maybe_await(jpeg())
                if isinstance(data, (bytes, bytearray)) and data:
                    return bytes(data)
        getter = getattr(shot, "get_screenshot", None)
        if callable(getter):
            data = await _maybe_await(getter())
            if isinstance(data, (bytes, bytearray)) and data:
                return bytes(data)
        take = getattr(shot, "take_screenshot", None)
        if callable(take):
            data = await _maybe_await(take())
            if isinstance(data, (bytes, bytearray)) and data:
                return bytes(data)
        raise DeskError("DVT screenshot returned an empty frame.")

    async def _screencapture_once(self) -> bytes:
        """One still. The device tears down this XPC channel afterward."""
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

    async def _stop_picture(self) -> None:
        self._stop.set()
        task = self._shot_task
        self._shot_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._live is not None:
            with contextlib.suppress(Exception):
                await self._live.close()
            self._live = None
        self.hevc_url = None
        for dvt, shot in reversed(self._dvt_pairs):
            with contextlib.suppress(Exception):
                await shot.__aexit__(None, None, None)
            with contextlib.suppress(Exception):
                await dvt.__aexit__(None, None, None)
        self._dvt_pairs = []
        self._dvt_pool = None
        self._dvt_shot = None
        self._dvt = None
        if self._screenshotr is not None:
            closer = getattr(self._screenshotr, "close", None)
            if callable(closer):
                with contextlib.suppress(Exception):
                    await _maybe_await(closer())
            self._screenshotr = None
        self._screencapture_oneshot = False
        self._capture_backend = ""
        self._picture_mode = ""
        self._stop = asyncio.Event()

    async def _screenshot_loop(self, delay: float) -> None:
        import time
        from collections import deque

        from iphone_desk.frames import LatestSlot, remaining_frame_delay, rolling_fps

        workers = 1
        if self._dvt_pool is not None:
            workers = max(1, self._dvt_pool.qsize())
        latest: LatestSlot[bytes] = LatestSlot()
        stamps: deque[float] = deque(maxlen=12)
        last_report = time.perf_counter()

        async def _fill() -> None:
            while not self._stop.is_set():
                started = time.perf_counter()
                try:
                    raw = await self._capture_still()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("screenshot failed: %s", exc)
                    leftover = remaining_frame_delay(0.05, 10.0)
                    if leftover > 0:
                        with contextlib.suppress(asyncio.TimeoutError):
                            await asyncio.wait_for(self._stop.wait(), timeout=leftover)
                    continue
                if raw:
                    latest.put(raw)
                leftover = remaining_frame_delay(time.perf_counter() - started, 1.0 / max(delay, 0.01))
                if leftover > 0:
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._stop.wait(), timeout=leftover)

        fillers = [asyncio.create_task(_fill(), name=f"iphone-desk-fill-{i}") for i in range(workers)]
        try:
            while not self._stop.is_set():
                raw = latest.take()
                if raw is None:
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._stop.wait(), timeout=0.02)
                    continue
                try:
                    await self._emit_still(raw)
                except Exception as exc:
                    logger.warning("still decode failed: %s", exc)
                    continue
                now = time.perf_counter()
                stamps.append(now)
                if now - last_report >= 1.5:
                    fps = rolling_fps(list(stamps))
                    backend = self._capture_backend or "screenshot"
                    logger.info("Mirror %.1f fps (%s).", fps, backend)
                    last_report = now
        finally:
            for task in fillers:
                task.cancel()
            for task in fillers:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def _emit_still(self, raw: bytes) -> None:
        loop = asyncio.get_running_loop()
        from iphone_desk.frames import decode_still_to_bgra

        decoded = await loop.run_in_executor(None, decode_still_to_bgra, raw)
        if decoded is not None and self._on_live_frame is not None:
            self._on_live_frame(decoded[0], decoded[1], decoded[2])
            return
        if self._on_frame is not None and raw:
            result = self._on_frame(raw)
            if asyncio.iscoroutine(result):
                await result

    async def _capture_still(self) -> bytes:
        if self._dvt_pool is not None:
            shot = await self._dvt_pool.get()
            try:
                return await self._dvt_take(shot)
            finally:
                self._dvt_pool.put_nowait(shot)
        if self._dvt_shot is not None:
            return await self._dvt_take(self._dvt_shot)
        if self._screenshotr is not None:
            data = await self._screenshotr.take_screenshot()
            return bytes(data) if data else b""
        if self._screencapture_oneshot:
            return await self._screencapture_once()
        raise DeskError("No stills backend is open.")

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
        await self._stop_picture()
        self._stop.set()

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

        for obj in (self._buttons, self._hid):
            with contextlib.suppress(Exception):
                await _aclose(obj)
        self._buttons = self._hid = None
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
        self._kb_id = None
        self._keys.clear()
        self._stop = asyncio.Event()
