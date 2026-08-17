"""Preview-frame helpers for the screenshot fallback path."""

from __future__ import annotations

from io import BytesIO

PREVIEW_MAX_HEIGHT = 1000
PREVIEW_JPEG_QUALITY = 70


def rolling_fps(timestamps: list[float]) -> float:
    """Frames per second over a short window of completion times."""
    if len(timestamps) < 2:
        return 0.0
    span = float(timestamps[-1]) - float(timestamps[0])
    if span <= 0:
        return 0.0
    return (len(timestamps) - 1) / span


def remaining_frame_delay(elapsed: float, target_fps: float) -> float:
    """How long to wait so capture+wait stays near ``target_fps``.

    If the capture already used the whole budget, return 0. Do not add a
    fixed sleep on top of a slow DVT round-trip.
    """
    if target_fps <= 0:
        return 0.0
    leftover = (1.0 / target_fps) - max(0.0, float(elapsed))
    return leftover if leftover > 0.0 else 0.0


def shrink_bgra(
    data: bytes,
    width: int,
    height: int,
    *,
    max_height: int = PREVIEW_MAX_HEIGHT,
) -> tuple[int, int, bytes]:
    """Downscale a tight BGRA framebuffer so the window is not painting 3.6 MP live frames."""
    if width <= 0 or height <= 0:
        return width, height, data
    expected = width * height * 4
    if len(data) < expected:
        return width, height, data
    payload = data[:expected]
    if max_height <= 0 or height <= max_height:
        return width, height, payload
    try:
        from PIL import Image
    except Exception:
        return width, height, payload
    scale = max_height / float(height)
    new_width = max(1, int(round(width * scale)))
    image = Image.frombytes("RGBA", (width, height), payload, "raw", "BGRA")
    image = image.resize((new_width, max_height), Image.Resampling.BILINEAR)
    return new_width, max_height, image.tobytes("raw", "BGRA")


def prepare_preview_frame(
    data: bytes,
    *,
    max_height: int = PREVIEW_MAX_HEIGHT,
    quality: int = PREVIEW_JPEG_QUALITY,
) -> bytes:
    """Downscale a full-phone PNG/JPEG to a JPEG the window can paint quickly.

    HID mapping uses get-display-info, not these pixels, so shrinking the
    preview does not move taps.
    """
    if not data:
        return data
    try:
        from PIL import Image
    except Exception:
        return data

    try:
        image = Image.open(BytesIO(data))
        height = int(getattr(image, "height", 0) or 0)
        if max_height > 0 and height > max_height:
            width = max(1, int(round(image.width * (max_height / height))))
            image.draft("RGB", (width, max_height))
        image.load()
    except Exception:
        return data

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    height = int(image.height)
    if max_height > 0 and height > max_height:
        width = max(1, int(round(image.width * (max_height / height))))
        image = image.resize((width, max_height), Image.Resampling.BILINEAR)

    out = BytesIO()
    image.save(out, format="JPEG", quality=max(30, min(95, int(quality))), optimize=False)
    return out.getvalue()
