# iPhone Desk

Windows desktop app that shows a paired iPhone's screen and lets you tap and drag it.

Version 0.1.0. Owned by Helvio (helv-io / Helvio88).

## What this is

Screen plus touch for a phone you own. The PC must already be trusted by that iPhone, and Developer Mode must be on.

iPhone Desk is **not** Apple iPhone Mirroring. It is **not** Continuity. It does not use Apple ID pairing, does not show notifications, does not carry iMessage or call audio, and does not sync files or the clipboard.

It is **not** a jailbreak, **not** a remote-access implant, and it will not control a phone that has not tapped Trust on this computer.

It talks to Apple's own developer services through the public Python API of [pymobiledevice3](https://github.com/doronz88/pymobiledevice3). No Continuity or iPhone Mirroring protocols are reverse-engineered. Touch and screenshots go through pymobiledevice3 helpers (`universal-hid-service tap/drag`, `hid button`, `get-display-info`, `screen-capture`, `display serve-web`).

## Requirements

- Windows 10 or 11
- Python 3.12 or newer
- An iPhone on iOS 17 or later
- USB cable
- [Apple Mobile Device Support](https://support.apple.com/en-us/HT204144) (install [iTunes for Windows](https://www.apple.com/itunes/) or the Apple Devices app)
- Developer Mode enabled on the phone (after Trust, this PC can unhide that Settings row; you still flip the switch and restart)

## First run

1. Install Apple Mobile Device Support (iTunes or Apple Devices).
2. Plug the iPhone in over USB.
3. Unlock the phone and tap **Trust This Computer**.
4. After Trust, iPhone Desk asks iOS to show Developer Mode. Enable the switch under **Settings > Privacy & Security > Developer Mode**, then restart when iOS asks. The PC does not flip that switch for you.
5. Start iPhone Desk and click **Connect**.

The window repeats this checklist and can refresh USB / pairing / Developer Mode status before you connect.

On Connect the app:

1. Lists the USB device through usbmux
2. Pairs (or reuses an existing pair record) via lockdown
3. Asks iOS to show Developer Mode (AMFI reveal only; you still enable the switch), then checks that it is on
4. Runs `mounter auto-mount` so the Developer Disk Image is present (downloaded and cached, no Xcode required)
5. Opens pymobiledevice3's no-admin userspace RSD tunnel (`UserspaceRsdTunnel`)
6. Reads pixel size from `get-display-info`
7. Starts the screen session (screenshots by default; live HEVC only if you asked and the phone allows `startmediastream`)

## Start the app

From a command prompt in this repo:

```bat
start.bat
```

Or, after a one-time install:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m iphone_desk
```

`python -m iphone_desk` and the `iphone-desk` console script both open the window.

Optional live HEVC viewer (Qt WebEngine):

```bat
pip install -e ".[hevc]"
```

## Using the viewer

- The live screen fills the window (letterboxed).
- Mouse click sends a tap.
- Click-drag sends a drag.
- Scroll wheel sends a short vertical swipe.
- Toolbar: Home, Lock, volume, Disconnect.

HID coordinates are UInt16 values from 0 to 65535, with (0, 0) at the top-left. Window pixels are converted with the size from `get-display-info`.

## Screen modes

**Preferred:** `developer core-device display serve-web` (HEVC decoded in-browser with WebCodecs), embedded in the window when Qt WebEngine is installed.

**Windows fallback:** HEVC WebCodecs is often flaky or missing on Windows (the Microsoft HEVC Video Extensions package and a WebEngine build that can decode it). If the live picture is black or frozen, uncheck live HEVC or click **Screenshot fallback**. That loop uses `developer core-device screen-capture` (and can fall back to `developer dvt screenshot`) at about 8 frames per second. Usable, not 60 fps.

Screenshot-only connect does not call Apple's live remote-control video API (`startmediastream` / `touch_session` / `serve-web`). Some iPhones reject that API with "Remote control requires iOS 27". The screenshot path still shows the screen. Home / Lock / volume use Indigo HID and do not need that stream. Taps may be blocked on those phones because Universal HID is gated on the same video session.

If live HEVC is checked and the phone rejects `startmediastream`, iPhone Desk falls back to screenshots instead of showing a raw CoreDevice error dialog.

`serve-vnc` is macOS-only (VideoToolbox). This app does not depend on it.

Wi-Fi tunnels are a stretch goal. 0.1.0 is USB first.

## Out of scope

- Cloning macOS iPhone Mirroring or Continuity
- Notifications, iMessage, call audio, clipboard, file sync
- Jailbreak, sideload malware, passcode bypass
- Controlling a phone that has not trusted this computer

## Tests

```bat
pip install -e ".[dev]"
python -m pytest
```

Tests cover pixel-to-HID mapping, letterboxing, scroll-to-drag, display-info parsing, the tap/drag helpers, the post-Trust AMFI reveal that unhides Developer Mode, and screenshot connect avoiding `startmediastream`.

## Credits

Device access is implemented with [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) by doronz88 and contributors (GPL-3.0-or-later). iPhone Desk's own source is MIT. When you install this project you also install pymobiledevice3 and must follow its license.

## License

MIT. See `LICENSE`.
