# Echo firmware maintenance

This is Echo Firmware, a personal Momentum fork, maintained with the owner's explicit
request for AI-assisted development. These instructions apply to this fork.
The original project's contribution policy is preserved in
`documentation/UPSTREAM_AGENT_POLICY.md`; do not submit AI-authored work upstream.
Preserve all source licenses and attribution.

- `origin`: https://github.com/P1tt1cus/Echo-Firmware
- `upstream`: https://github.com/Next-Flip/Momentum-Firmware
- Maintained/default branch: `studio`, the sole local/fork branch by owner request.
  Work directly on it in focused commits, push to this fork, and verify CI. Do not
  create feature/integration branches automatically; older PR workflows are historical.
- Initial base: `d3f89dfe2ef6b01839201598e9be1590cba80322`, matching the installed
  Momentum build dated 2026-08-18. Target f7, API 87.1.
- Read ReadMe.md and `studio-target.json` before work. Then use the
  [contributor handbook](documentation/echo/contributing/README.md), including
  current-state.md and task-playbook.md, before implementation. It contains exact
  build/test/deployment recipes and complete C/JS/host-Python examples.
- Paired companion: https://github.com/P1tt1cus/flipperzero-wifi-marauder
- Paired ESP32: https://github.com/P1tt1cus/ESP32Marauder (ZY-ESP32, LDDB).
- Preserve submodule pins. Do not silently advance dependencies or install a
  newer upstream firmware instead of building this fork.
- Follow the repository's fbt build instructions for relevant firmware changes.
  Build and test the companion against the resulting SDK when exported APIs change.
  Keep compile/test evidence separate from actual on-device validation.
- Review fetched upstream commits/diffs without adding a persistent branch. Never
  reset `studio` to upstream or automatically merge upstream releases.
- Never commit private captures, keys, Wi-Fi credentials, device backups, or caches.
- Initial fork setup changes no firmware behavior and flashes nothing. Preserve
  device storage and the installed recovery baseline during subsequent upgrades.

## Echo identity

Read `documentation/echo/README.md` for the Echo launcher and deployment. Preserve
API 87.1; the five new Echo icons are intentionally disabled in the export CSV.
Build `updater_minpackage SKIP_EXTERNAL=1` for firmware-only installs, and upload
the Echo asset pack and Echo Radio FAP separately. Do not use a resources bundle
that removes existing external apps. Run `scripts/echo_validate.py` alongside
the build and check launcher navigation on-device. Renaming the device changes
the USB serial-port name; re-enumerate before connecting.

App dashboards are external FAP updates; see the Echo guide. Run
`scripts/echo_dashboard_test.py` and build the three affected FAPs. Keep
`applications/main/echo/echo_dashboard.h` identical to the companion copy.

Shared GUI menus are styled in `applications/services/gui/modules/echo_menu.h`,
Submenu/VariableItemList and the Compact Menu renderer. Run
`scripts/echo_shared_menu_test.py` with existing Echo checks. Changes require a
firmware-only update; retain API 87.1, existing FAPs and SD resources. Preserve
standard/extended callbacks, settings values, locks and app-specific input.

Echo installer UI uses `applications/system/updater/views/echo_install.h`. Keep
error diagnostics and retry/exit controls intact. Run
`scripts/echo_installer_test.py --package-check` after building. The Echo guide
records the version sources, quoted manifest label and preview limitations.

Replay Bench 1.2 is a separate FAP opened from the Sub-GHz 1.5 dashboard. Read
`documentation/echo/replay-bench.md`. Run the parser and control sanitizer tests
(`echo_replay_test.py`, `echo_replay_control_test.py`) and build `fap_subghz fap_echo_replay`.
Install both apps; keep the bench separate to preserve heap for browsing and TX.
Never use real captures or run RF transmissions just to exercise its UI.
