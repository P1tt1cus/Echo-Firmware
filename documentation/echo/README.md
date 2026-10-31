# Echo 1.1

[Echo Firmware](https://github.com/P1tt1cus/Echo-Firmware) is an independently
maintained Momentum fork. The
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
preserving other settings. Set the device name through Echo's configuration app (legacy loader ID `Momentum`),
or write `/ext/dolphin/name.settings` using the existing Flipper Name File v1
format with `Name: Echo`. Both settings take effect after reboot. Re-enumerate
USB afterward: the port name changes from Qwerty to Echo. Close apps and release
the serial port before changing clients. Use binary-safe replacement uploads.

The validation script checks animation ordering/dimensions, every packed pixel,
private icon/API declarations and Git partial-clone version metadata. Build and
host checks are separate from on-device verification; record installed hashes
and actual device results in the workspace handoff.

## App dashboards (native apps 1.1, Echo Radio 1.6)

Remotes, NFC and Sub-GHz now open a common Echo dashboard. Radio and Sessions
use the same layout in the companion. Four actions are visible with a scrolling
selection, a brief description below, and SD status or last board-reply age in
the header. Up/Down wraps, Left/Right jumps to first/last, short OK opens an
action, and Back returns. Debug actions remain locked when system debug is off.
Existing action scenes, saved files and settings are retained.

Build only the affected external apps; this update needs no MCU flash:

```sh
FBT_NO_SYNC=1 ./fbt -j4 fap_infrared fap_nfc fap_subghz SKIP_EXTERNAL=1
python3 scripts/echo_dashboard_test.py
```

Install `.extapps/infrared.fap`, `nfc.fap`, and `subghz.fap` from
`build/f7-firmware-C/` into their existing `/ext/apps/Infrared/`, `/ext/apps/NFC/`
and `/ext/apps/Sub-GHz/` locations. Close apps first and hash-verify replacements.
Core Echo 1.0/API 87.1 and ESP32 firmware are unchanged.

`applications/main/echo/echo_dashboard.h` is app-local and adds no firmware API.
Keep its companion copy at `studio/echo_dashboard.h` identical when changing
the shared renderer. Both repositories exercise the real header with sanitizer
tests for navigation, bounds, action IDs, locked actions and model locking.
App structure fields and view IDs are appended to preserve existing offsets.

## Shared menus (Echo 1.1)

Echo styling now lives in the firmware's shared Submenu and VariableItemList
controls. Existing API 87.1 FAPs inherit it without rebuilding: built-in tools,
settings, nested menus and third-party apps using those controls. The Compact
Tools launcher also uses the Echo layout; other launcher styles stay available.
Screens that draw their own UI (games, file browsers, keyboards and live tools)
retain their app-specific controls. This is a shared menu update, not a rewrite
of every third-party renderer.

Menus show a title, selection count, four rows, a scrollbar and a footer.
Portrait submenus fit ten rows. Caller-provided headers take priority; other
titles come from the allocating app thread. Submenus add small action icons and
hints for recognised actions. Settings retain their values, Left/Right changes,
locked-item explanations, scrolling labels and existing callbacks. Extended
OK events remain available to apps that register them. Tools uses Left/Right
to jump to first/last. Empty/reset lists and selection removal are handled safely.

The implementation is private to GUI; API 87.1 and public signatures are
unchanged. Run `python3 scripts/echo_shared_menu_test.py` (actual production
controls, real m-array, sanitizer host adapter), existing Echo checks and
`firmware_all updater_minpackage SKIP_EXTERNAL=1`. Install the firmware-only
package and preserve SD resources, settings and FAPs. Verify representative
settings, built-in and unmodified third-party app menus on the device.

## Echo installer

The update confirmation displays **Install Echo / Echo 1.1**. During installation,
the private code-drawn pulse and ECHO wordmark accompany real overall progress,
a plain-language stage and a restart screen. Error screens retain the exact
diagnostic and stage code, short-OK retry and long-Back exit. Flash validation,
backup/restore, power controls and recovery logic are unchanged.

Default artifacts use `echo-1.1-<commit>`; the visible manifest Info is simply
`Echo 1.1`. The package-version argument is quoted so its space survives SCons.
Source commit/branch remain in device diagnostics. When bumping the version,
update `scripts/version.py`, `fbt_options.py`, the default in
`site_scons/commandline.scons`, and the installer identity assertions together.

Run `python3 scripts/echo_installer_test.py --package-check` after the firmware
and updater build. It checks the production renderer at every progress value,
restarts, SD wait, diagnostics and generated package identity. The renderer
can also be included in a temporary preview FAP for on-device visual checks;
remove the preview afterward. RPC is unavailable during the RAM flasher, so
distinguish preview screenshots from actual install completion evidence.

The updater restarts between backup, flashing and restore. Its restart screen
says **Restarting Echo**, never declares completion before the desktop returns.

## Repository branding

The maintained repository is **P1tt1cus/Echo-Firmware**; the local workspace
folder remains `momentum_firmware` and the branch remains `studio`. Momentum is
retained as upstream attribution. The CLI `src` command and fallback source
metadata point to Echo. Menus display the legacy `Momentum` configuration app
as **Echo**, retaining its loader ID, keybinds and saved menu entries.

Build `fap_momentum_app` for its menu-editor label update; install the resulting
`build/f7-firmware-C/.extapps/momentum_app.fap` at
`/ext/apps/assets/momentum_app.fap`. This is separate from a firmware-only update.
The historical `MNTM` menu style remains a legacy layout; Echo uses Compact.
Repository branding changes do not require a device rename or erase.

## Sub-GHz Replay Bench

[Replay Bench](replay-bench.md) compares saved captures and prepares a bounded
replay with separate manual receiver observations. Install the Sub-GHz 1.2
dashboard and Echo Replay Bench 1.0 FAPs together; API 87.1 and the installed
core remain compatible. The bench runs separately to leave heap for SD browsing
and RAW encoding.
