## iPhone Desk 0.4.0

Same GitHub Release, two files:

- Windows bundle: `iPhoneDesk-0.4.0-windows-x64.zip` (unzip and run `iPhoneDesk.exe`)
- Linux AppImage: `iPhoneDesk-0.4.0-linux-x86_64.AppImage` (`chmod +x`, then run it)

On Windows, install Apple Mobile Device Support (`winget install Apple.AppleMobileDeviceSupport`). On Linux, install usbmuxd if the setup screen says the helper is missing (`sudo apt install usbmuxd` on Debian/Ubuntu; Fedora and Arch commands are in the README). The AppImage does not bundle that daemon.

- USB only. WiFi was removed because it did not work.
- Video mode control: HEVC live, DVT screenshots, Core Device stills, lockdown screenshotr, Auto
- HEVC decodes on the PC with PyAV. Decoder toggle: auto or software
- Named modes show the real error and keep the last frame. Auto is the only fallback
- Trust, Developer Mode, and iOS 17+ checks stay in place

See [CHANGELOG.md](https://github.com/helv-io/iphone-desk/blob/main/CHANGELOG.md) for the full list.
