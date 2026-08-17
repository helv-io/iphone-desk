from PySide6.QtCore import Qt

from iphone_desk.keyboard import KEY_A, KEY_ENTER, KEY_LEFT_SHIFT, hid_usage_for_qt_key


def test_letters_and_enter() -> None:
    assert hid_usage_for_qt_key(int(Qt.Key.Key_A)) == KEY_A
    assert hid_usage_for_qt_key(int(Qt.Key.Key_Return)) == KEY_ENTER
    assert hid_usage_for_qt_key(int(Qt.Key.Key_Shift)) == KEY_LEFT_SHIFT


def test_unknown_key_is_none() -> None:
    assert hid_usage_for_qt_key(0) is None
