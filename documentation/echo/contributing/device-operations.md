# Device operations and troubleshooting

Run from the Echo repository root with the toolchain Python environment from
[build/test](build-and-test.md#toolchain). These are operational recipes, not an
instruction to deploy for every contribution. Documentation-only work needs no
firmware flash. Build/test first; deploy only the artifact required by the task.

## Discover and release the port

1. Quit qFlipper before serial CLI/storage/RPC. It holds the USB port.
2. Enumerate now; renaming/reboot/reconnect can change the path:

```sh
python3 -m serial.tools.list_ports
```

3. Assign the observed device path, for example on the established Mac:

```sh
export ECHO_PORT=/dev/cu.usbmodemflip_Echo1
python3 documentation/echo/contributing/examples/host/read_status.py \
  --port "$ECHO_PORT" --command 'loader info'
```

Use one client at a time, close its handle, then switch tools. `lsof "$ECHO_PORT"`
can help identify the owner on macOS. Do not kill arbitrary processes or assume
a UART problem from a busy/missing USB port. ESP32 CP2102 serial is a different
port; its environment does not make missing USB hardware appear.

For an interactive console:

```sh
python3 scripts/serial_cli.py -p "$ECHO_PORT"
```

This uses pyserial miniterm (Ctrl+] exits). Useful device commands:

```text
help
device_info
loader info
free
top
```

`device_info` identifies core commit/dirty/version/region, not every FAP version.
`free` reports total free heap, minimum and largest block. `top` is supported;
`ps` and `power info` are not established equivalents here. `loader close` depends
on the running app honoring its exit signal; a successful USB connection is not
proof that the app or its worker is healthy. Prefer normal Back after stopping
an active operation.

The read-only example's fixed reply window avoids returning on the first quiet
interval. For long commands, define an explicit deadline and parse a real terminal
result; do not infer success from an echo, silence or prompt alone. Never retry
writes, sends, pairing or scripts automatically after an uncertain timeout.

## Install one FAP

First close the target app and confirm `loader info` is idle. If replacing it,
record/download the existing artifact when appropriate for this task, and record
its hash. Earlier “no backup” applied to one historical installation, not all work.

Example destinations:

| Build artifact | Existing SD destination |
| --- | --- |
| `lfrfid.fap` | `/ext/apps/RFID/lfrfid.fap` |
| `nfc.fap` | `/ext/apps/NFC/nfc.fap` |
| `subghz.fap` | `/ext/apps/Sub-GHz/subghz.fap` |
| `subghz_add_manually.fap` | `/ext/apps/assets/subghz_add_manually.fap` |
| `echo_replay.fap` | `/ext/apps/Sub-GHz/echo_replay.fap` |
| `infrared.fap` | `/ext/apps/Infrared/infrared.fap` |
| `bad_kb.fap` | `/ext/apps/Tools/bad_kb.fap` |
| `momentum_app.fap` | `/ext/apps/assets/momentum_app.fap` |
| Companion `marauder_studio.fap` | `/ext/apps/GPIO/marauder_studio.fap` |
| New `echo_starter.fap` tutorial | `/ext/apps/Tools/echo_starter.fap` |

Binary-safe commands, illustrated for the tutorial:

```sh
python3 scripts/storage.py -p "$ECHO_PORT" send -f \
  build/f7-firmware-C/.extapps/echo_starter.fap /ext/apps/Tools/echo_starter.fap
python3 scripts/storage.py -p "$ECHO_PORT" size /ext/apps/Tools/echo_starter.fap
```

`scripts/storage.py` creates needed parent paths and removes an existing file
before binary replacement. Do not reuse append-only historical `/tmp/fpush.py`.
A correct size alone does not prove identical contents. Check MD5 and retain
SHA256 for the artifact manifest:

```sh
python3 - <<'PY'
import hashlib
import os
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from flipper.storage import FlipperStorage

local = Path('build/f7-firmware-C/.extapps/echo_starter.fap')
remote = '/ext/apps/Tools/echo_starter.fap'
data = local.read_bytes()
expected = hashlib.md5(data).hexdigest()
with FlipperStorage(os.environ['ECHO_PORT']) as storage:
    observed = storage.hash_flipper(remote).strip().lower()
if observed != expected:
    raise SystemExit('Device hash mismatch; do not launch')
print('MD5 matches:', expected)
print('Artifact SHA256:', hashlib.sha256(data).hexdigest())
PY
```

After releasing the storage client, use the device's Tools -> Apps -> Tools entry,
or type in the interactive CLI:

```text
loader open /ext/apps/Tools/echo_starter.fap
```

The tutorial checks are About -> Back -> Exit, reopen -> Back, loader idle and
heap after exit. Do not replace an existing same-named app you did not create.
Remove only the tutorial file when done, if this was a temporary exercise.

Generic file operations:

```sh
python3 scripts/storage.py -p "$ECHO_PORT" receive /ext/PATH build/LOCAL_COPY
python3 scripts/storage.py -p "$ECHO_PORT" send -f LOCAL_FILE /ext/PATH
python3 scripts/storage.py -p "$ECHO_PORT" list /ext/apps/Tools
```

Replace uppercase placeholders deliberately. Listing is recursive and captures
may contain private names: list the smallest relevant directory. Removal is
`remove /ext/EXACT_FILE`; directories must be empty. Never delete a user's broad
capture/data tree as test cleanup. Verify test-file identity/hashes first.

## Install an on-device JS script

```sh
python3 scripts/storage.py -p "$ECHO_PORT" send -f \
  documentation/echo/contributing/examples/scripts/echo_hello.js \
  /ext/apps/Scripts/echo_hello.js
```

Then select it from Apps -> Scripts, or run `js /ext/apps/Scripts/echo_hello.js`
in the interactive CLI. Use this finite, no-hardware example to verify the engine.
A script requiring GUI/serial/etc. also needs the corresponding installed JS
modules. Do not replace the JS Runner/module pack speculatively to fix one typo.

## Firmware-only core update

Only needed for a core/shared implementation change. Do not use an upstream web
updater to install Echo. Build `firmware_all updater_minpackage SKIP_EXTERNAL=1`
with the pinned toolchain and run the installer package check first.

1. Inspect the **specific generated package** under `dist/f7-C/`. It should contain
   `firmware.dfu`, `updater.bin`, `update.fuf`. Read the manifest: no radio-stack,
   resources or option-byte payload is intended for this ordinary update.
2. Record source/dirty status, API, hashes, current `device_info`, settings/name/
   app hashes and relevant files. Do not overwrite the installed recovery baseline.
3. Upload that directory to a unique `/ext/update/Echo-<source>/` using the storage
   tool; verify every package file hash. Do not choose a stale package by wildcard.
4. From Archive, open its `update.fuf` and confirm the Echo update. CLI alternative
   for an explicitly requested installation:

```text
update install /ext/update/Echo-SOURCE/update.fuf
```

5. The update reboots; USB disappearance/serial exceptions are expected during
   that transition. Re-enumerate after it returns, then query `device_info` and
   `loader info`. Verify the **actual** installed commit, clean/dirty metadata,
   API compatibility, AU region, desktop and preserved file hashes.
6. Install matching changed FAPs separately and hash-check them. A core package
   deliberately does not replace SD apps or Echo assets. Follow the existing
   [theme/install guide](../README.md) for an intentional asset-pack change.

Do not describe “command accepted” as “installation verified.” Do not flash via
SWD/DFU, erase storage, replace radio stack, migrate APIs or install a resources
bundle that removes apps as a routine recovery step. Those are separate tasks.

## On-device test procedure

Start from a known screen. Capture/inspect it before sending a button that can
activate an operation. Use synthetic fixtures with unique names. Verify source
hashes before/after tests and read saved output back over USB. Record screen,
loader, heap and the actual state transition, not just a tool exit code.

For RPC screen automation, use the current protobuf schema/client matching this
firmware (see `assets/protobuf` and the `rpc` service sources). A screen is 128x64
monochrome, 1024 bytes; receiving a frame is not proof that the app progressed.
Pair Press/Short-or-Long/Release correctly and prefer **one input per observed
transition**; grouped inputs previously produced ambiguous navigation. End the
RPC session and close serial before another client. Historical `/tmp/studio-rpc`
files are not a maintained dependency; use the user's available screen-control
client or build a proper client against these schemas rather than importing an
unavailable temporary Python module.

Test safe navigation first: open, long names, empty folders, details, Back, cancel,
reopen, exit. For RF/HID, use the user's owned fixture and explicit intended test.
For BLE typing use the selected paired host and blank editor with harmless text.
“Prepared” in Replay Bench does not transmit; OK/Send does. NFC direct launch may
emulate; use Saved -> Info for inspection. Never infer a physical response from
an on-screen success label. The [ledger](../workflow-polish.md) lists the remaining
physical tests and their pass evidence.

## Recovery and failure table

| Symptom | Next observation/action |
| --- | --- |
| No port / busy port | Re-enumerate, check cable/device mode and qFlipper/client ownership; release existing client |
| Missing Python module | Use pinned toolchain environment; for read-only example pyserial is required; don't change device firmware |
| Unknown `fap_<id>` target | Check manifest ID/location and whether SKIP_EXTERNAL excluded applications_user |
| Missing FAP import / wrong API | Check APPCHK, API CSV and SDK provenance; build from this checkout |
| App reports SD/file error | Inspect path/type/format and read-back; preserve original/recovery siblings; don't format SD |
| RAW Decode “File error” | Validate bounded RAW headers/records; compare first versus later corruption; not a TX-region failure |
| “Out of memory” crash screen | Record it as a real crash, core/app source, operation and last heap/largest-block data; inspect eager buffers/ownership |
| Blank RPC frame | Take a fresh capture, check loader/USB and known-safe Back; a blank frame alone isn't proof of a frozen app |
| Frozen app but CLI works | Stop via normal Back/app exit if possible; avoid opening a second hardware client; inspect worker/lock/join lifecycle |
| Whole device unresponsive | Record last state; stop serial clients. Historical successful physical recovery was unplug USB, hold Back for 30s, release, turn on if needed and reconnect. Recheck identity/loader; do not call it remotely recovered without evidence |
| GPIO companion silent | Different component: close app before diagnostic, read sibling guide and use meaningful protocol reply; don't alter native firmware/wiring by guesswork |

## Evidence to retain locally

Store build logs, prior changed FAP, artifact SHA256/MD5, device read-back hashes,
source/dirty status, screen captures and test results under an ignored unique
`build/<task>/` directory. Commit a concise public description of observations and
limits, never private fixtures. Use the result template in the task playbook.
