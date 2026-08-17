from iphone_desk.checklist import CHECKLIST_STEPS, ChecklistStatus, format_step_state


def test_checklist_mentions_trust_and_developer_mode() -> None:
    text = " ".join(CHECKLIST_STEPS)
    assert "Trust" in text
    assert "Developer Mode" in text
    assert "USB" in text
    assert "WiFi" not in text
    assert "Apple Mobile Device" in text


def test_ready_requires_driver_and_usb() -> None:
    waiting = ChecklistStatus(True, False, None, None)
    assert not waiting.ready_to_connect()
    usb = ChecklistStatus(True, True, True, True)
    assert usb.ready_to_connect()
    no_driver = ChecklistStatus(False, True, True, True)
    assert not no_driver.ready_to_connect()


def test_step_states() -> None:
    rows = format_step_state(True, True, True, False)
    assert rows[0][1] == "ok"
    assert rows[1] == ("USB", "ok")
    assert rows[2][1] == "ok"
    assert rows[3][1] == "fail"
    none = format_step_state(True, False, None, None)
    assert none[1] == ("USB", "wait")
