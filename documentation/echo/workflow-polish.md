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
| 1 | Stability: memory, browser cancellation, worker/radio cleanup | Browser fixes and sanitizer checks pass; device regression pending final core install; radio cleanup continues in stages 4–6 |
| 2 | RFID: search/decode feedback, write verification and specific failures | Implemented; host/build and device UI pass; physical tag tests pending |
| 3 | NFC: completeness, emulation limits, missing keys and original/modified data | Implemented; host/build and synthetic-file device UI pass; physical tests pending |
| 4 | Sub-GHz: operating status, duplicates, RAW/errors, Replay Bench lifecycle | Implemented; host/build/CI and limited device UI pass; physical tests pending |
| 5 | BLE: pairing/connection/HID readiness, interrupted pairing and disconnect cancellation | Implemented; host/build and device UI pass; paired-host tests pending |
| 6 | IR: press/hold/repeat, remote navigation, parsed/RAW identification | Pending |
| 7 | Files: selection restoration, long folders, naming/overwrite/corrupt-file feedback | Pending |
| 8 | Cross-app contextual actions and measured performance review | Pending |
| 9 | Full regression, install/hash checks, physical validation, passing fork PR | Pending |

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
