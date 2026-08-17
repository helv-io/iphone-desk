"""Named picture paths. Each mode is an explicit choice, not a hidden fallback."""

from __future__ import annotations

from typing import Iterable

VIDEO_MODE_HEVC = "hevc"
VIDEO_MODE_DVT = "dvt"
VIDEO_MODE_CORE = "core"
VIDEO_MODE_SCREENSHOTR = "screenshotr"
VIDEO_MODE_AUTO = "auto"

VIDEO_MODE_ORDER: tuple[str, ...] = (
    VIDEO_MODE_HEVC,
    VIDEO_MODE_DVT,
    VIDEO_MODE_CORE,
    VIDEO_MODE_SCREENSHOTR,
    VIDEO_MODE_AUTO,
)

VIDEO_MODE_LABELS: dict[str, str] = {
    VIDEO_MODE_HEVC: "HEVC live",
    VIDEO_MODE_DVT: "DVT screenshots",
    VIDEO_MODE_CORE: "Core Device stills",
    VIDEO_MODE_SCREENSHOTR: "Lockdown screenshotr",
    VIDEO_MODE_AUTO: "Auto",
}

VIDEO_MODE_HINTS: dict[str, str] = {
    VIDEO_MODE_HEVC: (
        "CoreDevice DisplayService start_video_stream. Local PyAV decode. "
        "Not the HID remote-control path."
    ),
    VIDEO_MODE_DVT: "developer dvt screenshot. Hot Instruments channel. Stills only.",
    VIDEO_MODE_CORE: "developer core-device screen-capture. Reconnects each still.",
    VIDEO_MODE_SCREENSHOTR: "com.apple.mobile.screenshotr over lockdown.",
    VIDEO_MODE_AUTO: "Try HEVC, then DVT, then Core Device, then screenshotr. Shows which one stuck.",
}

AUTO_FALLBACK_ORDER: tuple[str, ...] = (
    VIDEO_MODE_HEVC,
    VIDEO_MODE_DVT,
    VIDEO_MODE_CORE,
    VIDEO_MODE_SCREENSHOTR,
)

STILL_MODES: frozenset[str] = frozenset(
    {VIDEO_MODE_DVT, VIDEO_MODE_CORE, VIDEO_MODE_SCREENSHOTR}
)

HEVC_DECODER_AUTO = "auto"
HEVC_DECODER_SOFTWARE = "software"

HEVC_DECODER_ORDER: tuple[str, ...] = (
    HEVC_DECODER_AUTO,
    HEVC_DECODER_SOFTWARE,
)

HEVC_DECODER_LABELS: dict[str, str] = {
    HEVC_DECODER_AUTO: "PyAV auto",
    HEVC_DECODER_SOFTWARE: "PyAV software",
}

SETTINGS_VIDEO_MODE = "video_mode"
SETTINGS_HEVC_DECODER = "hevc_decoder"


def normalize_video_mode(value: object, *, default: str = VIDEO_MODE_AUTO) -> str:
    text = str(value or "").strip().casefold()
    if text in VIDEO_MODE_LABELS:
        return text
    return default


def normalize_hevc_decoder(value: object, *, default: str = HEVC_DECODER_AUTO) -> str:
    text = str(value or "").strip().casefold()
    if text in HEVC_DECODER_LABELS:
        return text
    return default


def video_mode_label(mode: str) -> str:
    return VIDEO_MODE_LABELS.get(normalize_video_mode(mode), VIDEO_MODE_LABELS[VIDEO_MODE_AUTO])


def hevc_decoder_label(decoder: str) -> str:
    return HEVC_DECODER_LABELS.get(
        normalize_hevc_decoder(decoder), HEVC_DECODER_LABELS[HEVC_DECODER_AUTO]
    )


def is_still_mode(mode: str) -> bool:
    return normalize_video_mode(mode) in STILL_MODES


def combo_choices(order: Iterable[str], labels: dict[str, str]) -> list[tuple[str, str]]:
    return [(key, labels[key]) for key in order if key in labels]
