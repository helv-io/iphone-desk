# iPhone Desk

[![ci](https://github.com/helv-io/iphone-desk/actions/workflows/ci.yml/badge.svg)](https://github.com/helv-io/iphone-desk/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/helv-io/iphone-desk)](https://github.com/helv-io/iphone-desk/releases/latest)
[![downloads](https://img.shields.io/github/downloads/helv-io/iphone-desk/total)](https://github.com/helv-io/iphone-desk/releases)
[![license](https://img.shields.io/github/license/helv-io/iphone-desk)](LICENSE)

Windows and Linux app that shows a trusted iPhone over USB and sends touch, keys, and hardware buttons.

Not Apple iPhone Mirroring. Not Continuity. Not a jailbreak. The phone must tap Trust on this PC, and Developer Mode must be on.

## Install

Grab the latest Windows zip from [Releases](https://github.com/helv-io/iphone-desk/releases/latest):

`iPhoneDesk-<version>-windows-x64.zip`

Unzip the folder and run `iPhoneDesk.exe` inside it.

You still need [Apple Mobile Device Support](https://support.apple.com/en-us/HT204144) on the PC:

```bat
winget install Apple.AppleMobileDeviceSupport
```

iTunes is not required.

On Linux, download `iPhoneDesk-<version>-linux-x86_64.AppImage` from the same release, then:

```bash
chmod +x iPhoneDesk-*-linux-x86_64.AppImage
./iPhoneDesk-*-linux-x86_64.AppImage
```

If the setup screen says the phone helper is missing, install usbmuxd (do not run sudo from the app):

```bash
# Debian / Ubuntu
sudo apt install usbmuxd

# Fedora
sudo dnf install usbmuxd

# Arch
sudo pacman -S usbmuxd
```

After usbmuxd is running, auto-scan / Connect works the same as on Windows. The AppImage does not bundle that daemon.

## First run

1. Plug the iPhone in over USB.
2. Unlock it and tap **Trust This Computer**.
3. After Trust, iPhone Desk asks iOS to show **Settings > Privacy & Security > Developer Mode**. Turn that on and restart when iOS asks.
4. Pick a **Video mode** (or leave Auto) and click **Connect**.

USB only. Network usbmux devices are ignored.

## Video mode

The window has a Video mode control. The last choice is remembered. You can switch after Connect. That reconnects the picture path only. Trust, the tunnel, and HID stay.

| Mode | What it is |
| --- | --- |
| HEVC live | CoreDevice DisplayService `start_video_stream`. Local PyAV decode to the phone canvas. Not the HID remote-control path. |
| DVT screenshots | `developer dvt screenshot`. Hot Instruments channel. Stills only. |
| Core Device stills | `developer core-device screen-capture`. Reconnects each still. |
| Lockdown screenshotr | `com.apple.mobile.screenshotr` over lockdown. |
| Auto | Try HEVC, then DVT, then Core Device, then screenshotr. Status shows which one stuck. |

If a named mode fails, the real error is shown and the last good frame stays. Auto is the only mode that tries the next path.

HEVC has a decoder sub-option: **PyAV auto** (try hardware, then software) or **PyAV software**. Needs the `av` package (already in the Windows zip).

Screenshot modes never call `startmediastream`, `ScreenStreamServer`, or `touch_session`.

H.264 / Valeria is not shipped. On Windows that path needs WinUSB/Zadig, which replaces Apple Mobile Device Support and breaks Trust.

## From source

Windows 10/11 or Linux, Python 3.12+.

```bat
start.bat
```

`start.ps1` finds Python from `py`, PATH, or a uv install.

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m iphone_desk
python -m pytest
```

Build the Windows zip:

```bat
packaging\build.ps1
```

On Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m iphone_desk
python -m pytest
./packaging/build-appimage.sh
```

The host still needs usbmuxd. The AppImage does not bundle that daemon.

## Credits

Device access is [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) (GPL-3.0-or-later). HEVC decode follows its `hevc_av` / serve-vnc path. This repo is MIT. Installing the app also installs pymobiledevice3; follow both licenses.

## License

MIT. See `LICENSE`.
