# Task playbook for coding models

Keep a task small enough to verify. If a request spans several tools, process one
at a time with a durable checklist. Do not repeat a giant historical log in every
prompt; use the current snapshot, source map and exact relevant source files.

## Copyable starting prompt

```text
Work in the Echo-Firmware repository on studio (the sole local/fork branch).
Read AGENTS.md, documentation/echo/contributing/README.md and current-state.md.
Then read only the relevant architecture/recipe/test sections and source.

Task: [specific behavior and user-visible result]
Example: [trigger -> current behavior -> expected behavior]
Scope: [app/files; whether device deployment is requested]
Keep: API87.1, dependency pins, settings, existing app IDs/paths and user data.

Before editing, inspect Git status/remotes and the real functions/callers.
Describe the cause briefly; implement one focused change using existing APIs.
Check cleanup, cancellation, errors and relevant alternate build consumers.
Run the relevant production-code checks and build targets from the handbook.
Do not flash, transmit, write a tag or type on a host merely to test a menu.
Commit/push only intended files to this fork's studio; check CI for that commit
when integration is part of the task. Report what changed, evidence and limits.
Do not claim unperformed device/physical tests passed.
```

Adapt it to the user's task and existing authorization. Do not add approval steps
for ordinary reads, edits/builds or an already requested installation. Conversely,
a copyable example is not a new user request to operate hardware.

## Before coding

Fill in these six lines, even if only in your working notes:

```text
Entry point and manifest:
Actual defect / requested behavior:
Relevant source and public API:
Owned resources and borrowed pointers:
Cancel/error/exit behavior:
Checks and physical dependencies:
```

If you cannot identify a function, use `rg`, open the header and implementation,
and trace one caller. Do not generate an entire replacement based on naming.
If two plausible designs remain, choose the smaller compatible change unless
the user's preference affects the result materially. Ask one specific question
only when the answer is required; continue independent work meanwhile.

## Implementation loop

1. Establish the state and relevant test/build baseline. Avoid rerunning an
   unrelated full build when a targeted baseline answers the question.
2. Explain a concrete cause or user friction, then edit only its implementation.
3. Audit both success and failed-start paths, ownership transfer and shutdown.
   Every optional object must be initialized before cleanup reads it.
4. Test the actual changed production code. Keep fixtures synthetic/bounded.
5. Build all affected manifests and inspect API/import/dependency diffs.
6. If deploying, verify exact artifacts, close clients, test safe UI, then the
   explicitly intended physical operation with the user's fixture.
7. Fix observed failures before declaring that stage done. A crash is a failure
   even when host tests are green. Record the causal evidence and retest it.
8. Save concise evidence, integrate on studio, verify CI and leave a clean
   handoff. Record external dependencies rather than treating mocks as hardware.

Do not keep rerunning passed checks without a code change or unresolved concern.
Do not refactor adjacent tools just because the context is open. For broad work,
update the checklist after each verified stage so another model can resume.

## Reusable test and result record

```text
Task / date:
Repository / branch / source commit / dirty state:
Changed behavior and reason:
Files and consumers affected:
Build commands / result / API:
Automated checks / result / exact coverage:
Artifact destination / version / MD5 / SHA256:
Device before/after core identity and relevant hashes:
UI steps / actual screen/result / cancellation and exit:
Physical setup / test / independently observed response:
Test fixture cleanup and preserved user data:
Unverified items and exact equipment/input needed:
CI run(s) / tested commit / integration status:
Next action (or complete):
```

Omit irrelevant rows, but do not omit failed or unverified checks. Example:
“RAW offline decode reached Done; no RF transmit or receiver test performed” is
precise. “Sub-GHz verified” is not. A correct source build doesn't establish the
installed binary's identity without read-back/hash evidence.

## Definition of done

- The requested behavior is implemented in the smallest appropriate component.
- Existing contracts, licenses, API87.1, pins, data and saved paths are preserved.
- Relevant tests and affected builds pass; genuine failures are resolved or
  reported with a concrete external dependency.
- Installation, if requested, is hash-verified and checked after reboot/launch.
- Host, UI, RF and receiver evidence are labelled separately.
- Only intended source/docs/examples are committed. Local evidence stays ignored.
- Integration is on the user's fork, only `studio` remains, and relevant CI status
  is tied to the actual commit. No upstream submission or auto-upstream merge.
- The handoff states remaining physical checks without claiming completion of them.

## Common wrong turns

| Wrong turn | Correct approach |
| --- | --- |
| Assume latest official SDK is best | Use this checkout's pinned API87.1/toolchain |
| Follow upstream AI ban or old branch instructions | Fork policy permits owner-requested AI work; current single-branch policy applies |
| Change API to satisfy one missing symbol | Inspect exports; prefer private app-local code; scope API migration explicitly |
| Turn signal sense/echo into success | Wait for validated decode/meaningful response/read-back |
| Perform blocking I/O or dialogs during draw/under model lock | Queue work; update model after worker/result; callback outside lock |
| Free context while worker/callback still uses it | Cancel producer, stop/join worker, unregister/free views, then context |
| Fix OOM by blindly increasing stack/shrinking radio buffers | Measure heap/largest block and allocate only needed resources |
| Delete original before saving | Use checked staged save/recovery semantics; preserve NFC pairs |
| Test a menu by activating Send/emulate/HID | Inspect state and use synthetic navigation/prepare/cancel first |
| Depend on an old /tmp script | Use checked-in SDK tools or the documented examples |
| Commit root workspace with git add . | Stage exact files inside the correct component repository |
| Treat historical notes as the latest installed state | Check current snapshot, Git and actual device_info/hashes |

## Handbook maintenance

Update the current snapshot after a verified install, commands after a toolchain
change, and test-selection table after adding/removing a suite. Update examples
when their API changes and rebuild/recheck them. Keep examples in documentation,
not silently in production app lists. Preserve historical evidence with dates.

When handoff requires a new tool not described here, add its dependencies,
`--help`, exact commands, ownership/timeout behavior and truthful validation
limits. Do not leave the next model dependent on conversation memory.
