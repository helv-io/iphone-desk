# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-08-17

### Removed

- WiFi / Network usbmux as a connect path. It did not work. USB only again. The 0.3.0 WiFi history below is kept as history.

### Added

- Visible Video mode control (combo, last choice persisted). Switch after Connect reconnects the picture path only.
- HEVC live: CoreDevice DisplayService `start_video_stream`, local PyAV decode (no browser / WebCodecs). Queries `get-media-support-info` / `get-media-stream-server-status` when present. Sticky keyframe + RPS recovery like pymobiledevice3 serve-vnc. Decoder sub-option: PyAV auto or PyAV software.
- DVT screenshots: hot Instruments channel, JPEG if the service offers it, decode in memory, latest frame wins.
- Core Device stills: `ScreenCaptureService` as its own mode.
- Lockdown screenshotr: `com.apple.mobile.screenshotr` as its own mode.
- Auto: try HEVC, then DVT, then Core Device, then screenshotr, and show which one stuck.

### Changed

- usbmux picker accepts ConnectionType USB only. `set_enable_wifi_connections` is not called.
- Named modes do not silently fall back. A failed mode shows the real error and leaves the last good frame.
- Screenshot modes never call `startmediastream` / `ScreenStreamServer` / `touch_session`.

### Notes

- H.264 / Valeria was not shipped. Upstream dropped the libusb backend. On Windows, libusb usually needs WinUSB/Zadig, which replaces Apple Mobile Device Support.

## [0.3.0] - 2026-08-17

### Added

- Connect over WiFi after the first USB Trust. usbmux Network devices are accepted when no cable is present
- After Trust, lockdown WiFi connections are turned on (`EnableWifiConnections`) so later Connect can find the phone on the LAN
- Checklist transport row shows USB, WiFi, or both. Auto-scan picks up a network iPhone
- Status copy says which transport is in use (`Pairing over WiFi...`, `Connected to X over WiFi`)

### Changed

- USB is still preferred when the same UDID is visible over USB and WiFi
- `NoUsbDeviceError` is now `NoDeviceError` (alias kept). The empty-device message mentions USB or WiFi, including a sleeping phone that is not advertising
- First-run docs: plug in once, Trust, Developer Mode, leave WiFi enable on, then Connect on the same WiFi without the cable

## [0.2.1] - 2026-08-17

### Added

- Phone-shaped viewer: locked aspect ratio and iPhone-style rounded corners
- Auto-scan for a USB iPhone on the setup screen
- Long-press Home invokes Siri
- Taller volume buttons and a longer power button

### Changed

- Live video is decoded on the PC and painted on the phone canvas. The old in-app web page could connect and accept touch while showing a blank picture on Windows.
- Windows release is a folder bundle (`iPhoneDesk-<version>-windows-x64.zip`). Unzip and run `iPhoneDesk.exe` inside. The old one-file exe was failing to start.

### Fixed

- Shift+1 and other combo keys send the shifted character
- Keyboard is opened on the live-video path, not only on stills
- Build script stops a leftover `iPhoneDesk.exe` so the new bundle can overwrite it, then launches the result

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

[0.4.0]: https://github.com/helv-io/iphone-desk/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/helv-io/iphone-desk/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/helv-io/iphone-desk/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/helv-io/iphone-desk/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/helv-io/iphone-desk/releases/tag/v0.1.0
