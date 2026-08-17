from iphone_desk.coords import (
    HID_MAX,
    fitted_image_rect,
    hid_to_pixel,
    phone_corner_radius,
    pixel_to_hid,
    scroll_wheel_to_drag,
    widget_to_hid,
    widget_to_image_pixel,
)


def test_pixel_to_hid_corners() -> None:
    assert pixel_to_hid(0, 0, 828, 1792) == (0, 0)
    assert pixel_to_hid(828, 1792, 828, 1792) == (HID_MAX, HID_MAX)


def test_pixel_to_hid_center() -> None:
    x, y = pixel_to_hid(414, 896, 828, 1792)
    assert abs(x - 32768) <= 1
    assert abs(y - 32768) <= 2


def test_phone_corner_radius_scales_with_short_side() -> None:
    assert phone_corner_radius(430, 932) == 430 * 0.128
    assert phone_corner_radius(0, 100) == 0.0


def test_pixel_to_hid_clamps() -> None:
    assert pixel_to_hid(-10, 2000, 100, 100) == (0, HID_MAX)


def test_pixel_to_hid_rejects_bad_size() -> None:
    try:
        pixel_to_hid(1, 1, 0, 10)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_hid_roundtrip() -> None:
    width, height = 1179, 2556
    hid = pixel_to_hid(200, 400, width, height)
    px, py = hid_to_pixel(*hid, width, height)
    assert abs(px - 200) < 1
    assert abs(py - 400) < 1


def test_letterbox_centers_portrait_in_wide_widget() -> None:
    rect = fitted_image_rect(800, 400, 100, 200)
    assert rect.height == 400
    assert abs(rect.width - 200) < 0.01
    assert abs(rect.x - 300) < 0.01
    assert rect.y == 0


def test_widget_margin_is_ignored() -> None:
    assert widget_to_image_pixel(10, 200, 800, 400, 100, 200) is None
    mapped = widget_to_image_pixel(400, 200, 800, 400, 100, 200)
    assert mapped is not None
    assert abs(mapped[0] - 50) < 0.5
    assert abs(mapped[1] - 100) < 0.5


def test_widget_to_hid_uses_display_pixels() -> None:
    hid = widget_to_hid(400, 200, 800, 400, 100, 200)
    assert hid is not None
    assert hid == pixel_to_hid(50, 100, 100, 200)


def test_scroll_wheel_up_swipes_down() -> None:
    x1, y1, x2, y2 = scroll_wheel_to_drag(32768, 30000, 120, distance=4000)
    assert (x1, y1) == (32768, 30000)
    assert x2 == 32768
    assert y2 == 34000


def test_scroll_wheel_down_swipes_up() -> None:
    x1, y1, x2, y2 = scroll_wheel_to_drag(32768, 30000, -120, distance=4000)
    assert y2 == 26000
    assert x1 == x2


def test_scroll_wheel_zero_is_noop() -> None:
    assert scroll_wheel_to_drag(10, 20, 0) == (10, 20, 10, 20)
