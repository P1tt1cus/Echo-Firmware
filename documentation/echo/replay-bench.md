# Sub-GHz Replay Bench

**Echo Replay Bench 1.1** is a separate app, launched from the **Sub-GHz 1.3**
dashboard, targeting f7/API 87.1. It uses the Flipper's internal CC1101; no ESP32 or external radio is needed.
Open **Tools → Sub-GHz → Replay Bench**, or **Apps → Sub-GHz → Echo Replay Bench**.
The dashboard closes before launching the bench to leave memory for file browsing
and RAW playback; Back returns to Sub-GHz when launched through that dashboard.

## Compare captures

1. Choose **Capture A**, then **Capture B**, from saved `.sub` files.
2. Open **Compare A / B**. Up/Down scrolls the report; Back returns.
3. Use **Save comparison** to export a text report without transmitting.

The menu shows selected capture filenames and restores the last action after
returning from a report or preparation. Each file picker reopens at its previous
selection. Start failures identify capture parameters, missing encoders or radio
rejection separately; these messages are not receiver-acceptance evidence.

The bench compares frequency, preset name, protocol and declared bit count. For
matching decoded protocols and bit widths with available keys, it shows the
number of changed significant bits and the XOR of stored key bytes. Keys are
right-aligned, big-endian; the bit count excludes unused leading padding.

It also compares every file byte, including formatting and metadata, and reports
the first differing byte offset. This is a positional byte comparison, not an
insertion-aware diff. RAW files show pulse counts and summed absolute timing;
they are not demodulated or aligned. Different preset names are highlighted;
custom preset contents are covered by the full-file byte comparison.

Changing bits alone does not establish encryption, a rolling counter or an
anti-replay mechanism. A non-cryptographic FNV-1a fingerprint identifies each
working copy in reports; it is not used to decide file equality or authenticity.

## Run a replay test

**Prepare A replay** loads the working copy and checks the current transmission
settings without starting RF. The next screen shows the protocol, frequency,
internal radio and run limits. Short **OK / Send** explicitly starts the run;
Back cancels preparation. Duplicate queued Send events do not start another run.

- **Decoded static protocols:** one encoder run with `Repeat=1` requested. A
  protocol may include multiple frames in that run; this is not a universal
  one-frame guarantee.
- **RAW recordings:** one pass through the recorded pulses. That recording may
  itself contain repeated messages.
- **Decoded dynamic protocols:** comparison only. Their encoders can advance
  counters or regenerate data, which would not replay the saved capture unchanged.

Back or the on-screen Stop action ends an active run. A dispatcher watchdog
stops runs that have not completed after 10 seconds (checked every 100 ms;
this is not a precise RF timing instrument). Existing frequency/region checks
remain in force. The bench does not change region configuration or bypass it.

The result reports **encoder completion**, a failed start, a user stop or a time
limit. It does not infer that the receiver accepted a command. Use **Observe**
to record **Unknown**, **Expected response**, **No visible change** or
**Unexpected response**. These are explicitly labelled manual observations.

## Files and reports

Sources are opened read-only. Analysis creates bounded working copies under
`/ext/subghz/echo_bench/` using unique `.tmp` filenames. Replay uses the working
copy, not a source that might have changed since selection. Choosing a new A
clears B. Normal exit removes working copies; interruption or power loss may
leave `.tmp` files that can be removed later while the app is closed.

Reports use unique `.txt` filenames in the same folder. A test report is written
before transmission begins and updated after completion/stopping and when an
observation is recorded. A power loss can leave the initial, explicitly
unconfirmed status. A report-creation/write failure prevents a new test from
starting; a later save failure is shown and can be retried using **Last test →
Save**. Leaving the app with an unsaved update may lose that update.

**Save comparison** exports the current A/B selection. **Last test** retains the
most recent test's frozen capture summary even if a different A/B pair is later
selected. Reports include saved keys and source filenames; treat them as capture
data. They are not uploaded automatically.

Limits: 256 KiB per input file, 512 bytes per metadata line and 8192 bytes per
RAW data line, decoded replay files at most
8 KiB, RAW replay duration at most 10 seconds, decoded key display up to 32
bytes. Unsupported or malformed files are rejected. Larger files may still be
usable in the original Sub-GHz workflows. The separate bench starts with the internal radio and does not save a new
radio preference. The bench does not overwrite original capture files or save
modified rolling-code data.

## Build and validation

```sh
FBT_NO_SYNC=1 ./fbt -j4 fap_subghz fap_echo_replay SKIP_EXTERNAL=1
python3 scripts/echo_replay_test.py
python3 scripts/echo_replay_control_test.py
python3 scripts/echo_dashboard_test.py
```

With both apps closed, install `subghz.fap` and `echo_replay.fap` from
`build/f7-firmware-C/.extapps/` into `/ext/apps/Sub-GHz/`. Both files are required
for the dashboard shortcut; Echo Replay Bench can also be opened directly.
The Sub-GHz manifest includes `echo_replay` as a dependency, even when other
external apps are skipped.
A core firmware flash is not required. Public API 87.1, original app ID and data paths remain.

The parser tests compile production code with address/undefined-behaviour
sanitizers. They cover fragmented reads, metadata, key bit differences, RAW
counts/timing, invalid numbers, duplicate fields, missing fields, size bounds
and a deterministic malformed-input corpus. Control tests compile production
prepare/send/finish/event code with mocked radio/storage to check no TX during
preparation, duplicate events, cancellation, deadlines, clock wrap, save/start
failures and manual observations. They do not verify RF output or receiver
behaviour. Hardware verification must be recorded separately.
