# Architecture and contracts

## Find the implementation before editing

Start with `rg -n 'symbol_or_label' applications lib targets scripts`. Read the
containing function, its callers and its matching free/stop function. A public
header declaring a function does not mean an external FAP can import it: also
check `targets/f7/api_symbols.csv`. A `+` entry exports it; a `-` entry does not.
Do not export a new symbol just to fix a missing-import error.

| Area | Entry points / examples |
| --- | --- |
| Five-entry launcher | `applications/services/loader/loader_menu.c` |
| Shared menu rendering | `applications/services/gui/modules/echo_menu.h`, `submenu.c`, `variable_item_list.c` |
| App-local Echo dashboard | `applications/main/echo/echo_dashboard.h` |
| Staged saves | `applications/main/echo/echo_file_save.h` and `scripts/echo_file_save_test.py` |
| Browser/name validation | `applications/services/gui/modules/file_browser*`, `validators.c` |
| RFID | `applications/main/lfrfid/`, `lib/lfrfid/` |
| NFC | `applications/main/nfc/`, protocol support plugins, `lib/nfc/` |
| Sub-GHz / Bench | `applications/main/subghz/`, `subghz_replay_app.c`, `helpers/subghz_replay_data.c`, `lib/subghz/` |
| BLE/USB HID | `applications/main/bad_usb/` (build/app ID is **bad_kb**) |
| IR | `applications/main/infrared/`, `lib/infrared/signal/` |
| Settings / installer | `applications/main/momentum_app/`, `applications/system/updater/` |
| JS engine and modules | `applications/system/js_app/` |
| SDK API / configuration | `targets/f7/api_symbols.csv`, `studio-target.json`, `application.fam` files |
| Build tooling / host checks | `fbt`, `scripts/fbt_tools/`, `scripts/echo_*test.py`, `.github/workflows/` |

`application.fam` determines app IDs, entry points, source lists, embedded plugins,
requirements and stack size. Some FAPs compile the same helper with different
`cdefines`; changing it requires checking **every** consumer. NFC support plugins
are bundled by its build. Sub-GHz helper changes can affect Sub-GHz, Add Manually
and Replay Bench. A changed source list can silently omit needed code.

## GUI and event flow

Use this flow for a tool with background work:

```text
Input callback -> queue a custom event -> dispatcher / scene manager
                                      -> start / cancel worker
Worker -> bounded result/status -> dispatcher event or tick -> update model
Draw -> read model and render only
```

- `ViewDispatcher` owns event dispatch and registered view IDs; it does not own
  every separately allocated view object. `SceneManager` supplies lifecycle and
  state transitions for larger apps. Register, remove and free views explicitly.
- Standard `Submenu` and `VariableItemList` inherit Echo styling. Prefer these for
  simple tools. The C starter demonstrates a submenu and details screen.
- To use the private dashboard, read its real `echo_dashboard_configure()`
  signature. It keeps pointers to title/items; these must outlive the view.
  Status is copied into 9 bytes (8 visible characters). Callbacks should enqueue
  events. This header adds no firmware export. If editing it, keep the companion
  copy `studio/echo_dashboard.h` byte-identical and test both repositories.
- Custom draw functions get model context; input functions get their configured
  view context. Do not cast them interchangeably. Never perform SD I/O, parse a
  file, start a worker or call a blocking dialog during draw.
- Keep `with_view_model` sections short. Collect action/context under the lock;
  release it **before** calling another component, posting actions that may
  re-enter the view, or waiting for a worker. Lock re-entry can freeze the device.
- Distinguish Press, Release, Short, Long and Repeat. Do not trigger one-shot work
  for both Press and Short. Held transmission must stop on release, Back and exit;
  queued repeats must not resurrect a cancelled operation.
- Short OK selects; Back returns/cancels. Show meaningful controls on live views.
  Keep settings Left/Right and standard extended callbacks/locked explanations.
  Preserve selection after details, cancelled operations and file rename.

## Ownership and shutdown

Initialize optional pointers/flags (`calloc` or explicit fields). Write down each
owner, borrowed pointer and transfer. Avoid two owners of one RAW buffer. The IR
signal setter's copy/ownership rules differ from internal parser transfer: read
the implementation before reusing them.

Normal shutdown order:

1. Mark stopping and reject new work; clear held/pending-send intent.
2. Disable hardware/ISR producers before stopping queues they feed.
3. Ask the worker to stop and join it **without holding the view model lock**.
4. Close files/streams; process failure/recovery feedback while context still lives.
5. Unregister views; free dispatcher, view modules and models in the order their
   API requires. Close each opened record, then free application context.

App exit, Back, timeout, disconnect, failed start and file-open errors must all
leave the same resource invariants. Do not invoke a callback that waits on the
thread currently invoking it. The RAW completion path polls on the dispatcher
rather than calling into a stop/join cycle from its own worker.

## Memory is a runtime constraint

FAP code/data loads into RAM. FAP file size is not its heap allocation. Measure
`free` at app idle, browser, worker start, completion and exit; inspect both free
bytes and largest block. A large contiguous allocation can fail despite enough
combined free space. Keep large buffers off the app thread's small stack.

Prefer bounded streaming and on-demand worker allocation. A larger `stack_size`
is not a solution to heap exhaustion. Do not shrink RF buffer capacities just to
make a UI test pass. Replay Bench is separate deliberately, leaving memory for
its file browser/encoder. Do not fold it into the full Sub-GHz app without data.

Keep lengths/counts bounded, check arithmetic before allocation/progress division,
and handle empty lists/files. Use clock-wrap-safe unsigned elapsed time comparisons.
Separate file bytes read, pulses processed, DMA completion and target response.

## Storage and recovery

Use `/ext/apps_data/<appid>/` for new app data and retain established paths for
existing tools. Distinguish `FSE_NOT_EXIST` from SD/stat failure. Validate names
with existing validator behavior; reject empty/dot names, separators, invalid FAT
characters and trailing dot/space. A stat error is not an available filename.

New files must reject collisions. Replacing an existing file must be intentional.
For existing native apps, follow their tested staged-save flow:

- Write to an exclusively reserved sibling `.echo-new-N`.
- Check complete writes, flush/sync and close. Free buffered streams before
  cleanup/rename when their close may still own the underlying file.
- Retain/move an existing original to `.echo-old-N`, then commit the replacement.
- On commit failure, restore the original; on failed restore, preserve and report
  the recovery path. Do not remove the last usable copy.
- Keep edit text/selection/data for retry. A cleanup failure after a successful
  commit is different from an unsuccessful save.

The shared helper is **private**, not an API87.1 import. Copying it into a new
FAP requires an explicit app-local dependency or include path and appropriate
fault-injection tests; do not invent a public `echo_*` symbol. NFC original and
shadow files require the existing paired-save/rename logic, not two independent
unchecked writes. Staged saves are not a power-cut transaction.

## Capability and hardware boundaries

Native LF RFID, NFC, IR, Sub-GHz and existing BLE tools use the Flipper itself.
External-board Wi-Fi/GPS/etc. does not appear because a native menu exists. Use
existing region checks; preserve AU provisioning. A UI test must never press Send
or begin emulation just to see a details screen. NFC direct-file launch can start
emulation; use Saved -> Info for inspection. RAW direct launch can be send-only;
use Sub-GHz Saved -> More -> Decode for offline checks.

Represent at least idle/starting/running/stopping/finished/error where needed.
Only a successful start establishes running. Only a meaningful parsed response
establishes a companion link; echoes and prompt characters do not. Silence is not
completion. BLE HID reconnect must not resume a cancelled sequence automatically.
An encoder finishing does not prove receiver acceptance. Tag sensing is not a
validated decode; write read-back is not independent reader acceptance.

## Preserve compatibility

Keep API87.1 and submodule revisions. Echo's private icons remain disabled in the
export CSV. If a build proposes API changes, stop and inspect why: use app-local
code for a private feature, or explicitly scope a coordinated API/SDK migration.
Do not manually mark every proposed symbol `+` or silently accept a newer SDK.
Visible branding can change while internal IDs (`Momentum`, `marauder_studio`,
`bad_kb`) and saved paths remain for compatibility.
