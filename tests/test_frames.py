from io import BytesIO

import pytest
from PIL import Image

from iphone_desk.frames import (
    LatestSlot,
    decode_still_to_bgra,
    prepare_preview_frame,
    remaining_frame_delay,
    rolling_fps,
    shrink_bgra,
)


def test_rolling_fps() -> None:
    assert rolling_fps([]) == 0.0
    assert rolling_fps([1.0]) == 0.0
    assert rolling_fps([1.0, 1.2, 1.4, 1.5]) == pytest.approx(6.0)


def test_remaining_delay_is_zero_when_capture_already_used_budget() -> None:
    assert remaining_frame_delay(0.2, 10.0) == 0.0
    assert remaining_frame_delay(0.05, 10.0) == 0.05


def test_remaining_delay_rejects_non_positive_fps() -> None:
    assert remaining_frame_delay(0.01, 0.0) == 0.0
    assert remaining_frame_delay(0.01, -8.0) == 0.0


def _png(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), (12, 34, 56)).save(buf, format="PNG")
    return buf.getvalue()


def test_prepare_preview_downscales_and_jpeg_encodes() -> None:
    raw = _png(1290, 2796)
    out = prepare_preview_frame(raw, max_height=900)
    preview = Image.open(BytesIO(out))
    assert preview.format == "JPEG"
    assert preview.height == 900
    assert preview.width == 415


def test_prepare_preview_keeps_small_frames() -> None:
    raw = _png(200, 400)
    out = prepare_preview_frame(raw, max_height=900)
    preview = Image.open(BytesIO(out))
    assert preview.size == (200, 400)


def test_prepare_preview_returns_original_on_garbage() -> None:
    junk = b"not-an-image"
    assert prepare_preview_frame(junk) == junk


def test_shrink_bgra_downscales() -> None:
    width, height = 200, 2000
    pixel = bytes([10, 20, 30, 255])
    data = pixel * (width * height)
    new_w, new_h, out = shrink_bgra(data, width, height, max_height=500)
    assert new_h == 500
    assert new_w == 50
    assert len(out) == new_w * new_h * 4


def test_latest_slot_keeps_newest() -> None:
    slot: LatestSlot[int] = LatestSlot()
    slot.put(1)
    slot.put(2)
    assert slot.take() == 2
    assert slot.take() is None


def test_decode_still_to_bgra() -> None:
    raw = _png(20, 40)
    decoded = decode_still_to_bgra(raw, max_height=900)
    assert decoded is not None
    width, height, data = decoded
    assert (width, height) == (20, 40)
    assert len(data) == 20 * 40 * 4


def test_shrink_bgra_keeps_small_frames() -> None:
    width, height = 20, 40
    data = bytes([1, 2, 3, 255]) * (width * height)
    new_w, new_h, out = shrink_bgra(data, width, height, max_height=500)
    assert (new_w, new_h) == (width, height)
    assert out == data
