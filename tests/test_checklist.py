from iphone_desk.checklist import CHECKLIST_STEPS, WHAT_THIS_IS, ChecklistStatus, format_step_state


def test_checklist_mentions_trust_and_developer_mode() -> None:
    text = " ".join(CHECKLIST_STEPS)
    assert "Trust" in text
    assert "Developer Mode" in text
    assert "USB" in text
    assert "Apple Mobile Device" in text
    assert "this PC asks iOS to show Developer Mode" in text
    assert "Settings > Privacy & Security" in text


def test_what_this_is_is_not_apple_mirroring() -> None:
    assert "not Apple iPhone Mirroring" in WHAT_THIS_IS
    assert "not Continuity" in WHAT_THIS_IS
    assert "jailbreak" in WHAT_THIS_IS


def test_ready_requires_driver_and_usb() -> None:
    waiting = ChecklistStatus(True, False, None, None)
    assert not waiting.ready_to_connect()
    ready = ChecklistStatus(True, True, True, True)
    assert ready.ready_to_connect()


def test_step_states() -> None:
    rows = format_step_state(True, True, True, False)
    assert rows[0][1] == "ok"
    assert rows[1][1] == "ok"
    assert rows[2][1] == "ok"
    assert rows[3][1] == "fail"
