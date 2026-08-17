from iphone_desk.device import DeviceSession
from iphone_desk.errors import DeskError


def test_session_starts_disconnected() -> None:
    session = DeviceSession()
    assert session.summary is None
    assert session.hevc_url is None
    assert session.display.width > 0


def test_desk_error_is_exception() -> None:
    assert issubclass(DeskError, Exception)
