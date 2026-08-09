# VatsimConnect

ATC text alerts from **vPilot** to your Android phone.

## Important

Do not edit/publish any files without my (Inqsane's) permission. All files fall under Copyright.
If you want to edit any of the files or request anything please contact us unter david@virtualpilot.online or "inqsane" on discord.
Alternatively, contact us via the contact form on our website which will be available at some point. (WIP)

## What it does

- Windows app bridges vPilot (plugin + UI fallback) to your phone over the local network
- Live callsign / online status on the phone and notification
- Push-style ATC / radio / SELCAL alerts
- One-click **Setup EXE** — standalone installer (no other files needed)

## Homepage

https://virtualpilot.online

## Build

```powershell
.\build.ps1
```

Outputs in `dist\` (and Desktop):

- **`VatsimConnect-Setup.exe`** — one-click installer (Desktop / Start Menu shortcut). Self-contained — you only need this file.
- `VatsimConnect.exe` — raw Windows bridge (embedded inside the Setup)
- `VatsimConnect.apk` / `.aab` — Android app
- `VatsimConnect.dll` — vPilot plugin

### Install (Windows)

1. Run `VatsimConnect-Setup.exe` (or download it from [Releases](https://github.com/Inqsane/VatsimConnect/releases))
2. Click **Install** (or **Remove** to uninstall)
3. Restart **vPilot** once so the plugin loads
4. Install the Android APK on your phone and pair with the one-time code

Prefer to inspect source before running anything? Use **https://github.com/Inqsane/VatsimConnect/**

Make sure your APK / Play Store build matches your Windows build please don’t mix a website EXE with a random GitHub APK from another version.

### Requirements

- Windows + vPilot
- Android phone on the same network
- For Android release builds: JDK 17 + Android SDK; optional `android/keystore.properties` for signing

## Notes

- The installer copies the plugin into `%LOCALAPPDATA%\vPilot\Plugins`
- Do not download files from sources other than https://github.com/Inqsane/VatsimConnect or https://virtualpilot.online
