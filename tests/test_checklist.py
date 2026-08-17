from iphone_desk.checklist import (
    CHECKLIST_STEPS,
    ChecklistStatus,
    checklist_steps,
    format_step_state,
    phone_helper_label,
    phone_helper_missing_detail,
    phone_helper_missing_error,
    transport_step_label,
)


def test_checklist_mentions_trust_and_developer_mode() -> None:
    text = " ".join(checklist_steps("Windows"))
    assert "Trust" in text
    assert "Developer Mode" in text
    assert "USB" in text
    assert "WiFi" in text
    assert "Apple Mobile Device" in text
    linux = " ".join(checklist_steps("Linux"))
    assert "usbmuxd" in linux
    assert "Trust" in linux
    assert "WiFi" in linux
    assert "Apple Mobile Device" not in linux


def test_ready_requires_driver_and_transport() -> None:
    waiting = ChecklistStatus(True, False, None, None)
    assert not waiting.ready_to_connect()
    usb = ChecklistStatus(True, True, True, True)
    assert usb.ready_to_connect()
    wifi = ChecklistStatus(True, False, True, True, wifi_present=True)
    assert wifi.ready_to_connect()
    both = ChecklistStatus(True, True, True, True, wifi_present=True)
    assert both.ready_to_connect()


def test_step_states() -> None:
    rows = format_step_state(True, True, True, False)
    assert rows[0][1] == "ok"
    assert rows[1] == ("USB", "ok")
    assert rows[2][1] == "ok"
    assert rows[3][1] == "fail"


def test_transport_step_labels() -> None:
    assert transport_step_label(False, False) == "USB / WiFi"
    assert transport_step_label(True, False) == "USB"
    assert transport_step_label(False, True) == "WiFi"
    assert transport_step_label(True, True) == "USB + WiFi"
    wifi = format_step_state(True, False, True, True, wifi_present=True)
    assert wifi[1] == ("WiFi", "ok")
    both = format_step_state(True, True, True, True, wifi_present=True)
    assert both[1] == ("USB + WiFi", "ok")
    none = format_step_state(True, False, None, None)
    assert none[1] == ("USB / WiFi", "wait")


def test_helper_copy_windows() -> None:
    assert phone_helper_label("Windows") == "Apple Mobile Device Support"
    assert "Apple Mobile Device Support" in phone_helper_missing_error("Windows")
    assert "sudo apt" not in phone_helper_missing_error("Windows")
    assert "Apple Mobile Device Support" in phone_helper_missing_detail("Windows")
    assert format_step_state(False, False, None, None, system="Windows")[0][0] == (
        "Apple Mobile Device Support"
    )


def test_helper_copy_linux() -> None:
    assert phone_helper_label("Linux") == "usbmuxd"
    err = phone_helper_missing_error("Linux")
    assert "sudo apt install usbmuxd" in err
    assert "Apple Mobile Device" not in err
    detail = phone_helper_missing_detail("Linux")
    assert "sudo apt install usbmuxd" in detail
    assert "USB" in detail
    assert format_step_state(False, False, None, None, system="Linux")[0][0] == "usbmuxd"


def test_helper_copy_follows_platform(monkeypatch) -> None:
    monkeypatch.setattr("iphone_desk.checklist.platform.system", lambda: "Linux")
    assert phone_helper_label() == "usbmuxd"
    assert "sudo apt install usbmuxd" in phone_helper_missing_error()
    monkeypatch.setattr("iphone_desk.checklist.platform.system", lambda: "Windows")
    assert phone_helper_label() == "Apple Mobile Device Support"
    assert "Apple Mobile Device Support" in phone_helper_missing_error()


def test_default_checklist_steps_match_this_os() -> None:
    assert CHECKLIST_STEPS[0] == phone_helper_label()
    assert "Trust" in CHECKLIST_STEPS
    assert "Developer Mode" in CHECKLIST_STEPS
    assert "USB / WiFi" in CHECKLIST_STEPS
