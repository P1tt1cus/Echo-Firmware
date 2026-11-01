# Build, test and integrate

## Toolchain

Commands in this handbook assume a POSIX shell and repository root. A fresh
checkout is:

```sh
git clone --branch studio --recurse-submodules https://github.com/P1tt1cus/Echo-Firmware.git
cd Echo-Firmware
```

For the owner's existing workspace:

```sh
cd ~/Documents/projects/bug_reports/flipper/momentum_firmware
git status --short
git branch --show-current
git remote -v
```

Use `studio`; preserve unrelated edits. Do not rerun clone over this directory.
`git submodule status --recursive` checks pins. Missing initialization can be
repaired with `git submodule update --init --recursive` after inspecting local
submodule changes. Never use `git submodule update --remote` for routine setup.

On the established Mac, toolchain 39 is installed under `~/.ufbt`:

```sh
export FBT_TOOLCHAIN_PATH="$HOME/.ufbt"
export FBT_NO_SYNC=1
./fbt -j4 fap_infrared SKIP_EXTERNAL=1
```

On a new machine omit that path override and let `./fbt` bootstrap its configured
toolchain. Do not set it to a nonexistent directory. `FBT_NO_SYNC=1` prevents
automatic submodule synchronization; it does not supply missing submodule files.

For Python checks and tooling, source the same environment **in the shell that
will run the command**:

```sh
export FBT_TOOLCHAIN_PATH="$HOME/.ufbt"
. scripts/toolchain/fbtenv.sh
python3 --version
python3 scripts/echo_dashboard_test.py
```

Omit the override on a fresh machine using repo-local toolchain. The environment
contains the firmware's Python dependencies (including asset tooling). Host C
sanitizer tests also require `cc` with ASAN/UBSAN: macOS Command Line Tools or an
appropriate Linux compiler. A subprocess invocation does not permanently modify
its parent shell. In agent tools, repeat the exports/source per command or use
the verified absolute toolchain Python path. Do not install a random latest SDK
to fix missing Python imports.

`ufbt` is used by the separate companion, pinned there to **mntm-012/API87.1**.
For native Echo use this checkout's fbt. A current official API88.x SDK is not the
installed target. API check:

```sh
sed -n '2p' targets/f7/api_symbols.csv
```

Expected: `Version,+,87.1,,`.

## Build targets

| Change | Command targets | Output / deployment |
| --- | --- | --- |
| New user C starter | `./fbt -j4 fap_echo_starter` | `.extapps/echo_starter.fap`; omit SKIP_EXTERNAL |
| Existing native FAP | `./fbt -j4 fap_infrared SKIP_EXTERNAL=1` | `.extapps/infrared.fap`; replace only the intended app |
| Sub-GHz helper | `./fbt -j4 fap_subghz fap_subghz_add_manually fap_echo_replay SKIP_EXTERNAL=1` | Three FAPs share helper code |
| Core/library/shared GUI | `./fbt -j4 firmware_all updater_minpackage SKIP_EXTERNAL=1` | `.dfu`, updater and `.fuf`; core update required |
| All currently maintained native targets | Full command below | Matches firmware CI |
| On-device JS / host script | No fbt for a standalone script | Test correct interpreter/module version |

```sh
./fbt -j4 firmware_all updater_minpackage \
  fap_infrared fap_nfc fap_subghz fap_momentum_app fap_echo_replay \
  fap_lfrfid fap_bad_kb fap_subghz_add_manually SKIP_EXTERNAL=1
```

FAP output is normally `build/f7-firmware-C/.extapps/`. Firmware-only packages
are under `dist/f7-C/f7-update-echo-1.1-<source>/`; inspect generated paths rather
than guessing a hash or choosing the oldest directory. Building does not flash.
`./fbt launch` **does** deploy/run; use only when intended. Debug/release or dirty
source metadata can change output hashes; record the exact source/build state.

## Choose checks by impact

Run scripts as `python3 scripts/<name>.py`. Table entries omit `echo_` prefix
and `_test.py` suffix for compactness; e.g. `browser` means `echo_browser_test.py`.

| Changed behavior | Relevant checks |
| --- | --- |
| Assets, version, identity | `echo_validate.py`; `menu`, `dashboard`, `installer --package-check` |
| Shared menus | `shared_menu`, `menu`, `dashboard`; representative app settings on device |
| Browser and naming | `browser`, `filename`; native file-save checks for affected callers |
| RFID | `rfid`, `file_save`; its save scenes are included in file-save checks |
| NFC | `nfc_status`, `nfc_save`, `file_save` |
| Sub-GHz | `subghz_history`, `subghz_control`, `subghz_memory`, `subghz_file`, `subghz_save`, `replay`, `replay_control` |
| BLE HID | `hid_control`, `hid_view`, `hid_profile` |
| IR | `ir_view`, `ir_move`, `ir_control`, `ir_file`, `ir_exit`, `ir_save`, `ir_save_scene`, `file_save` |
| Shared staged-save helper | `file_save`, `nfc_save`, `subghz_save`, `ir_save`, `ir_save_scene` |

These compile production code/functions with host adapters and sanitizers; read
the test's header and assertions to understand its coverage. A scheduling adapter
does not validate MCU ISR/DMA timing. Extraction tests can break when function
layout changes: update extraction to the real code rather than weakening behavior
assertions or replacing production functions with a second implementation.

For meaningful new operation tests, cover success plus the failure boundaries:
short read/write, close failure, absent file/SD, malformed first/later record,
empty list, cancellation while active, repeated start/stop, duplicate events,
clock wrap, failed start and ownership after exit. Choose what applies. A static
label change does not need a new mirror-image test.

## Full registered host suite

The executable source of truth is `.github/workflows/build.yml`. It currently
registers 28 checks including assets/installer checks. After building the core
package, this runs the exact listed commands sequentially:

```sh
python3 - <<'PY'
from pathlib import Path
import shlex
import subprocess
import sys

lines = Path('.github/workflows/build.yml').read_text().splitlines()
commands = [line.strip() for line in lines if line.strip().startswith('python3 scripts/echo_')]
if not commands:
    raise SystemExit('No registered Echo checks found; inspect workflow format')
for command in commands:
    print(command, flush=True)
    subprocess.run([sys.executable, *shlex.split(command)[1:]], check=True)
print('Passed', len(commands), 'registered checks')
PY
```

This avoids a stale handwritten shell loop and stops at the first failure. It
only understands the workflow's current one-line command format; inspect changes
to the workflow before reusing. It does not run the firmware build or lint.

## Format and review

```sh
./fbt lint_all
git diff --check
git diff --stat
git diff -- targets/f7/api_symbols.csv
git diff --submodule=short
```

Use toolchain `clang-format` on changed C/H and `python3 -m black` on changed
Python. Do not format unrelated files or update dependencies to silence warnings.
The existing missing-manifest `main/echo` helper directory and `.cli_gui`/
`.f0_mtp` app-ID warnings have appeared in passing builds; inspect the actual
final error/APPCHK rather than assuming any warning caused failure.

## Single-branch integration

The owner explicitly wants only `studio`. Do not open a new persistent branch.
Before editing, fetch origin and inspect divergence; fast-forward a clean local
`studio` when appropriate. Preserve user edits and never force-push to simplify
history. For a small reviewed change:

```sh
git add path/to/intended/file
git diff --cached
git commit -m 'Describe the concrete change'
git push origin studio
gh run list -R P1tt1cus/Echo-Firmware --branch studio --limit 5
```

Check the jobs for **your exact commit**; a previous green run is not evidence.
Use `gh run view RUN_ID -R P1tt1cus/Echo-Firmware --log-failed` for failures.
Fix them on `studio` with focused follow-up commits. Do not equate push success,
CI success and an installed update. Existing PR references are historical; this
policy supersedes earlier feature-branch instructions.

Only stage files in this repository. Root workspace notes live outside it; never
include a parent's unrelated changes. If a task requires an API/dependency or
hardware migration, specify that scope and its tests before editing those parts.
