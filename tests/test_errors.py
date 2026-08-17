from iphone_desk.errors import (
    REMOTE_CONTROL_FALLBACK_STATUS,
    humanize_device_error,
    is_remote_control_unsupported,
)

HELVIO_STARTMEDIASTREAM = (
    "Failed to invoke: com.apple.coredevice.feature.startmediastream. "
    "Got error: {'CoreDevice.error': {"
    "'userInfoWithNSSecureCoding': b'bplist00\\xd4\\x01NSKeyedArchiver', "
    "'code': 9021, "
    "'userInfo': {'NSLocalizedDescription': "
    "'Remote control requires iOS 27.0 or later on this device.'}, "
    "'domain': 'com.apple.dt.CoreDeviceError'}}"
)


def test_ios27_startmediastream_is_unsupported() -> None:
    exc = RuntimeError(HELVIO_STARTMEDIASTREAM)
    assert is_remote_control_unsupported(exc)


def test_humanize_hides_coredevice_plist() -> None:
    shown = humanize_device_error(RuntimeError(HELVIO_STARTMEDIASTREAM))
    assert shown == REMOTE_CONTROL_FALLBACK_STATUS
    assert "bplist" not in shown
    assert "NSKeyedArchiver" not in shown
    assert "9021" not in shown


def test_humanize_keeps_plain_desk_errors() -> None:
    assert humanize_device_error(RuntimeError("No USB iPhone found.")) == "No USB iPhone found."
