# Contributing to Echo

This handbook is for a contributor or coding model starting without the chat
history. Read it in order. Use the checked-in code as the API reference; do not
invent function names, device capabilities or installation results.

## First five minutes

1. Read the repository [agent instructions](../../../AGENTS.md),
   [current state](current-state.md) and [task playbook](task-playbook.md).
2. Run `git status --short`, `git branch --show-current`, `git remote -v`,
   and `git log -5 --oneline` **inside this firmware repository**.
3. Check that the working branch is `studio` and origin is
   `https://github.com/P1tt1cus/Echo-Firmware.git`. Preserve existing changes.
4. Choose the smallest appropriate implementation from the table below.
5. Follow [build/test](build-and-test.md), then the optional, separately verified
   [device workflow](device-operations.md). Record facts with the evidence template.

The owner wants **one branch, `studio`, locally and on this fork**. Work directly
on it, use focused commits, and let its push CI validate changes. Do not create
feature/integration branches automatically. Review upstream with fetched commits
or diffs; do not replace Echo with upstream. This supersedes historical branching
instructions in old workspace notes. This policy concerns Echo-Firmware; other
component repositories have their own instructions.

## Choose the right kind of contribution

| Need | Implement here | Needs MCU firmware update? |
| --- | --- | --- |
| A standalone tool with GUI/workers | C FAP in `applications_user/<unique_id>/` | Normally no; build against this API87.1 checkout |
| A small on-device automation | `.js` under SD `/ext/apps/Scripts/` | No, if installed JS Runner/modules supply the API |
| Mac/Linux file conversion, diagnostics or test automation | Python under `scripts/`, or a separate host tool | No; host Python does not run on Flipper |
| Fix an existing native app | `applications/main/<app>/` and its manifest | FAP install; core too if shared `lib/`/services change |
| Shared GUI, firmware services, exported library implementation | `applications/services/`, `lib/`, `targets/` | Yes; rebuild affected FAPs when they embed changed code |
| Echo Radio/ESP32 functionality | Separate sibling repositories | Read their own guides; not part of native-only work |
| Vox integration | Define the interface first | Proposal only; do not claim integration exists |

## Handbook map

- [Current state and boundaries](current-state.md): installed versus source state,
  versions, evidence, physical-test gaps and the companion boundary.
- [Architecture and contracts](architecture.md): where to edit, ownership, GUI
  threading, workers, storage, memory, radio cleanup and compatibility.
- [Create apps and scripts](apps-and-scripts.md): complete C starter, mJS starter,
  host diagnostics, extension recipes and local API lookup.
- [Build and test](build-and-test.md): local toolchain, targets, dependency-based
  test selection, full CI checks, formatting and Git workflow.
- [Device operations](device-operations.md): ports, binary-safe transfer, hashes,
  FAP/core deployment, recovery, evidence and common failures.
- [Task playbook](task-playbook.md): copyable model prompt, task/result templates,
  definition of done and ways to stay within a small context window.

## Ground rules

- f7 / **API87.1**, toolchain 39, existing user data and pinned submodules are
  compatibility requirements. A new upstream SDK is not a substitute.
- Echo permits owner-requested AI-assisted work. The original upstream policy is
  archived in [UPSTREAM_AGENT_POLICY.md](../../UPSTREAM_AGENT_POLICY.md); do not
  submit this fork's AI-authored changes upstream under that policy.
- Build, host tests, device UI, RF output and target acceptance are separate facts.
  State exactly which one was checked.
- Never commit private captures, tag keys, pairing material, credentials, device
  dumps or build caches. Use synthetic examples and ignored `build/` evidence.
- This handbook documents deployment; reading it does not request a flash,
  pairing, HID input, card write or RF transmission. Apply the actual user task.
- No `/tmp` helper is a prerequisite. Commands use checked-in sources or explicitly
  identified local toolchain paths. Historical temporary upload helpers are unsafe
  for replacement FAPs; use `scripts/storage.py`.

## Validation of these examples (2026-11-01)

- The C starter was copied into `applications_user/echo_starter`, built with
  toolchain 39 and passed API87.1 SDKCHK/APPCHK. The byte-identical temporary copy
  was then removed. It was not installed; GUI runtime behavior is not claimed.
- Host Python `--help`, invalid-deadline and command-allowlist rejection checks
  pass. An actual read-only `loader info` query received a valid device response;
  it did not launch/close an app or change hardware state.
- The finite mJS starter follows the checked-in engine's print/delay/loop examples.
  It was not uploaded/executed; on-device runtime validation remains unperformed.
- Relative documentation links, changed example formatting and full repository
  lint pass. No firmware or FAP installation occurred for this handbook task.
