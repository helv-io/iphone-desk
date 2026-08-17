import pytest

from iphone_desk.hid_actions import (
    BUTTONS,
    TOUCH_CONTACT,
    TOUCH_RELEASE,
    contact,
    drag,
    drag_is_tap,
    press_named_button,
    release,
    tap,
)


class FakeTouch:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    async def send_touchscreen(self, state: int, x: int, y: int, service_id: int = 257) -> None:
        self.calls.append((state, x, y))


class FakeButtons:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    async def send_button(self, usage_page: int, usage_code: int, state: int) -> None:
        self.calls.append((usage_page, usage_code, state))


@pytest.mark.asyncio
async def test_live_contact_and_release_are_separate() -> None:
    hid = FakeTouch()
    await contact(hid, 10, 20)
    await contact(hid, 30, 40)
    await release(hid, 30, 40)
    assert hid.calls == [
        (TOUCH_CONTACT, 10, 20),
        (TOUCH_CONTACT, 30, 40),
        (TOUCH_RELEASE, 30, 40),
    ]


@pytest.mark.asyncio
async def test_tap_contact_then_release() -> None:
    hid = FakeTouch()
    await tap(hid, 32768, 1000, hold=0)
    assert hid.calls == [
        (TOUCH_CONTACT, 32768, 1000),
        (TOUCH_RELEASE, 32768, 1000),
    ]


@pytest.mark.asyncio
async def test_drag_streams_then_releases() -> None:
    hid = FakeTouch()
    await drag(hid, 0, 0, 100, 0, steps=4, duration=0)
    states = [call[0] for call in hid.calls]
    assert states[0] == TOUCH_CONTACT
    assert states[-1] == TOUCH_RELEASE
    assert states[-2] == TOUCH_CONTACT
    assert hid.calls[-1][1:] == (100, 0)
    assert hid.calls[0][1:] == (0, 0)


@pytest.mark.asyncio
async def test_tap_clamps_to_hid_range() -> None:
    hid = FakeTouch()
    await tap(hid, -20, 90000, hold=0)
    assert hid.calls[0][1:] == (0, 65535)


@pytest.mark.asyncio
async def test_home_button_down_then_up() -> None:
    buttons = FakeButtons()
    await press_named_button(buttons, "home")
    assert buttons.calls[0] == (0x0C, 0x40, 1)
    assert buttons.calls[-1] == (0x0C, 0x40, 2)


def test_tiny_move_is_tap() -> None:
    assert drag_is_tap(100, 100, 120, 110)
    assert not drag_is_tap(100, 100, 2000, 100)


def test_siri_is_a_long_power_press() -> None:
    page, usage, hold = BUTTONS["siri"]
    assert (page, usage) == BUTTONS["lock"][:2]
    assert hold > BUTTONS["home"][2]
