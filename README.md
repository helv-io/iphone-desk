# iPhone Desk

[![ci](https://github.com/helv-io/iphone-desk/actions/workflows/ci.yml/badge.svg)](https://github.com/helv-io/iphone-desk/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/helv-io/iphone-desk)](https://github.com/helv-io/iphone-desk/releases/latest)
[![downloads](https://img.shields.io/github/downloads/helv-io/iphone-desk/total)](https://github.com/helv-io/iphone-desk/releases)
[![license](https://img.shields.io/github/license/helv-io/iphone-desk)](LICENSE)

Windows app that shows a trusted iPhone over USB and sends touch, keys, and hardware buttons.

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

## First run

1. Plug the iPhone in over USB.
2. Unlock it and tap **Trust This Computer**.
3. After Trust, iPhone Desk asks iOS to show **Settings > Privacy & Security > Developer Mode**. Turn that on and restart when iOS asks.
4. Open iPhone Desk and click **Connect**.

Connect tries live video, then falls back to stills if the phone rejects the stream (common on iOS 26: "Remote control requires iOS 27").

## From source

Windows 10/11, Python 3.12+.

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

Build the exe:

```bat
packaging\build.ps1
```

## Credits

Device access is [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) (GPL-3.0-or-later). This repo is MIT. Installing the app also installs pymobiledevice3; follow both licenses.

## License

MIT. See `LICENSE`.
