# Create apps and scripts

All paths/commands below are relative to the Echo repository root. Run the
[toolchain setup](build-and-test.md#toolchain) first. The examples are teaching
sources under `documentation/`; they are not automatically installed or included
in normal firmware. Inspect the current API before extending them.

## Recipe 1: a native C FAP

Copy the complete starter into the app discovery directory:

```sh
cp -R documentation/echo/contributing/examples/echo_starter applications_user/echo_starter
./fbt -j4 fap_echo_starter
```

**Do not pass `SKIP_EXTERNAL=1` for this `applications_user` example.** That flag
excludes this discovery directory in this checkout. Native `applications/main`
FAPs in the full CI build are a different case.

Files:

- [application.fam](examples/echo_starter/application.fam) declares ID
  `echo_starter`, exported entry function `echo_starter_app`, GUI dependency,
  2 KB thread stack and Tools category.
- [echo_starter.c](examples/echo_starter/echo_starter.c) implements About/Exit,
  queued menu selection, Back from About to menu, and Back from menu to exit.
  It frees all views/records/context after the dispatcher stops. It performs no
  storage, RF or HID operation.

Output: `build/f7-firmware-C/.extapps/echo_starter.fap`. Check the build's actual
path if using a debug/different configuration. Verify APPCHK and absence of
missing imports. Deploy only if your task calls for it; use the
[device instructions](device-operations.md#install-one-fap).

For a real tool, rename the folder, `appid`, entry symbol, C types and visible
name consistently. App IDs are unique lowercase letters/digits/underscores;
build target is `fap_<appid>`. The ID, visible name and C entry symbol are separate.
Increment `fap_version` for a new shipped app version. Add a 10x10 monochrome
`fap_icon` only when you actually provide its file. Use `fap_icon_assets` for
private compiled icons; see [manifests](../../AppManifests.md).

Start with a standard Submenu to inherit Echo styling. For larger apps, study
`applications/examples/example_view_dispatcher/`, then the relevant native app's
SceneManager flow. Add one state/operation at a time:

1. Define the state and event enum, including cancel/error/completion.
2. Render state using existing GUI modules; keep all I/O out of draw.
3. Queue activation and handle it in the dispatcher/scene.
4. Add a bounded worker only if the operation needs it; specify ownership and
   stop/join paths before implementing start.
5. Add malformed-input/cancellation/error tests at the actual operation boundary.
6. Measure heap at idle/start/stop/exit before shipping.

For private Echo dashboards, read the exact configure API in
`applications/main/echo/echo_dashboard.h` and the
[contracts](architecture.md#gui-and-event-flow). Do not add exported firmware
functions for a private dashboard. For file persistence use a unique
`/ext/apps_data/<appid>/` path; preserve existing files on failed saves.

If this was only a tutorial build, remove the copied app after confirming it
still exactly matches the example; do not delete an existing contributor's app.
The documentation example remains the template. Do not commit both copies.

## Recipe 2: an on-device JavaScript script

Use [echo_hello.js](examples/scripts/echo_hello.js). This is Flipper **mJS**, not
Node.js or a browser. `print()` and `delay(milliseconds)` are engine built-ins.
Do not assume npm packages, filesystem APIs, promises, arrow functions or a
Node-style event loop work. Follow syntax used by the checked-in examples.

Copy to SD `/ext/apps/Scripts/echo_hello.js` using the storage command in the device
guide, then open **Tools -> Apps -> Scripts -> echo_hello.js** (or the equivalent
Archive path for your launcher configuration). CLI alternative:

```text
js /ext/apps/Scripts/echo_hello.js
```

CLI output appears on the USB console; UI launch displays the JS console. For
an interactive CLI script, Ctrl+C stops it. A host JS syntax check alone does not
prove mJS compatibility. Record a real engine run before calling it runtime-tested.
Installed JS Runner/module versions may differ from source; a missing module is
not evidence of an unsupported physical chip.

Find module names and signatures in the local TypeScript definitions:

```sh
rg --files applications/system/js_app/packages/fz-sdk
rg -n 'declare|export|function' applications/system/js_app/packages/fz-sdk/serial/index.d.ts
```

Then read the C implementation in `applications/system/js_app/modules/` when
semantics matter. The manually written `documentation/js/` can lag; local types,
production code and `examples/apps/Scripts/Examples/` are better evidence.
Examples include GUI, storage, serial, GPIO, IR and Sub-GHz. Some transmit or
change hardware state; copying an example is not a harmless default test.

A GUI script imports `event_loop`, then `gui`, then its `gui/<view>` modules.
Subscribe to view input/navigation and call `eventLoop.run()`; call `stop()` on
exit. Use the checked-in GUI example for callback arguments, dependency order
and extra callback state. Avoid long blocking loops in callbacks. Bound file reads
and serial waits, check module capabilities and close hardware handles on every
ordinary exit path. CLI cancellation is not a substitute for application cleanup.

## Recipe 3: a host Python diagnostic

[read_status.py](examples/host/read_status.py) is a complete read-only USB example:

```sh
python3 documentation/echo/contributing/examples/host/read_status.py --help
python3 documentation/echo/contributing/examples/host/read_status.py --command 'loader info'
python3 documentation/echo/contributing/examples/host/read_status.py --command free --seconds 5
```

It requires `pyserial`, discovers one macOS-style Flipper device or accepts an
explicit `--port`, and only allows `device_info`, `loader info` and `free`.
For Linux/Windows pass the enumerated port explicitly. It reads for a fixed
window through quiet intervals and closes the serial handle with a context
manager. It is not a binary transfer client or a general command-completion
parser. A reply containing an echo is not semantic success: inspect its body.

For a new host tool, follow this structure: argument parsing -> explicit input
validation -> one serial/storage client -> finite deadline -> validate result ->
close -> meaningful exit code. Use `time.monotonic()` for deadlines, subprocess
argument arrays (not shell interpolation), and binary-safe storage for files.
Do not log captures/keys by default or send automatic retries for mutations.

Use standard-library Python unless a dependency has a concrete purpose. Put a
maintained host tool in `scripts/` with `--help` and dependency/run instructions;
put pure conversion/parsing logic behind functions so it can be tested without
hardware. Python scripts execute on the host; copying one to SD does not make it
an on-device app. UART JS is a separate runtime and transport.

## Extending existing native tools

- RFID: trace scene -> view -> worker -> dictionary serialization. Signal sense
  must not become a completed read. Keep normal/password-write retry states.
- NFC: inspect protocol-specific plugin as well as generic scene. Preserve keys/
  sectors/pages completeness, original/shadow pairs and restore behavior.
- Sub-GHz: inspect shared helper consumers and core file worker. Allocate live RX
  worker on demand, stop ISR first, keep offline EOF/error/cancel distinct. The
  bench deliberately rejects decoded dynamic replay; do not silently mutate it.
- BLE HID: source folder `bad_usb`, app target `fap_bad_kb`. Disconnect wins over
  pending run; release keys and require explicit Run after reconnect. Test with
  REM-only data before a user-selected blank editor and harmless text.
- IR: distinguish parsed messages from RAW timing buffers. Validate once on load,
  cache selected metadata outside draw, preserve hold/release/Back and reorder
  insertion semantics. Check all create/append/edit/move save paths.

See the [test selection table](build-and-test.md#choose-checks-by-impact) before
changing any shared helper. Build every affected manifest, not just the app whose
screen initially exposed the issue.
