# Current state and boundaries

Recorded **2026-11-01**. This is a snapshot, not a fresh device query. Check Git
and `device_info` when continuing; do not overwrite newer evidence with this table.

## Source and installed components

| Component | Recorded state |
| --- | --- |
| Repository | `P1tt1cus/Echo-Firmware`, local directory often named `momentum_firmware` |
| Maintained branch | `studio`; sole local/fork branch by owner request |
| Last functional integration before handbook | `adc00d8eb`, merge of [PR #6](https://github.com/P1tt1cus/Echo-Firmware/pull/6) |
| Device | Flipper Zero named **Echo**, formerly Qwerty; f7, AU provisioned |
| Installed core | Echo 1.1, clean source `ae48bb3f`, API87.1 |
| Installed native FAPs | RFID 1.2; NFC 1.3; Sub-GHz 1.5; Add Manually 1.2; Replay Bench 1.2; Bad KB 1.1; Infrared 1.5 |
| Sub-GHz FAP source | `d3f612c2a`, including final RX-memory fix |
| Paired companion | Echo Radio 1.6, internal app ID `marauder_studio` |
| ESP32 | ZY-ESP32 / ESP32-D0WD-V3 / 4 MB, `studio.2-au`; latest GPIO link requires fresh verification |

A merged source commit is not automatically installed. Native app versions,
core source, SDK API and ESP32 firmware are four different version identifiers.
Full installed hashes/source metadata are retained locally in ignored
`build/workflow-polish-install/manifest.json`. The public
[workflow ledger](../workflow-polish.md) contains the durable evidence and limits.
The [target record](../../../studio-target.json) is the compatibility reference.

## What Echo already provides

- Desktop centre opens **Radio, Remotes, Sessions, Tools, Settings**. Tools keeps
  the full installed app menu. Radio and Sessions refer to the external companion.
- Shared Submenu/VariableItemList styling; native Echo dashboards; desktop pulse
  asset pack; branded firmware-only installer.
- Native RFID search/sense/checking feedback and actual read-back write status.
- NFC capture-completeness/capability feedback and original/modified-shadow clarity.
- Sub-GHz exact duplicate identity, bounded RAW parsing, offline EOF/error/cancel,
  RX memory allocation on demand and a separate Replay Bench FAP.
- BLE HID cancellation/disconnect feedback in Bad KB; IR parsed/RAW feedback,
  held-input cleanup, reorder Pick/Save/Cancel and staged file edits.
- Shared browser ownership/selection/cancellation and filename validation;
  staged RFID/NFC/Sub-GHz/IR saves with ordinary I/O failure recovery.

The proposed BLE Lab, advertising-impersonation workflows and Vox integration
are **not shipped features**. Do not invent menus or claim these were implemented.

## Verified and unverified

At the last functional integration, all **28** CI host checks, firmware/updater/
app builds and lint passed. Synthetic device tests covered file save/readback,
NFC original/shadow restore, browser empty/230-entry navigation, IR reorder,
RAW valid/invalid decode/cancel, Replay Bench prepare/cancel and representative
startup/exit. The final 15-file hash audit preserved settings/name/other apps.
Synthetic regression files were removed. No RF replay ran for UI testing.

Still unperformed: owned-tag physical RFID writes/reader acceptance; physical
NFC completeness/emulation/reader checks; Sub-GHz receiver acceptance; paired-host
BLE typing/reconnect; IR appliance response. Requirements are listed at the end
of the [ledger](../workflow-polish.md). The Kogan TV remote is not verified working.

Known limits:

- Staged saves are not power-loss-atomic. Preserve and expose recovery paths.
- Back cannot interrupt an individual blocked SD-driver call; cancellation occurs
  between operations.
- Existing TX API does not expose detailed late RAW worker errors in the TX UI.
- Earlier blank RPC frames/unexpected grouped-input navigation did not recur in
  the final startup pass; cause remains unconfirmed.
- Offline RAW decoding previously caused a real out-of-memory reboot. Fixed by
  allocating the 16 KB RX queue only during live reception, keeping it across
  hops and releasing it on full stop. Do not reintroduce eager RX allocation.

## Workspace boundaries

The owner's workspace commonly lives at
`~/Documents/projects/bug_reports/flipper/`. It contains three **separate Git
repositories**, plus historical root notes. The parent of that workspace is an
unrelated repository. Always `cd` into the intended component before Git writes;
never stage root notes by running `git add .` from the parent.

| Directory | Purpose |
| --- | --- |
| `momentum_firmware/` | Echo core, native apps, on-device JS engine, host tooling |
| `marauder_companion/` | Echo Radio C FAP; `P1tt1cus/flipperzero-wifi-marauder` |
| `esp32_marauder/` | External board source; `P1tt1cus/ESP32Marauder` |
| `marauder_firmware/` | Historical binaries, wiring and UART diagnostics, not the ESP source |
| `kogan_ir/` | TV remote troubleshooting and unverified codes |
| `~/Documents/projects/Vox/` | Owner's harness; read its own instructions before integration |

Native Echo does not require the ESP32. Read sibling `AGENTS.md` and README
before touching that component. The companion uses mntm-012 f7/API87.1 SDK;
its dashboard header must match Echo's. Older names/URLs/versions in chronological
workspace notes are historical. Prefer the latest explicit validation entry.
