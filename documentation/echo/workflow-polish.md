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
| 2 | RFID: search/decode feedback, write verification and specific failures | In progress |
| 3 | NFC: completeness, emulation limits, missing keys and original/modified data | Pending |
| 4 | Sub-GHz: operating status, duplicates, RAW/errors, Replay Bench lifecycle | Pending |
| 5 | BLE: pairing/connection/HID readiness, interrupted pairing and disconnect cancellation | Pending |
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
