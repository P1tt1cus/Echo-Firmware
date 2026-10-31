# Echo 1.0

Echo is the personal firmware identity for this maintained Momentum fork. The
visible device name is **Echo**, without an owner name or edition suffix.
The original Momentum and Flipper attribution and licenses remain intact.

## Interface

The main launcher has five entries:

- **Radio** opens Echo Radio (companion 1.5 or later).
- **Remotes** opens the existing Infrared app.
- **Sessions** opens Echo Radio directly at its saved-file browser menu.
- **Tools** opens the full original app menu, including Applications and core tools.
- **Settings** opens the system settings menu.

The launcher shows an ECHO header and all five rows with small icons at once.
Up/Down wraps; short OK opens the selection. Back from Tools or Settings returns
to the Echo launcher. The existing full menu
configuration is retained for Tools. Echo Radio keeps the `marauder_studio` app ID
and `/ext/apps_data/marauder` storage so saved files and preferences continue to
work. The separate original Marauder companion is retained.

The **Echo** asset pack shows an expanding pulse and ECHO wordmark, followed by
PRESS OK. It is a desktop animation (one-second reveal, four-second hold), not a
replacement for the recovery screen or update-progress screen. Five original
monochrome launcher icons accompany it. No Vox integration is included yet.

## Build and install

The base is d3f89dfe, f7/API 87.1. The new icon symbols are private, leaving the
exported API unchanged. Build with the pinned toolchain (39):

```sh
FBT_NO_SYNC=1 ./fbt -j4 firmware_all updater_minpackage SKIP_EXTERNAL=1
python3 scripts/echo_validate.py
python3 scripts/echo_menu_test.py
```

Source dependencies must already be initialized recursively. `updater_minpackage`
contains the MCU firmware and updater only; it does not replace the radio stack
or SD resources/apps. Install the matching Echo Radio FAP separately. Generate
and pack Echo's theme with Pillow and heatshrink2 available:

```sh
python3 scripts/echo_assets.py
python3 -c 'from scripts.asset_packer import pack; pack("assets/dolphin/custom", "build/echo-assets", print)'
```

Copy `build/echo-assets/Echo` to `/ext/asset_packs/Echo`. Set `asset_pack: Echo`
and `menu_style: 6` (Compact) in the existing `/int/.momentum_settings.txt`,
preserving other settings. Set the device name through Momentum's name setting,
or write `/ext/dolphin/name.settings` using the existing Flipper Name File v1
format with `Name: Echo`. Both settings take effect after reboot. Re-enumerate
USB afterward: the port name changes from Qwerty to Echo. Close apps and release
the serial port before changing clients. Use binary-safe replacement uploads.

The validation script checks animation ordering/dimensions, every packed pixel,
private icon/API declarations and Git partial-clone version metadata. Build and
host checks are separate from on-device verification; record installed hashes
and actual device results in the workspace handoff.
