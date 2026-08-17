"""Map Qt keys to HID Keyboard usage codes (page 0x07)."""

from __future__ import annotations

from PySide6.QtCore import Qt

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
KEY_RIGHT_CTRL, KEY_RIGHT_SHIFT, KEY_RIGHT_ALT, KEY_RIGHT_GUI = 0xE4, 0xE5, 0xE6, 0xE7


QT_TO_HID: dict[int, int] = {
    int(Qt.Key.Key_A): KEY_A,
    int(Qt.Key.Key_B): KEY_B,
    int(Qt.Key.Key_C): KEY_C,
    int(Qt.Key.Key_D): KEY_D,
    int(Qt.Key.Key_E): KEY_E,
    int(Qt.Key.Key_F): KEY_F,
    int(Qt.Key.Key_G): KEY_G,
    int(Qt.Key.Key_H): KEY_H,
    int(Qt.Key.Key_I): KEY_I,
    int(Qt.Key.Key_J): KEY_J,
    int(Qt.Key.Key_K): KEY_K,
    int(Qt.Key.Key_L): KEY_L,
    int(Qt.Key.Key_M): KEY_M,
    int(Qt.Key.Key_N): KEY_N,
    int(Qt.Key.Key_O): KEY_O,
    int(Qt.Key.Key_P): KEY_P,
    int(Qt.Key.Key_Q): KEY_Q,
    int(Qt.Key.Key_R): KEY_R,
    int(Qt.Key.Key_S): KEY_S,
    int(Qt.Key.Key_T): KEY_T,
    int(Qt.Key.Key_U): KEY_U,
    int(Qt.Key.Key_V): KEY_V,
    int(Qt.Key.Key_W): KEY_W,
    int(Qt.Key.Key_X): KEY_X,
    int(Qt.Key.Key_Y): KEY_Y,
    int(Qt.Key.Key_Z): KEY_Z,
    int(Qt.Key.Key_1): KEY_1,
    int(Qt.Key.Key_2): KEY_2,
    int(Qt.Key.Key_3): KEY_3,
    int(Qt.Key.Key_4): KEY_4,
    int(Qt.Key.Key_5): KEY_5,
    int(Qt.Key.Key_6): KEY_6,
    int(Qt.Key.Key_7): KEY_7,
    int(Qt.Key.Key_8): KEY_8,
    int(Qt.Key.Key_9): KEY_9,
    int(Qt.Key.Key_0): KEY_0,
    int(Qt.Key.Key_Return): KEY_ENTER,
    int(Qt.Key.Key_Enter): KEY_ENTER,
    int(Qt.Key.Key_Escape): KEY_ESC,
    int(Qt.Key.Key_Backspace): KEY_BACKSPACE,
    int(Qt.Key.Key_Tab): KEY_TAB,
    int(Qt.Key.Key_Space): KEY_SPACE,
    int(Qt.Key.Key_Minus): KEY_MINUS,
    int(Qt.Key.Key_Equal): KEY_EQUAL,
    int(Qt.Key.Key_BracketLeft): KEY_LBRACKET,
    int(Qt.Key.Key_BracketRight): KEY_RBRACKET,
    int(Qt.Key.Key_Backslash): KEY_BACKSLASH,
    int(Qt.Key.Key_Semicolon): KEY_SEMICOLON,
    int(Qt.Key.Key_Apostrophe): KEY_APOSTROPHE,
    int(Qt.Key.Key_QuoteLeft): KEY_GRAVE,
    int(Qt.Key.Key_Comma): KEY_COMMA,
    int(Qt.Key.Key_Period): KEY_DOT,
    int(Qt.Key.Key_Slash): KEY_SLASH,
    int(Qt.Key.Key_CapsLock): KEY_CAPS_LOCK,
    int(Qt.Key.Key_F1): KEY_F1,
    int(Qt.Key.Key_F2): KEY_F2,
    int(Qt.Key.Key_F3): KEY_F3,
    int(Qt.Key.Key_F4): KEY_F4,
    int(Qt.Key.Key_F5): KEY_F5,
    int(Qt.Key.Key_F6): KEY_F6,
    int(Qt.Key.Key_F7): KEY_F7,
    int(Qt.Key.Key_F8): KEY_F8,
    int(Qt.Key.Key_F9): KEY_F9,
    int(Qt.Key.Key_F10): KEY_F10,
    int(Qt.Key.Key_F11): KEY_F11,
    int(Qt.Key.Key_F12): KEY_F12,
    int(Qt.Key.Key_Left): KEY_LEFT,
    int(Qt.Key.Key_Right): KEY_RIGHT,
    int(Qt.Key.Key_Up): KEY_UP,
    int(Qt.Key.Key_Down): KEY_DOWN,
    int(Qt.Key.Key_Delete): KEY_DELETE,
    int(Qt.Key.Key_Home): KEY_HOME,
    int(Qt.Key.Key_End): KEY_END,
    int(Qt.Key.Key_PageUp): KEY_PAGEUP,
    int(Qt.Key.Key_PageDown): KEY_PAGEDOWN,
    int(Qt.Key.Key_Shift): KEY_LEFT_SHIFT,
    int(Qt.Key.Key_Control): KEY_LEFT_CTRL,
    int(Qt.Key.Key_Alt): KEY_LEFT_ALT,
    int(Qt.Key.Key_Meta): KEY_LEFT_GUI,
    int(Qt.Key.Key_Super_L): KEY_LEFT_GUI,
    int(Qt.Key.Key_Super_R): KEY_RIGHT_GUI,
}


def hid_usage_for_qt_key(key: int) -> int | None:
    """Return the HID usage for a Qt key, or None if we do not send it."""
    return QT_TO_HID.get(int(key))
