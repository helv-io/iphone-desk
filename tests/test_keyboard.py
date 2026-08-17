from iphone_desk.keyboard import (
    KEY_A,
    KEY_ENTER,
    KEY_F1,
    KEY_LEFT_SHIFT,
    KEY_1,
    QT_KEY_EXCLAM,
    QT_KEY_F1,
    QT_KEY_RETURN,
    QT_KEY_SHIFT,
    hid_usage_for_qt_key,
    hid_usages_for_qt_key,
)


def test_letters_and_enter() -> None:
    assert hid_usage_for_qt_key(ord("A")) == KEY_A
    assert hid_usage_for_qt_key(QT_KEY_RETURN) == KEY_ENTER
    assert hid_usage_for_qt_key(QT_KEY_SHIFT) == KEY_LEFT_SHIFT
    assert hid_usage_for_qt_key(QT_KEY_F1) == KEY_F1


def test_unknown_key_is_none() -> None:
    assert hid_usage_for_qt_key(0) is None


def test_shift_1_is_exclamation() -> None:
    assert hid_usages_for_qt_key(QT_KEY_EXCLAM) == (KEY_LEFT_SHIFT, KEY_1)
    assert hid_usage_for_qt_key(QT_KEY_EXCLAM) == KEY_1
