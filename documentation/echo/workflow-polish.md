# Echo workflow improvement loop

Requested 2026-11-01. Scope: improve existing native Flipper tools without adding
apps or requiring the ESP32. API 87.1, user files, submodule pins and radio region
settings remain compatible.

## Loop

For each stage: inspect current behavior → identify a concrete defect or friction
→ implement a focused change → run production-code regression tests and affected
builds → check available device UI → record evidence → fix failures → continue.
Complete physical checks with the user's own tags, remotes and paired host.
Mocks, screen checks, transmission completion and receiver acceptance are separate
claims. Do not label an unperformed physical test as passed.

## Queue

| Stage | Scope | Status |
| --- | --- | --- |
| 1 | Stability: memory, browser cancellation, worker/radio cleanup | Implemented; host/CI and installed-core browser/startup checks pass; Sub-GHz OOM fixed and retested |
| 2 | RFID: search/decode feedback, write verification and specific failures | Implemented; host/CI, UI and synthetic save/readback pass; physical fixtures listed below |
| 3 | NFC: completeness, emulation limits, missing keys and original/modified data | Implemented; host/CI, status and synthetic original/shadow save/restore pass; physical fixtures listed below |
| 4 | Sub-GHz: operating status, duplicates, RAW/errors, Replay Bench lifecycle | Implemented; host/CI, RAW EOF/errors/cancel, RX start/stop and Bench prepare/cancel pass; receiver tests listed below |
| 5 | BLE: pairing/connection/HID readiness, interrupted pairing and disconnect cancellation | Implemented; host/CI and REM-only UI pass; paired-host checks listed below |
| 6 | IR: press/hold/repeat, remote navigation, parsed/RAW identification | Implemented; host/CI, navigation and synthetic save/reorder/readback pass; appliance checks listed below |
| 7 | Files: selection restoration, long folders, naming/overwrite/corrupt-file feedback | Implemented; fault-injection tests and installed browser/file checks pass; power-loss/SD hardware faults unverified |
| 8 | Cross-app contextual actions and measured performance review | Implemented; contextual review and IR/Sub-GHz memory measurements recorded |
| 9 | Full regression, install/hash checks, physical validation, passing fork PR | Core/apps installed and hash-verified; startup/exit regression and CI pass; physical dependencies documented; integration tracked in fork PR #6 |

## Baseline

- Fork `P1tt1cus/Echo-Firmware`, base studio `62362f54e`, working branch
  `feature/echo-workflow-polish`. Worktree clean before starting.
- Echo USB identified on 2026-11-01; installed core `13e6960e`, Echo 1.1/API87.1,
  AU provisioning. Replay Bench was running; no radio action was requested.
- Last Replay Bench installation verified UI and file handling, not RF output.
- Physical fixtures requested from the user; availability not yet known.

## Evidence and findings

Record actual changes, commands, results and outstanding physical checks here as
each stage progresses. Build artifacts/screenshots belong in ignored `build/`,
not in source. Never commit captures, credential data or pairing secrets.

### Stage 1: shared browser

- Fixed null destination/custom-icon copy and leaked replaced icons; self-copy is safe.
- Fixed the selected-name string leak on every sorted reload; preserve the first
  row's identity as well as later rows when sorting.
- Clamp selection to entries actually loaded if the directory shrinks or becomes
  empty, avoiding stale indices. Empty-list navigation no longer underflows.
- Worker observes stop requests between directory reads, including offset scans;
  stop takes priority over queued loads. Back during loading cancels the browser
  even inside nested directories; loading screen states this control.
- `python3 scripts/echo_browser_test.py`: PASS, production methods and m-array
  under ASAN/UBSAN, 200 reload cycles with zero retained strings/icons, selection,
  shrinking/empty directories, four cancellation phases, storage handle cleanup.
- Cancellation cannot interrupt an individual blocking SD operation; checks happen
  between operations. This is not a claim about an unresponsive SD driver's latency.
- Core build and on-device checks recorded below when complete.
- `firmware_all updater_minpackage SKIP_EXTERNAL=1`: PASS; API 87.1 unchanged.
  Existing shared-menu production regression suite: PASS. Changes committed as
  `61d8733a5`; core installation deferred to combined validated package.

### Stage 2: RFID

- Read screen distinguishes searching, sensed activity, and checking decoded data;
  shows auto ASK/PSK switching or the selected fixed mode, placement and Back hints.
- Auto-read re-entry explicitly resets its mode/status instead of showing the last
  scan's state. Signal/card-sense events never become a completed-read claim.
- Existing worker already verifies repeated decoded data and compares read-back
  protocol/data after writing. Success now states **Data verified / Read-back matches**,
  without claiming reader acceptance or password verification.
- Write retries distinguish differing read-back from a prolonged unverified write.
  Both normal and password-write scenes retain Back cancellation.
- `python3 scripts/echo_rfid_test.py`: PASS under ASAN/UBSAN, all 12 mode/status
  layouts, real scene transitions, no success from sense events, fixed-mode
  behavior, re-entry, worker stop/join calls. `fap_lfrfid`: PASS, API87.1.
- Physical tag read/write/reader-acceptance tests remain pending fixtures.
- RFID 1.1 source `e77943ea8` installed, local/device MD5
  `ab9430967cdcaa03cdabc30dd4694234`. Real screen captured showing Auto ASK,
  **Signal detected**, placement hint and Back control; Back returns to menu.
  This verifies UI and cancellation, not successful decoding/writing a tag.
  Previous FAP and screenshots retained in ignored `build/workflow-polish-install/`.

### Stage 3: NFC

- Centre **Status** on read results and Info opens capture completeness and emulation
  capability; **Details** or Back returns, preserving Retry/More on the result.
- MIFARE Classic reports sectors and keys separately; all sectors with a missing
  key stays partial. Ultralight distinguishes unread pages from all pages captured
  but incomplete authentication data. Other protocols do not inherit a false full
  card-copy claim from UID recognition or emulation support.
- Status identifies unsaved, saved and modified-shadow files. It does not infer
  reader acceptance. Existing live dictionary sector/key progress is retained.
- Ultralight no longer labels every incomplete read as password protection;
  feedback allows for retry/communication failures as well as authentication.
- `echo_nfc_status_test.py`: PASS, production render/event functions, ASAN/UBSAN,
  partial/full/UID/auth-incomplete data, capability flags, shadow status and 100
  Status/Details/Back cycles. `fap_nfc`: PASS, embedded protocol plugins/API87.1.
- Physical NFC reads/emulation and modified-card behavior remain pending fixtures.
- NFC 1.2 source `d874fd592` installed; local/device MD5
  `b814866c5ae99178419bf43958dbab11`. Synthetic ISO14443-3A file opened through
  Saved (direct file launch would start emulation). Info → Status → Back checked
  visually, including UID-only capability and identification-only data.
- Synthetic source MD5 `0ccae45f878f57f06f077e6ad2dc22eb` unchanged, fixture
  removed after closing NFC. No NFC emulation/transmission or card write performed.
  Screenshots and previous FAP retained locally; no private card data used.
- Info views reserve a footer for Status; embedded plugin builds included.

### Stage 4: Sub-GHz

- Duplicate detection now requires protocol, frequency, preset and identical
  serialized capture data. Hash collisions no longer suppress distinct signals,
  including in the 600 ms repeat filter and live remove-duplicates workflow.
  Timing/metadata differences intentionally retain distinct captures.
- Deduplication re-fetches shifted entries after deletion instead of using invalid
  pointers/iterators. Repeat counts saturate instead of wrapping. Comparison uses
  two 64-byte buffers and restores stream cursors; serialization failures are not
  entered as valid captures.
- RAW input posts events after releasing the model lock. Back cancels held-repeat
  and single-pass intent; queued repeats cannot restart after cancellation.
  Existing favorites explicitly request one pass. Completion is polled on the app
  tick instead of a worker callback that could block while the app joins the worker.
- RAW displays ready/recording/capture-ready and requested-versus-active TX status;
  existing frequency, preset, radio and sample-count feedback remains visible.
- TX errors distinguish invalid capture/preset, missing encoder, frequency/region
  restriction and radio start failure. Missing preset data is rejected before radio
  setup. Failed-start and stop paths clear freed transmitter pointers and tolerate
  a missing decoder; dynamic-save behavior remains intact.
- Replay Bench remembers its menu action and source selection, displays capture
  filenames, and records specific start failure causes. Its isolated memory footprint,
  bounded replay, cancellation and source-preserving working copies remain intact.
- `echo_subghz_history_test.py`: PASS (ASAN/UBSAN), forced hash collisions,
  protocol/frequency/preset distinctions, full-data comparison across chunks,
  cursor restoration, serialization failure, timing wrap/boundary, repeat saturation
  and repeated/adjacent removals using real m-array and production history functions.
- `echo_subghz_control_test.py`: PASS (ASAN/UBSAN), actual RAW input/stop helpers
  and TX-start/stop/completion functions with radio/decoder adapters. Checks unlocked
  callbacks, hold/release/Back/favorite intent, failure cleanup and error distinctions.
  Existing Replay Bench parser/control suites also pass, including new error text.
- Physical transmission, repeat timing and receiver response remain unverified.
  Existing native RAW file-worker malformed-file/progress behavior is queued for
  stage 7's corrupt-file handling review; it is not claimed fixed by these app changes.

- Native Sub-GHz 1.3 and Replay Bench 1.1 source `98b97d984` installed; local/device
  MD5 respectively `af560fa7e2c8ec9cdf04b395f612764a` and
  `959a4a18afd890013841882a6d239fd6`. API87.1 builds pass. CI firmware
  `41228281567` and lint `41228281562` passed.
- Device screens show RAW **Ready to record**, loaded synthetic capture filename,
  and Help → Back retaining Help selection. No transmit button was pressed.
- During grouped input checks, screens unexpectedly changed to Radio and then
  Sub-GHz. User confirmed no button interaction. Cause remains unresolved; fresh
  bench launch and one-button-at-a-time Help/Back checks passed. Do not count the
  interrupted preparation/cancellation check as passed. Repeat during final
  regression after core update; screenshots are retained for comparison.

### Stage 5: BLE/HID — in progress

- Disconnect now takes priority over simultaneous start/resume/connect flags.
  Coalesced reconnect returns to idle instead of continuing the interrupted run.
- Scheduled start listens for disconnect; interruption during the 1.5 second
  connection wait cancels the pending run. Cancel also wins over simultaneous
  connection. End during that wait exits directly. Start rechecks link presence.
- Worker exit releases keys/buttons before destroying the HID interface. BLE
  instance fields are explicitly zero-initialized before status callbacks start.
- `echo_hid_control_test.py`: PASS (ASAN/UBSAN), actual production worker with
  scripted event/radio/storage adapters: active, paused, button-wait and delayed
  string cancellation, disconnect/connect races, canceled/normal scheduled starts,
  normal completion, link-loss start guard and exit release. `fap_bad_kb`: PASS.
- This first cancellation patch is not installed. Remaining work: connection and
  pairing UI, long-command cancellation, status callback/pairing lifecycle review,
  physical paired-host test. No keystrokes were sent to a host.

- Follow-up: long STRING/ALTSTRING commands check pending stop/disconnect/exit
  between characters, leaving those flags for the worker; no automatic resume.
  HID state now distinguishes offline arming, linked readiness to start, lost link
  and reconnect requiring Run again. Elapsed seconds wrap correctly at 60.
- BLE uses the system pairing screen, including explicit numeric-code confirmation;
  prior PIN-screen suppression is restored on exit. Initial link status is sampled
  after registration and delivered when the worker attaches its callback.
- File-open failure cleanup only touches a successfully initialized HID interface.
  Zero-initialized worker storage makes this guard deterministic.
- `echo_hid_control_test.py` additionally passes long-command interruption and
  unreadable-file teardown. `echo_hid_view_test.py` passes all USB/BLE worker states,
  arming/lost-link/reconnect labels, clock rendering and 100 repeated draw cycles.
  `echo_hid_profile_test.py` passes actual profile init/teardown with adapters,
  status attachment, system PIN UI selection, key-store/default-profile restoration
  and saved PIN-screen preference. API87.1 `fap_bad_kb` build passes.
- A linked status means the stack's connection/pairing event was received. It does
  not prove that a host accepted HID reports. Physical pairing rejection, reconnect,
  HID receipt and held-key release remain separate device tests.

- Bad KB 1.1 source `571ee7b95` installed; local/device MD5
  `a1f9b4556c55e729c304caaa017ac12d`. A synthetic BLE_ID plus REM-only script
  displayed BLE **Pair host**, **Armed on connect**, and cancellation back to idle.
  Single-input screen checks passed. No keyboard or mouse command was present.
  Previous binary and screenshots retained in `build/workflow-polish-install/`.
- Physical host choice requested (this Mac, user's other host, or defer). No host
  was paired and no typing test was run in this pass.

### Stage 6: IR — audit started

- Current remote/learn-success screens ignore Back while transmitting and their
  exit handlers do not explicitly stop TX. Inspect shared button-menu held-input
  behavior and app teardown before choosing the cleanup change.
- Remote uses the vertical ButtonMenu; signal names are indexed, but parsed/RAW
  metadata is only loaded when sending. Avoid parsing every button on each draw.
- Existing `infrared_tx_start` rate-limits requests and `infrared_tx_stop` joins the
  worker. Preserve protocol-specific repeat handling; UI feedback must distinguish
  an actual started worker from a rate-limited request.

- Remote screen now uses a horizontal list with remote name/position, selected
  button, parsed protocol or RAW carrier/sample count, and Hold OK/Release/Back
  controls. Learn and Edit remain list actions. Up/Down wraps; Left/Right pages.
- Signal details load once per selection/re-entry, not on every redraw. The same
  validated in-memory signal is used for sending. Read failures show explicitly.
  Selection survives Edit/return, with bounds checks for empty/shrinking lists.
- Callbacks run outside the model lock. Held input freezes selection; Back cancels
  intent immediately, including during SD loading. The app rechecks intent after
  loading before TX. Short taps retain start/release sequencing; duplicate starts
  cannot replace a signal already used by the worker.
- Back stops active TX; a subsequent Back leaves. Remote and learn-result exits
  stop TX, and final app cleanup stops before freeing the worker/signal. Existing
  protocol repeat encoding and the 50 ms inter-send limit remain intact; a blocked
  fast repeat shows Wait, then press OK instead of claiming active TX.
- Learn results label RAW capture with carrier/sample count and Hold OK control.
- `echo_ir_view_test.py`: PASS (ASAN/UBSAN), production view, 0–99 signal lists,
  layout bounds, wrap/page navigation, restored selection, held/short/Back events,
  unlocked callbacks and stale metadata. `echo_ir_control_test.py`: PASS, actual
  scene and TX functions with SD/worker adapters, parsed/RAW setup, cached loads,
  short/held lifecycle, duplicate/rate-limited starts, cancellation during loading,
  invalid signals and remote/learn exit cleanup. Physical IR output remains pending.

- IR 1.2 source `a932fcc1e` installed; local/device MD5
  `05758786ed5f7aa3e892b8433d023cc0`. API87.1 build passes. Device synthetic remote
  shows Parsed NEC, RAW 38 kHz / 4 samples, and Cannot read signal for an unknown
  protocol. Edit → Back restores the Edit row. No send button was pressed and no
  appliance response was tested. Source fixtures/screenshots/previous binary are
  retained locally in `build/workflow-polish-install/`.

### Stage 7: files — audit started

- IR `infrared_signal_read_raw` accepts a zero timing count and returns success
  after a setter that returns early, potentially retaining an earlier parsed signal.
  Its setter silently clamps invalid carrier/duty data; NaN duty escapes comparisons.
  Validate file input before replacing a signal, and test unchanged prior data on
  rejected reads. Check zero/oversized timings and 32-bit protocol mask shifts.
- IR direct-file load error returns from `infrared_app` without releasing its
  allocated app. Normal exit resets TX output before the new final-free stop guard;
  stop before changing output as well. Test these teardown paths.
- Sub-GHz file worker starts before file validation. Open/header failures can reach
  the completion wait without publishing an end marker, leaving TX waiting. RAW
  data parser accepts malformed/empty records and turns extreme durations into
  arbitrary 100 us pulses. Progress subtracts binary buffered bytes from a text-file
  offset and can underflow/divide by zero. Fix with explicit validation and bounded
  progress semantics while preserving the existing public API.

- IR file fix: reject zero/oversized timing counts, invalid carrier/duty values
  (including NaN/infinity), missing data and zero pulses before replacing the
  current signal. A rejected read leaves prior data intact and returns an error.
  Valid file timings transfer ownership directly, avoiding the second allocation
  and copy. Public raw setter retains its clamping policy but preserves old data
  for invalid lengths and handles input aliasing safely. 32-bit protocol masks no
  longer shift by the width of the target integer.
- IR direct-file errors now use normal cleanup, and exit stops TX before resetting
  output/power. RPC context parsing uses the matching unsigned-long sscanf type.
- `echo_ir_file_test.py`: PASS (ASAN/UBSAN), malformed/empty/oversized/missing RAW,
  NaN/infinite duty, carrier/pulse validation, prior parsed/RAW preservation,
  0/8/32-bit masks, alias-safe setter and 100 ownership cycles. Measured allocation:
  an initially parsed signal loading 1024 RAW timings now allocates one 4096-byte
  buffer (previous read path allocated two buffers). This is host allocation
  instrumentation, not a measured device read-time improvement.
- `echo_ir_exit_test.py`: PASS, production app entry with resource/GUI adapters,
  100 missing-file/wrong-type cycles and normal/menu/RPC exits, verifying cleanup
  and stop-before-output-reset order. IR API87.1 build passes.
- Save audit also found RFID's save-name handler deletes an existing file before
  saving its replacement. Preserve the original on rename/write failure; review
  NFC/Sub-GHz and shared name validation before declaring stage 7 complete.

- Shared filename validator now rejects empty/dot/traversal/control/FAT-invalid
  names and ambiguous trailing dots/spaces before touching storage. Existing-name
  collisions and SD/stat errors have separate feedback; only Not Exist means the
  proposed name is available. Optional current-name storage is zero-initialized.
  `echo_filename_test.py`: PASS (ASAN/UBSAN), 100 cycles, UTF-8 names, collisions,
  six storage error states, current-name handling and balanced record ownership.
  Core/updater/API87.1 build and Echo asset/installer checks pass; core not installed.
- Device checks on IR file validation: valid parsed signal followed by empty RAW,
  zero carrier and NaN duty records each shows Cannot read signal. No TX ran.
  Wrong-format direct open exits after Back; free heap was 142184 before and
  142232 after this single cycle (not a stress/leak-proof measurement).
- Wrong-format file popup initially clipped the path and mislabeled unknown
  formats as libraries. It now uses compact format/version/read-error messages
  shared by direct-file and Saved workflows; entry tests cover all three causes.
- Before/after allocation benchmark compiled production code from `9cd9e5f95`
  and the new reader with the same instrumented allocator: a parsed → 1024-sample
  RAW read used 2 allocations / 8192 peak timing bytes before, and 1 / 4096 after.
  Evidence is retained in `build/workflow-polish-install/ir-allocation-benchmark.json`.

- Final IR 1.3 source `d47cc186c` installed, local/device MD5
  `1a3ef1b2f3451fe6011042226460b54f`. Corrected wrong-format dialog visually checked:
  Not an IR / remote file, without clipped paths. Back exits cleanly. Earlier
  empty/carrier/NaN device checks used the same parser from `cca28a1b8`.
- Shared filename changes are in the built core only; installed core remains
  `13e6960e`. Finish Sub-GHz RAW worker and safe save/rename review before installing
  the combined package. Keep physical RF/IR/HID checks separate from these UI tests.


### Stage 7 — RAW file worker and offline decoding

- RAW startup now validates the exact type/version/protocol and buffers the first
  valid record before returning success. Missing, empty, malformed and short-read
  files fail startup; callers release the worker even when no thread was started.
  Offline decode clears its freed pointer, reports File error, and does not wait
  for a radio device. App exit also releases a remaining decode worker.
- Buffered file reads bound each line to 6144 bytes and initial metadata through
  the first record to 16384 bytes. Each RAW record must contain 1–512 non-zero
  signed decimal durations with magnitude at most 1,000,000 microseconds. These
  bounds cover native recordings; unusual externally generated files outside
  these limits now reject rather than being truncated or converted to 100 us.
  Entire records validate before any of their pulses enter the queue.
- EOF and late read failures explicitly terminate the consumer instead of leaving
  it waiting indefinitely. A second queue read after observing producer completion
  preserves a last pulse published concurrently with an empty receive. Stop checks
  bound producer work between reads/queue retries; an individual SD call can still
  block. The legacy completion callback fires once and must remain nonblocking.
- Progress is labelled Read, with bounded file offsets and wide multiplication;
  it no longer subtracts binary queue bytes from text offsets or divides by zero.
  Decode distinguishes File error from Done. The existing API87.1 cannot convey a
  detailed late worker error to the TX scene: transmission terminates, but a late
  failure may still be presented as completion there. Startup validates only the
  first record, not the whole file before transmission. No RF test was run.
- Offline duplicate removal now shares live reception's exact capture identity
  rather than deleting different data that happens to share a protocol/hash.
- `echo_subghz_file_test.py`: PASS, production worker and encoder/decode functions
  under ASAN/UBSAN with memory storage and deterministic scheduling adapters.
  Covers corrupt/empty/oversized/NUL/short reads, missing files, queue cancellation,
  final-pulse scheduling edge, one callback, progress arithmetic, device reset,
  100 reuse cycles and 100 failed decode starts. This is not thread/DMA hardware
  validation. Added to firmware CI.
- Existing Sub-GHz history/control and Replay Bench parser/control suites pass.
  Core, firmware-only updater, Sub-GHz 1.4 and Replay Bench build for API87.1;
  Echo asset and installer package checks pass. These changes are not installed:
  device core remains `13e6960e`, native Sub-GHz remains installed 1.3. Deploy the
  new Sub-GHz FAP with the combined core update and verify synthetic offline decode.
- Prior head `868394fc9` CI passed: firmware `41230506419`, lint `41230506422`.
  Next: RFID original-preserving save/rename, NFC/Sub-GHz save audit, then combined
  installation, browser/performance/navigation regression and physical fixtures.


### Stage 7 — RFID save and rename protection

- RFID Rename now moves the existing file with collision rejection, preserving
  file contents/comments. An unchanged name checks that the file still exists.
  Filename/path state changes only after success; failed saves remain available
  for retry. Editing no longer deletes the original first, and a failed edit
  restores the original in-memory data while retaining edited bytes for retry.
- A private native-app staged-save helper creates an exclusive sibling temporary
  file, finishes writing it, then moves an existing destination to an unused
  recovery path before committing. Commit failure attempts rollback. If rollback
  fails, the original remains in `<card>.rfid.echo-old-N` and its suffix is shown.
  If cleanup fails after a successful commit, the retained original is reported.
  Existing temporary/recovery files are not overwritten; 32 slots bound lookup.
- This protects ordinary storage-operation failure, not filesystem power-loss
  atomicity. An interrupted commit can leave `.echo-new-N` / `.echo-old-N` siblings;
  preserve and inspect these through the file manager before manual recovery.
  No automatic startup recovery or removal of unknown retained files is attempted.
- The core RFID serializer now checks final close status instead of reporting a
  flush/close failure as success. Full behavior requires the combined core update;
  the staged-save/rename app changes themselves remain API87.1 compatible.
- `echo_file_save_test.py`: production helper, app helpers, name/edit event handlers
  and serializer pass ASAN/UBSAN. Fault injection covers all normal save steps,
  rollback failure, collision races, directories, slot exhaustion, retained-file
  protection, state/data rollback, retry and 100 ownership cycles. Added to CI.
  Existing RFID read/control tests and core/updater/RFID 1.2 builds pass. Physical
  SD failure/power-cut behavior is not established by these host adapters.
- Audit findings still to fix: NFC Save Name also deletes the original and shadow
  before saving; `nfc_save_file` ignores its path argument, and buffered close
  errors are ignored. Sub-GHz removes the destination before writing and ignores
  the byte count, then infers success from file existence; its rename overwrites
  collisions. Complete these paths before declaring the saved-file stage done.

- RFID 1.2 source `ceff67482` installed; local/device MD5
  `da1ea36e3588813cc168ccbeb6f442bd`. Prior 1.1 binary retained locally. Synthetic
  Saved → Rename changed `00_EchoSave.rfid` to `00_EchoSave_.rfid`; both file hashes
  were `2daaf20f57d5700c99c1f074bfbdd92e`, including the test comment. Browser kept
  the renamed file selected. Edit changed the first data byte from 00 to 10;
  readback was `10 EF 00 11 22`, MD5 `689c6543613a73d90f5f21238344b13c`. The normal
  serializer omits comments on data edits. No staging/recovery siblings remained.
  Back exited to the desktop, the fixture was removed, and loader is idle. No tag
  read, emulation or physical write was performed. Close-error handling still
  awaits the core update; on-device checks exercised normal SD operations only.
- Commit `ceff67482` CI passed: firmware `41231812616`, lint `41231812557`.
  Next implementation: NFC originals/shadows and truthful Sub-GHz save results.


### Stage 7 — NFC original and shadow protection

- NFC Save no longer deletes files before writing, honours its explicit target
  path, stages replacements and updates selection only on success. Updated data
  saved under the loaded card's name goes to its shadow; a new name creates a
  separate original and keeps the loaded pair. Failed saves keep the name input
  and previous filename/path for retry. New originals reject orphan-shadow names.
- Rename is identified by the Saved menu action, not merely a non-empty name.
  It preserves file bytes and the original/modified distinction. With a shadow,
  both exact copies are committed before either source is removed. Copy/read/
  write/sync/close/commit failure leaves the source pair available; failed copy
  cleanup or removal of old files is reported. A lone original uses safe rename.
  Both destination names are collision-checked, including orphan shadows.
- Pair rename uses extra disk space and is not a power-loss-atomic transaction.
  A power cut or cleanup failure may leave duplicate/staging files; source data
  is not intentionally removed until both new files are complete. Existing
  recovery artifacts remain protected by the bounded staged-save helper.
- Edit UID now writes a shadow, preserving Restore to Original State. A failed
  save restores the in-memory UID and leaves the edit available for retry.
  Shadow writes require an existing original. Selection stays on the `.nfc`
  path so browsers, loading and status consistently resolve the modified file.
- Core `nfc_device_save` now checks buffered flush/close before success and before
  ending its loading indication. This core fix is built, not installed yet.
- `echo_nfc_save_test.py`: PASS under ASAN/UBSAN, production app/helper/scene and
  serializer code. Covers every ordinary copy/sync/close/commit failure, rollback
  cleanup, collisions/orphans, unchanged/missing names, file-pair identity,
  canonical selection, named updates vs rename, UID rollback, retry and 100 cycles.
  Existing NFC status and staged-save/RFID suites pass. Core/updater/NFC 1.3 builds
  preserve API87.1. Physical NFC and SD power-loss behavior are not verified here.
- Next: install/check NFC synthetic pair workflows, then Sub-GHz save/rename
  accuracy and final shared-core/device regression. Prior `95b0cc7be` CI passed
  (firmware/lint runs `41232108931` and `41232108911`).

- NFC 1.3 source `bd022a3b2` installed, local/device MD5
  `ca1d9deb93fca34f021bd58915d70676`; previous 1.2 FAP retained locally. Synthetic
  pair rename `00_EchoPair` → `00_EchoPair_` preserved both exact file hashes:
  original `be5f138b66053158707da2e44603b97e`, shadow
  `a3f873174b35effe38efb1edfa236aa5`. Old names were absent; browser retained the
  new selection. Reopening loaded the shadow UID `05 06 07 08`.
- Device Edit UID changed it to `15 06 07 08`; shadow readback verified, MD5
  `7eab9305bd3abc9dd881c4e2788c97f3`, while original hash stayed unchanged.
  Restore to Original State removed the shadow, removed its Restore menu entry,
  and reloaded UID `01 02 03 04` in the edit view. Cancel/Back exited to desktop.
  No temporary/recovery siblings remained; all synthetic pair files were removed.
  No NFC read, emulation or physical card write occurred. The core buffered-close
  fix remains pending installation; these were normal SD/UI operations.
- `bd022a3b2` CI passed: firmware `41232718060`, lint `41232718061`.
  Next: Sub-GHz checked writes/overwrite/rename failure paths, remaining saved-file
  audit, combined core install and final navigation/performance/physical checks.


### Stage 7 — Sub-GHz save results, retry and rename

- Signal saves now check complete stream reads/writes, sync and close, then commit
  through the staged-save helper. New/manual/autosave files reject collisions;
  dynamic-protocol updates may replace only their specified destination while
  retaining/restoring the previous file on commit failure. Errors no longer infer
  success from a file merely existing. Transient Repeat removal uses a private
  serialized copy, preserving capture bytes/cursor. This adds temporary memory
  proportional to decoded serialized data; RAW recordings use file rename.
- Save Name builds its destination separately: failures keep the input/folder for
  retry instead of appending another filename. Rename rejects collisions, checks
  same-name existence, preserves bytes, and keeps the renamed file selected in
  the browser. Back restores the original path; empty input stays in the editor.
- Receiver autosave failures latch a flag instead of opening a dialog on the radio
  worker. A UI tick stops/joins reception, reports that the signal remains in
  history, then resumes reception. TX-stop releases the radio/speaker before a
  dynamic save callback can block on storage or failure feedback. RF/reconnect
  behavior under real storage failure still requires physical validation.
- Saving a decoded RAW signal now clears its released worker pointer. The new
  app-exit cleanup previously made this missed scene cleanup a double-free risk;
  the regression test covers duplicate save-success events and NULL teardown.
- `echo_subghz_save_test.py`: PASS ASAN/UBSAN, production save/rename/writer/scene
  code with storage adapters. Includes short and multi-chunk writes, read/sync/
  close errors, collisions, preserved captures/cursors, Repeat filtering, retries,
  selection, autosave dialog ordering, RAW cleanup and 100 ownership cycles.
  A separately compiled SUBGHZ_ADD_MANUALLY test covers its distinct save branch.
  Existing Sub-GHz control/history/RAW-file and Replay Bench suites pass; TX tests
  now require radio/speaker cleanup before the dynamic save callback.
- The standalone Add Manually app was omitted by SKIP_EXTERNAL=1. It is now an
  explicit Sub-GHz dependency, API87.1 build target and CI artifact. Deploy its
  1.1 FAP at `/ext/apps/assets/subghz_add_manually.fap` along with Sub-GHz 1.4.
  Core/updater, main app, Add Manually and Replay Bench builds pass.
- Remaining saved-file audit: IR batch edits stage a file but use an overwrite
  rename that deletes the original destination first; IR rename also treats
  FSE_EXIST as success. Fix these before the combined core/file regression.

- Sub-GHz 1.4 and Add Manually 1.1 source `f831a0365` installed; device/local
  MD5 `2c5a4e28d46117f8098a0d6f7ef7bb32` and
  `465c072e8f016d0320ba1250eb863249`. Both prior binaries retained locally.
  Synthetic unchanged-name save and rename `00_EchoSignal` → `00_EchoSignal_`
  returned to the selected file. Rename preserved MD5
  `935284ef0a51c279e26a8ee08a2474a7`, including its comment/Repeat field, and the
  old name was absent. Add Manually generated a GateTX file without transmitting;
  its 177-byte readback had the expected header/version/frequency/24-bit key and
  no transient Repeat field, MD5 `e0f391bc0c0d58b1eb31809091aed6e4`.
  Both synthetic files removed; loader idle/desktop verified. Core RAW-worker
  changes remain uninstalled, so these checks establish normal app file handling
  only. One-input-per-session navigation was stable throughout this pass.
- CI `f831a0365` passed firmware `41234101248` and lint `41234101251`.
  Next: IR create/append/batch edit/move/rename transactional save audit. IR move
  currently deletes then reinserts in separate commits; an insertion failure
  can therefore lose the moved signal. Preserve it in one staged replacement.

### Stage 7 — IR save/edit recovery

- Remote creation plus its first learned button now commits together, rejects
  collisions, and updates the current path/name list only on success. Append,
  insert, button rename/delete and move use checked staged replacements. A move
  writes its final ordering once instead of deleting and reinserting in two
  separate commits. Failed operations restore in-memory names and retain the
  original file; failed rollback reports the retained `.echo-old-N` suffix.
- Buffered write/flush/close errors prevent commit. Streams are freed before
  staging cleanup because buffered close can fail before closing its underlying
  file. Recovery notices run on the UI thread after joining the edit worker.
- Remote rename is byte-preserving, rejects collisions, checks unchanged-name
  existence and retains the new browser selection. Rename/learning save errors
  keep the entered name, selected button and learned signal available for retry.
- Edits/append reserialize the remote's valid signals one at a time, normalizing
  formatting and dropping comments as the earlier batch editor did. They need
  temporary SD space for a complete replacement and reject an unreadable signal
  rather than committing a partial remote. This is ordinary I/O-failure recovery,
  not power-loss atomicity.
- New `echo_ir_save_test.py` runs actual remote code and real name containers
  with storage/format adapters under ASAN/UBSAN: every normal failure step,
  original/name preservation and retry, all move permutations, failed rollback,
  create/collision/empty/unchanged-name/corrupt-source cases and 100 cycles.
  `echo_ir_save_scene_test.py` covers actual rename/create app helpers and scene
  event handlers, browser selection, retained input/selection, learned-signal
  retries and joined-worker recovery notices. Existing IR view/control/file/exit
  and shared staged-save suites pass; API87.1 core/updater/IR 1.4 builds pass.
  Device installation and synthetic edit checks are next.

- IR 1.4 source `f99bbb252` installed and hash-verified, MD5
  `0af2eaa3587ef14256d99cd2859e71eb`. Synthetic remote rename
  `00_EchoSave` → `00_EchoSave_` preserved exact MD5
  `566e93349264f56b6566c1705c4652e6` and removed the old name. The remote view
  showed the new name, and Back exited. Its reorder check exposed another
  pre-existing UI issue, fixed next before verifying staged button moves.

### Stage 8 — contextual control consistency

- IR reorder previously saved on Back while allowing the scene to exit, posted
  its worker callback under a model lock, and swapped endpoints on wrap even
  though the saved operation inserts at a new position. The view now uses
  insertion order throughout; OK picks/saves and Back cancels the preview first
  (a second Back exits). No-op moves do not start a worker. Save callbacks run
  outside the model lock; empty lists and reset callbacks are safe.
- Three bounded rows leave room for position and explicit Pick/Save/Cancel/Exit
  hints. Long labels stay within their row. `echo_ir_move_test.py` passes actual
  input/render code with real containers under ASAN/UBSAN: empty/long lists,
  both wrap boundaries, cancellation permutations, unlocked callbacks and 100
  cycles. Device reorder/save/cancel verification follows the rebuilt IR FAP.

- IR 1.5 source `6e1c0c272` installed, local/device MD5
  `62ec6cd07b19a3603f40eb33bffa39b3`. Reorder's first→last preview showed
  Volume_RAW_test, Third_test, Power_test. Back restored the original order
  and unchanged MD5 `566e93349264f56b6566c1705c4652e6`. Repeating the move
  and pressing OK saved that insertion order. The 312-byte USB readback matched
  every original parsed/RAW field; only ordering/serialization changed, MD5
  `9a096c7f0ba2328532e921431145453f`. Reopening showed that saved order and
  RAW 38 kHz / 4 samples. All synthetic remote/staging siblings removed; loader
  idle confirmed. No IR transmission or physical learned capture occurred.
- Startup observation: the first direct launch after installing 1.5, followed by
  Up before an initial screen capture, returned a completely blank RPC frame; a
  second snapshot was also blank. Loader still reported Infrared running, USB
  responded and Back exited normally. Two subsequent direct opens displayed
  correctly, and all one-input reorder/save/cancel checks passed. Root cause is
  unconfirmed; retain this alongside the earlier grouped-input navigation issue
  for final startup regression. This was not a confirmed frozen device.
- CI `f99bbb252` passed firmware `41234906082` / lint `41234905813`;
  CI `6e1c0c272` passed firmware `41235179188` / lint `41235179174`.
  Next: complete cross-app contextual/performance review, build/install the
  combined firmware-only core, then full navigation/browser/RAW regression and
  precisely document the remaining physical fixture/paired-host dependencies.

### Stage 8 — cross-app review and measured performance

- Reviewed shared menus/settings, native saved-item menus and live controls.
  Short OK selects menu actions; Back returns. Settings keep Left/Right values
  and locked-item explanations. Browsers cancel loading on Back and preserve
  selected files after rename. Live views keep their operation-specific controls
  explicit: IR/RAW hold/release, Replay Bench prepare/start/stop, BLE Arm/Cancel
  before linking and Run/Stop while linked. The IR reorder inconsistencies found
  in this review were fixed and device-verified above. Third-party custom views
  retain their own controls; no claim is made that they were rewritten.
- Production menu/dashboard, RFID/NFC status, Sub-GHz/Replay lifecycle, BLE HID
  control/view, IR control/reorder and browser suites all pass together (27 total
  suites including file/save/installer checks). Tests cover callback routing and
  cancellation as well as rendering. Device checks of the shared core are next.
- Measured improvement: instrumented actual IR RAW loading for 1024 timings went
  from two allocations / 8192 peak timing-buffer bytes at `9cd9e5f95` to one
  allocation / 4096 bytes. The current IR parser sanitizer test independently
  asserts the one-allocation bound. Artifact: `ir-allocation-benchmark.json`.
  This measures the timing buffers, not total app heap or wall-clock latency.
- Browser ownership tests retain zero strings/icons after 200 reload cycles;
  IR selected-signal caching avoids SD parsing during draw and reuses the same
  validated signal for send. New reliable saves intentionally use temporary SD
  space; Sub-GHz copies decoded serialized data and IR keeps a copy of names
  during commit. These are recovery tradeoffs, not claimed speed improvements.
- Combined core/app build and all 27 host suites pass at `ae48bb3f8`, API87.1.
  The device accepted a hash-verified firmware-only package at
  `/ext/update/Echo-workflow-ae48bb3f/update.fuf` and started its reboot/update.
  Package contains only firmware.dfu, updater.bin and update.fuf; radio stack,
  resource pack and apps are excluded. Before-state includes 15 file hashes
  (settings/name/current native apps/original companion/representative third-party
  app), installed source `13e6960e`, and AU provisioning. Completion/readback
  and final runtime regression are still pending at this entry.

### Final regression — installed core and Sub-GHz memory

- Core update completed: device_info reports clean `ae48bb3f`, Echo 1.1,
  API87.1 and AU. All 15 pre-update settings/name/app hashes are unchanged.
  Idle free heap was 143312 bytes; desktop and USB service work.
- Installed shared browser passed empty-directory navigation, a 230-file
  directory, last-page wrap and selected-file restoration after opening/back.
  One transitional RPC frame was blank; a fresh snapshot displayed correctly.
- Offline decoding a four-pulse synthetic RAW file then crashed with the device
  explicitly reporting "out of memory". This is a real runtime failure, not a
  passing parser test or an RPC-only issue. Before decode, browser free heap was
  16680 bytes (minimum 1800, largest block 8032).
- Sub-GHz's unused live RX worker retained a 16 KB pulse queue in browsing,
  offline decode and Replay Bench. Allocate it only for live RX, retain it across
  hopping, and release it on full stop. Start the worker before enabling its ISR
  producer and disable the ISR before joining/freeing. Pulse capacities remain
  unchanged. Sub-GHz 1.5 / Add Manually 1.2 / Replay Bench 1.2 contain this fix.
- New production-function sanitizer test covers 100 allocation/release cycles,
  500 retained-worker hops, producer ordering, no-op and TX-only stops. Runtime
  decode/cancellation verification of the new apps is pending.

### Final runtime result (2026-11-01)

- Sub-GHz 1.5, Add Manually 1.2 and Replay Bench 1.2 source `d3f612c2a`
  installed with matching local/device hashes. Firmware CI `41236679971` and
  lint `41236679984` pass, including all 28 registered host checks.
- The exact synthetic RAW decode that crashed now reaches Done; loader and USB
  remain responsive. Post-decode free heap is 30456 bytes, minimum 17896,
  largest block 18088. First-record and later-record zero-duration errors both
  show File error; Back returns through the menus and restores browser selection.
- A 51200-pulse synthetic file showed Read 020%; Back returned to the menu.
  After cancellation free heap was 43200 bytes. This verifies responsive offline
  cancellation, not RF playback or a precise cancellation-latency bound.
- Live internal-radio reception starts/stops three times with no decoded captures.
  Before RX: 43192 free bytes; during RX: 24216; after: 43232. After three cycles:
  43136, largest block 31640. This supports release of RX memory on full stop;
  it is not a long-duration leak benchmark or a successful protocol reception.
- Replay Bench loads the valid synthetic RAW, shows Prepared A, then Back cancels
  to the preserved Prepare selection. No Send action or RF transmission ran.
- Final startup/exit checks pass for RFID, NFC, Infrared, Bad KB's file browser,
  Sub-GHz/Add Manually/Replay Bench, Echo settings and existing Multi Converter.
  Loader returns idle; free heap after the ordinary app checks is approximately
  143 KB. The earlier blank IR startup did not recur in this pass; its original
  cause remains unconfirmed. This is representative compatibility, not testing
  every third-party app or every possible UI transition.
- All 234 synthetic regression files were hash-checked against local fixtures
  before removal, along with their three test directories. Prior synthetic
  RFID/NFC/IR files were removed in their respective stages. Existing user files,
  apps and settings remain in place. Local manifest records installed versions.

### Physical validation dependencies — not yet performed

No fixtures or paired-host choice were supplied in response to the earlier
questions. These checks remain distinct from the completed software/UI work:

| Area | Needed | Check and pass evidence |
| --- | --- | --- |
| RFID | Owned readable 125 kHz tag, disposable compatible writable T5577 and the user's reader | Repeat reads match protocol/data; write reports matching read-back; separate reader acceptance; cancel a retry without reporting success |
| NFC | Owned supported test card and corresponding reader; writable disposable card only for a chosen write test | Compare captured pages/sectors/keys with expected data; partial stays partial; original/shadow restore is correct; reader acceptance is recorded separately from emulation support |
| Sub-GHz | Owned permitted test transmitter/receiver and known static or RAW capture | Verify protocol reception and repeat counting; one requested bounded replay, stop behavior and independent receiver observation; no rolling-code acceptance inference |
| BLE HID | User-selected paired host and an open blank editor | Pair/link feedback, explicit Run typing only “Echo test”, disconnect mid-delay/long string releases keys and cancels; reconnect requires a new Run; cancel Arm without typing |
| IR | Owned remote and responding appliance, with known working codes | Compare short press with held repeat/release, Back cancellation, parsed/RAW learning and actual appliance response |

The earlier Kogan remote failures remain unresolved; no compatibility claim is
made by these changes. SD hardware removal/failure, power-loss recovery, sustained
RF/DMA timing and exhaustive third-party compatibility are also unverified.
Staged writes protect ordinary detected I/O failures but are not power-loss-atomic.
The existing API does not expose detailed late RAW TX worker errors to its TX UI.

Final integrity audit: all seven installed native FAP hashes match the local
manifest. Of 15 files recorded before the core update, only the three intended
Sub-GHz FAP replacements changed; settings/name/other app hashes match. Final
`device_info` reports clean `ae48bb3f`, Echo 1.1 and AU; loader is idle. Integration
and final CI status are recorded in [fork PR #6](https://github.com/P1tt1cus/Echo-Firmware/pull/6).
