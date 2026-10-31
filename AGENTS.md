# Studio Flipper firmware maintenance

This is P1tt1cus's personal Momentum fork, maintained with the owner's explicit
request for AI-assisted development. These instructions apply to this fork.
The original project's contribution policy is preserved in
`documentation/UPSTREAM_AGENT_POLICY.md`; do not submit AI-authored work upstream.
Preserve all source licenses and attribution.

- `origin`: https://github.com/P1tt1cus/Momentum-Firmware
- `upstream`: https://github.com/Next-Flip/Momentum-Firmware
- Maintained/default branch: `studio`. Start feature branches here; target PRs here.
- Initial base: `d3f89dfe2ef6b01839201598e9be1590cba80322`, matching the installed
  Momentum build dated 2026-08-18. Target f7, API 87.1.
- Read the Studio section of ReadMe.md and `studio-target.json` before work.
- Paired companion: https://github.com/P1tt1cus/flipperzero-wifi-marauder
- Paired ESP32: https://github.com/P1tt1cus/ESP32Marauder (ZY-ESP32, LDDB).
- Preserve submodule pins. Do not silently advance dependencies or install a
  newer upstream firmware instead of building this fork.
- Follow the repository's fbt build instructions for relevant firmware changes.
  Build and test the companion against the resulting SDK when exported APIs change.
  Keep compile/test evidence separate from actual on-device validation.
- Review upstream changes on a separate integration branch. Never reset `studio`
  to upstream or automatically merge upstream releases.
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
