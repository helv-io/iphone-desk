from iphone_desk.video_modes import (
    AUTO_FALLBACK_ORDER,
    HEVC_DECODER_AUTO,
    HEVC_DECODER_SOFTWARE,
    STILL_MODES,
    VIDEO_MODE_AUTO,
    VIDEO_MODE_CORE,
    VIDEO_MODE_DVT,
    VIDEO_MODE_HEVC,
    VIDEO_MODE_SCREENSHOTR,
    is_still_mode,
    normalize_hevc_decoder,
    normalize_video_mode,
    video_mode_label,
)


def test_normalize_and_labels() -> None:
    assert normalize_video_mode("DVT") == VIDEO_MODE_DVT
    assert normalize_video_mode("nope") == VIDEO_MODE_AUTO
    assert video_mode_label(VIDEO_MODE_HEVC) == "HEVC live"
    assert video_mode_label(VIDEO_MODE_DVT) == "DVT screenshots"
    assert video_mode_label(VIDEO_MODE_CORE) == "Core Device stills"
    assert video_mode_label(VIDEO_MODE_SCREENSHOTR) == "Lockdown screenshotr"
    assert video_mode_label(VIDEO_MODE_AUTO) == "Auto"


def test_auto_order() -> None:
    assert AUTO_FALLBACK_ORDER == (
        VIDEO_MODE_HEVC,
        VIDEO_MODE_DVT,
        VIDEO_MODE_CORE,
        VIDEO_MODE_SCREENSHOTR,
    )


def test_still_modes_do_not_include_hevc() -> None:
    assert VIDEO_MODE_HEVC not in STILL_MODES
    assert is_still_mode(VIDEO_MODE_DVT)
    assert not is_still_mode(VIDEO_MODE_HEVC)
    assert not is_still_mode(VIDEO_MODE_AUTO)


def test_decoder_normalize() -> None:
    assert normalize_hevc_decoder("SOFTWARE") == HEVC_DECODER_SOFTWARE
    assert normalize_hevc_decoder("nope") == HEVC_DECODER_AUTO
