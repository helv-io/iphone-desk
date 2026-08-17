# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-17

### Added

- Windows one-file exe (`iPhoneDesk.exe`) via PyInstaller, plus `packaging/build.ps1`
- GitHub Actions release workflow: tests, then tagged Windows exe on `v*`
- App icon (window + exe)
- Live HID touch: press, move, long-press, release (no more mouse-up-only taps)
- Host keyboard forwarded as a virtual HID keyboard
- Phone chrome: volume on the left, power (`⏻`) on the right, Home at the bottom
- Parallel DVT stills (three channels) when live HEVC is rejected
- Preview downscale so the UI is not painting 3.6 MP PNGs
- `start.ps1` finds Python 3.12+ from `py`, PATH, or uv when `py -3.12` is missing

### Changed

- Connect always tries live HEVC, then falls back to stills. No HEVC checkbox. No Stills button.
- Setup screen is status only
- Lock uses the existing Indigo power usage (`0x0C` / `0x30`) as the side button
- Apple Mobile Device Support is documented as the standalone winget package. iTunes is not required.

### Fixed

- Developer Mode row is revealed after Trust (AMFI action 0 only)
- CoreDevice 9021 / "Remote control requires iOS 27" is a fallback, not a crash dialog
- Screenshot path does not call `startmediastream` / `touch_session`

## [0.1.0] - 2026-08-17

### Added

- First Windows viewer and touch client over USB
- Checklist for Apple Mobile Device Support, Trust, and Developer Mode
- pymobiledevice3 CoreDevice screen and HID through a userspace RSD tunnel

[0.2.0]: https://github.com/helv-io/iphone-desk/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/helv-io/iphone-desk/releases/tag/v0.1.0
