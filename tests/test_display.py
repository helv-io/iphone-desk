import pytest

from iphone_desk.display import parse_display_size


def test_documented_core_device_shape() -> None:
    info = {"displays": [{"currentMode": {"size": [828, 1792]}}]}
    size = parse_display_size(info)
    assert size.width == 828
    assert size.height == 1792


def test_alternate_keys() -> None:
    info = {"Displays": [{"CurrentMode": {"Width": 1179, "Height": 2556}}]}
    size = parse_display_size(info)
    assert (size.width, size.height) == (1179, 2556)


def test_flat_size_on_display() -> None:
    info = {"displays": [{"size": {"width": 390, "height": 844}}]}
    size = parse_display_size(info)
    assert (size.width, size.height) == (390, 844)


def test_missing_size_raises() -> None:
    with pytest.raises(ValueError):
        parse_display_size({"displays": [{"name": "LCD"}]})
