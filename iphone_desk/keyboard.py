"""Map Qt key codes to HID Keyboard usage codes (page 0x07).

Qt.Key values are stored as integers so this module does not import PySide6.
"""

from __future__ import annotations

# HID Keyboard / Keypad page 0x07 (same values pymobiledevice3 uses).
KEY_A, KEY_B, KEY_C, KEY_D = 0x04, 0x05, 0x06, 0x07
KEY_E, KEY_F, KEY_G, KEY_H = 0x08, 0x09, 0x0A, 0x0B
KEY_I, KEY_J, KEY_K, KEY_L = 0x0C, 0x0D, 0x0E, 0x0F
KEY_M, KEY_N, KEY_O, KEY_P = 0x10, 0x11, 0x12, 0x13
KEY_Q, KEY_R, KEY_S, KEY_T = 0x14, 0x15, 0x16, 0x17
KEY_U, KEY_V, KEY_W, KEY_X = 0x18, 0x19, 0x1A, 0x1B
KEY_Y, KEY_Z = 0x1C, 0x1D
KEY_1, KEY_2, KEY_3, KEY_4, KEY_5 = 0x1E, 0x1F, 0x20, 0x21, 0x22
KEY_6, KEY_7, KEY_8, KEY_9, KEY_0 = 0x23, 0x24, 0x25, 0x26, 0x27
KEY_ENTER, KEY_ESC, KEY_BACKSPACE, KEY_TAB, KEY_SPACE = 0x28, 0x29, 0x2A, 0x2B, 0x2C
KEY_MINUS, KEY_EQUAL, KEY_LBRACKET, KEY_RBRACKET = 0x2D, 0x2E, 0x2F, 0x30
KEY_BACKSLASH, KEY_SEMICOLON, KEY_APOSTROPHE = 0x31, 0x33, 0x34
KEY_GRAVE, KEY_COMMA, KEY_DOT, KEY_SLASH = 0x35, 0x36, 0x37, 0x38
KEY_CAPS_LOCK = 0x39
KEY_F1, KEY_F2, KEY_F3, KEY_F4, KEY_F5, KEY_F6 = 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F
KEY_F7, KEY_F8, KEY_F9, KEY_F10, KEY_F11, KEY_F12 = 0x40, 0x41, 0x42, 0x43, 0x44, 0x45
KEY_RIGHT, KEY_LEFT, KEY_DOWN, KEY_UP = 0x4F, 0x50, 0x51, 0x52
KEY_DELETE = 0x4C
KEY_HOME, KEY_END, KEY_PAGEUP, KEY_PAGEDOWN = 0x4A, 0x4D, 0x4B, 0x4E
KEY_LEFT_CTRL, KEY_LEFT_SHIFT, KEY_LEFT_ALT, KEY_LEFT_GUI = 0xE0, 0xE1, 0xE2, 0xE3
KEY_RIGHT_GUI = 0xE7

# Qt::Key integers (qnamespace.h). Keep in sync with PySide6.QtCore.Qt.Key.
QT_KEY_ESCAPE = 0x01000000
QT_KEY_TAB = 0x01000001
QT_KEY_BACKSPACE = 0x01000003
QT_KEY_RETURN = 0x01000004
QT_KEY_ENTER = 0x01000005
QT_KEY_DELETE = 0x01000007
QT_KEY_HOME = 0x01000010
QT_KEY_END = 0x01000011
QT_KEY_LEFT = 0x01000012
QT_KEY_UP = 0x01000013
QT_KEY_RIGHT = 0x01000014
QT_KEY_DOWN = 0x01000015
QT_KEY_PAGEUP = 0x01000016
QT_KEY_PAGEDOWN = 0x01000017
QT_KEY_SHIFT = 0x01000020
QT_KEY_CONTROL = 0x01000021
QT_KEY_META = 0x01000022
QT_KEY_ALT = 0x01000023
QT_KEY_CAPSLOCK = 0x01000024
QT_KEY_F1 = 0x01000030
QT_KEY_SUPER_L = 0x01000053
QT_KEY_SUPER_R = 0x01000054
QT_KEY_SPACE = 0x20


def _letter_map() -> dict[int, int]:
    mapping: dict[int, int] = {}
    for offset, usage in enumerate(range(KEY_A, KEY_Z + 1)):
        mapping[ord("A") + offset] = usage
    for offset, usage in enumerate(range(KEY_1, KEY_9 + 1)):
        mapping[ord("1") + offset] = usage
    mapping[ord("0")] = KEY_0
    mapping[ord("-")] = KEY_MINUS
    mapping[ord("=")] = KEY_EQUAL
    mapping[ord("[")] = KEY_LBRACKET
    mapping[ord("]")] = KEY_RBRACKET
    mapping[ord("\\")] = KEY_BACKSLASH
    mapping[ord(";")] = KEY_SEMICOLON
    mapping[ord("'")] = KEY_APOSTROPHE
    mapping[ord("`")] = KEY_GRAVE
    mapping[ord(",")] = KEY_COMMA
    mapping[ord(".")] = KEY_DOT
    mapping[ord("/")] = KEY_SLASH
    return mapping


QT_TO_HID: dict[int, int] = {
    QT_KEY_RETURN: KEY_ENTER,
    QT_KEY_ENTER: KEY_ENTER,
    QT_KEY_ESCAPE: KEY_ESC,
    QT_KEY_BACKSPACE: KEY_BACKSPACE,
    QT_KEY_TAB: KEY_TAB,
    QT_KEY_SPACE: KEY_SPACE,
    QT_KEY_CAPSLOCK: KEY_CAPS_LOCK,
    QT_KEY_LEFT: KEY_LEFT,
    QT_KEY_RIGHT: KEY_RIGHT,
    QT_KEY_UP: KEY_UP,
    QT_KEY_DOWN: KEY_DOWN,
    QT_KEY_DELETE: KEY_DELETE,
    QT_KEY_HOME: KEY_HOME,
    QT_KEY_END: KEY_END,
    QT_KEY_PAGEUP: KEY_PAGEUP,
    QT_KEY_PAGEDOWN: KEY_PAGEDOWN,
    QT_KEY_SHIFT: KEY_LEFT_SHIFT,
    QT_KEY_CONTROL: KEY_LEFT_CTRL,
    QT_KEY_ALT: KEY_LEFT_ALT,
    QT_KEY_META: KEY_LEFT_GUI,
    QT_KEY_SUPER_L: KEY_LEFT_GUI,
    QT_KEY_SUPER_R: KEY_RIGHT_GUI,
}
QT_TO_HID.update(_letter_map())
for index, usage in enumerate(range(KEY_F1, KEY_F12 + 1)):
    QT_TO_HID[QT_KEY_F1 + index] = usage


def hid_usage_for_qt_key(key: int) -> int | None:
    """Return the HID usage for a Qt key, or None if we do not send it."""
    return QT_TO_HID.get(int(key))
