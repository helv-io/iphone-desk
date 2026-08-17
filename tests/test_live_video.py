from pathlib import Path

from iphone_desk.live_video import (
    LiveHevcPump,
    _is_key_nal,
    build_rtcp_pli,
    build_rtcp_rr,
    summarize_media_support,
)


def test_rtcp_rr_is_compound_packet() -> None:
    packet = build_rtcp_rr(1, 2, 99)
    assert packet[0] == 0x81
    assert packet[1] == 0xC9
    assert len(packet) == 44
    assert packet[32] == 0x81
    assert packet[33] == 0xCA


def test_rtcp_pli_is_12_bytes() -> None:
    packet = build_rtcp_pli(7, 9)
    assert len(packet) == 12
    assert packet[1] == 0xCE


def test_key_nal_types() -> None:
    assert _is_key_nal(19)
    assert _is_key_nal(20)
    assert _is_key_nal(21)
    assert not _is_key_nal(1)
    assert not _is_key_nal(32)


def test_pump_import_does_not_need_device() -> None:
    assert LiveHevcPump.__name__ == "LiveHevcPump"


def test_hevc_path_decodes_locally() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("iphone_desk", "device.py").read_text()
    start = text.index("async def _start_hevc")
    end = text.index("async def _start_dvt_stills")
    body = text[start:end]
    assert "ScreenStreamServer(" not in body
    assert "LiveHevcPump" in body
    live = Path(__file__).resolve().parents[1].joinpath("iphone_desk", "live_video.py").read_text()
    assert "LatestHevcTranscoder" in live
    assert "QWebEngine" not in live


def test_window_does_not_embed_webengine() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("iphone_desk", "window.py").read_text()
    assert "QWebEngine" not in text
    assert "hevc_ready" not in text
    assert "Video mode" in text


def test_summarize_media_support() -> None:
    assert summarize_media_support({"fps": 60, "width": 1264, "height": 2736}) == "1264x2736, 60 fps"
    assert summarize_media_support({}) == ""
