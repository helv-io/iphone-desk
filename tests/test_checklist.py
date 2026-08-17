from iphone_desk.checklist import (
    CHECKLIST_STEPS,
    ChecklistStatus,
    format_step_state,
    transport_step_label,
)


def test_checklist_mentions_trust_and_developer_mode() -> None:
    text = " ".join(CHECKLIST_STEPS)
    assert "Trust" in text
    assert "Developer Mode" in text
    assert "USB" in text
    assert "WiFi" in text
    assert "Apple Mobile Device" in text


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
