# Audio Playback Start Signal Audit

Read-only audit. No PhiAPS source, experiment record, session file, WAV file, or diagnostic data was modified. No experiment was run. The Android Studio emulator was not started, ADB was not used, the physical Pixel 8 was not connected, no package was installed, and the APK and Phigros native libraries were not inspected. AOSP main was not used as evidence.

## Inputs and hashes

Scratch libraries in `$TMPDIR/android17_libs/` were present and hashed this turn (SHA-256):

- `libwilhelm.so`: `9a630485f4e8e13e94103983f2e9eb0818fd71e5b47df515f8a2c42687b7266b` (matches the prior turn)
- `libOpenSLES.so`: `771ca94c10f7103d0f4e9a966f847d03c83327ac8db6ff2bc528cd36d899bdcc`
- `libaudioclient.so`: `0189039cd976a25deb1cfed6210932540f07b9719b53958b6671f04841f8bea1`
- `libaudiobase.so`: `633890a33aea6497264fd38a130030bb632b22975171b8b79ab7c9608d0b59fe`
- `libaudioflinger_datapath.so`: `6a1de1587f80f712a03c3dfc6077468e03781a925fcaf63886a79b1bdf703f87`
- `libaudioflinger_fastpath.so`, `libaudioflinger_timing.so`, `libaudioflinger_utils.so`: hashed, present (not analyzed further)

The requested report `Android17BuildIdentityAudit.md` does not exist in `Admissions/`. The closest file is `Admissions/android17_build_identity.md`, which was not used as a source for any finding here.

Output path `Admissions/AudioPlaybackStartSignalAudit.md` was confirmed absent before writing.

Existing reports consulted:

- `Admissions/AUDIO_START_SIGNAL_INVESTIGATION.md` (candidates C01 to C10, rounds 1 and 2)
- `Admissions/AUDIO_PLAYBACK_PIPELINE_AUDIT.md` (rounds 1, 2, and 3)
- `Admissions/C08_EVENT_DEEP_ANALYSIS.md`
- `Admissions/OpenSLESRealizeDispatchTrace.md` and `Admissions/OpenSLESDispatchAndRealizeCallerAudit.md` (prior binary work)
- `phigros_diagnostic/diags/AUDIO_START_SIGNAL_CANDIDATES.csv` and `phigros_diagnostic/diags/AUDIO_PLAYBACK_PIPELINE_CANDIDATES.csv`
- `experiment_data/sessions.json` (manual marks)
- `phigros_diagnostic/timeline.py` (marker labels)
- `audio_flinger.txt` and `audio_policy.txt` (dumpsys snapshots at the repo root)

## 1. Executive conclusion

No practical gameplay audio-start signal is established.

- No candidate is detected automatically by PhiAPS today. The existing markers `PREVIEW_PLAYING`, `START_TRIGGER`, `FIRST_AUDIO_PEAK`, `PREVIEW_STOPPED`, and `GAMEPLAY_AUDIO_STARTED` are label strings in `phigros_diagnostic/timeline.py` (lines 252 to 256). Their only occurrences in code are in that list and in `phigros_diagnostic/tests/test_experiment_records.py`. No code path emits them from audio data.
- `FIRST_AUDIO_PEAK` in session `session_20261114_211923` is a manual mark at 12:20:32.284 UTC. It is not a PCM measurement.
- The existing AudioFlinger and AudioTrack log lines show track creation, buffer operations, and frame counts. None of them is shown to correspond to audible sound at the speaker.
- The best existing candidate, C08 (`AudioTrackShared` `obtainBuffer` benign "Try again" plus `releaseBuffer` dropped wake), is not present at Play Start 1 in round 2 and first appears about 127 s after it.

Verdict: NO PRACTICAL SIGNAL ESTABLISHED.

## 2. Target event definition

The target is the first instant at which gameplay music (not preview, not a sound effect, not a system sound) is audible at the device output, measured on a clock that can be aligned with the PhiAPS session timeline.

The target is not any of the following:

- Object construction, `Realize`, `SetPlayState(PLAYING)`, or PlayerBase events. These are initialization or state changes (see the prior OpenSL ES reports).
- AudioTrack creation or the deprecation warning. These occur at scene load.
- Buffer submission (`obtainBuffer` or `releaseBuffer`). These show that the client is active, not that sound is produced.

## 3. Candidate observable signals

Each row is tied to existing evidence. "Observable by ordinary app" is classified only from what is verified in the repo, not from Android permission documentation (not checked here).

| ID | Candidate | Evidence source | Process | Notes |
|---|---|---|---|---|
| S1 | Actual PCM data available to a diagnostic app | Not present in any existing log | UNKNOWN | No existing record contains sample data. |
| S2 | AudioTrack submission of non-silent data | Frame counts only (C07 `stop(N)`, C-03 6144 frames) | App | Frame count shows submission, not non-silence. |
| S3 | AudioFlinger processing of the track stream | C08 buffer ops, C09 underrun, C06 mixer throttle | 500 (AudioFlinger) | C08 and C09 are buffer-level signals. |
| S4 | Playback-state transition (`PlayerBase` / `SetPlayState`) | Prior OpenSL ES reports; not a log line | App | Not confirmed to correlate with output. |
| S5 | `dumpsys audio` active-track snapshot | `audio_flinger.txt` line 125: "Tracks of which 0 are active" | Host-side ADB dump | Snapshot, not an event stream; requires ADB or device shell. |
| S6 | Track creation (C01 to C04) | Round 2 at 22:07:29 device time | App and 500 | Scene load; not playback. |

## 4. Candidate comparison

| Candidate | What it proves | Automatically observable by PhiAPS? | Required privilege | Timestamp quality | Main false-positive risk | Rank |
|---|---|---|---|---|---|---|
| S1 PCM availability | Audio samples exist | Not established | Unknown (likely system or instrumentation) | Unknown | Would include preview and silence | Not evaluable |
| S2 Frame submission (`stop` frame count) | Client delivered frames | Only from logcat (requires logcat access) | Log read | Stop-time only; no start time | Frames include silence; 6144-frame stops are too short for music | 3 |
| S3 C08 buffer retry | Track is being pulled by mixer | Only from logcat | Log read | Round 2 timestamps only; round 1 batched | Retry does not prove sound; not at PS1 | 2 |
| S4 `PlayerBase` / `SetPlayState` | Playback state changed | Not via public log in repo | UNKNOWN | Unknown | Known to precede or be unrelated to output (scene load) | 4 |
| S5 `dumpsys` active count | Track active at snapshot time | Only by polling | ADB or shell | Poll interval only | Preview and UI sounds can make a track active | 5 |
| S6 Track creation | Track object exists | Logcat | Log read | High, but wrong event | Occurs 34 s before PS1 | Rejected |

Ranking rationale: no candidate satisfies the acceptance criteria. S3 and S2 are ranked above S4 and S5 only because they are the only candidates that appear inside an active playback window in the existing logs, and they are not confirmed as audible.

## 5. Best candidate and justification

Best available candidate: S3, using C08 (`AudioTrackShared` buffer retry) as the first test candidate.

Justification:

- It is the only candidate with an event inside the round 2 playback interval (22:10:10.786 and 22:10:58.229 device time; 22:10:58.229 is 5.6 s before Play End).
- It is not present at PS1 (round 2) and does not appear in round 1 after 12:16:45.70 UTC.

Limits, which block it from being declared a practical signal:

- It does not coincide with PS1 or PS2 (see section 6).
- No log proves audible output at those times.
- Round 1 receive times are batched within one minute, so offsets cannot be measured there.

This is a candidate for validation only, not a signal.

## 6. Reassessment of existing evidence

| Question | Finding | Verdict |
|---|---|---|
| Which timestamps can serve as references? | Round 2 Play Start 1 at 13:08:03.522 UTC (22:08:03.522 device); Play Start 2 at 13:08:58.817 UTC; Play End at 13:11:03.873 UTC (from `AUDIO_START_SIGNAL_INVESTIGATION.md`) | VERIFIED (as cited in the prior report) |
| Can `START_TRIGGER` be distinguished from gameplay audio onset? | `START_TRIGGER` is a manual mark at 12:20:24.275 UTC in session `session_20261114_211923`, 8 s before `FIRST_AUDIO_PEAK` (12:20:32.284). It is not measured against audio. | VERIFIED that it is manual; UNKNOWN relation to audio onset |
| Can `FIRST_AUDIO_PEAK` be replaced by an automatic observation? | No automatic detector exists in the repo. The manual mark is the only evidence for this label. | UNKNOWN (no automatic source found) |
| Do logs contain evidence of the first gameplay audio data? | No. No sample data, no PCM peak, and no timestamped audio line is aligned to a verified gameplay onset in any round. Round 2 play window 22:08:03 to 22:08:58 has no audio-tagged line except C08 at 22:10:10 (outside). | VERIFIED (absence in the inspected logs) |
| Can preview playback produce false positives? | `PREVIEW_PLAYING` at 12:20:05.772 UTC precedes `START_TRIGGER` and `FIRST_AUDIO_PEAK` in session `session_20261114_211923`. Any audio event in that interval would be preview, not gameplay. The repo has no record separating preview from gameplay audio events. | SUPPORTED (ordering verified; per-event attribution UNKNOWN) |
| Do `PREVIEW_STOPPED` and `GAMEPLAY_AUDIO_STARTED` exist? | Absent in the examined session. Session `session_20261114_211923` marks are: Game Start, PREVIEW_PLAYING, START_TRIGGER, FIRST_AUDIO_PEAK, Play End, Score Screen. | VERIFIED |
| Is `audio_flinger.txt` a usable event source? | It is a single dumpsys snapshot (Start 11-14 11:50:21, Now 12:52:29). It shows "Tracks of which 0 are active" at line 125 and track tables. It is not a timestamped stream. | VERIFIED (format); not a playback-start source |

Other prior findings relied on:

- Round 2 PS1 has no audio event between 22:07:29.50 and 22:10:10.79 (`AUDIO_START_SIGNAL_INVESTIGATION.md`, section 4).
- C08 at 22:10:10.786 and 22:10:58.229 are paired with PID 500 `releaseBuffer dropped wake` at identical milliseconds (`AUDIO_PLAYBACK_PIPELINE_CANDIDATES.csv`).
- Round 3 (1311202603) has one client stop with 6144 frames at 13:13:31.630 UTC, about 2 s after process creation and before the Game Start mark at 13:13:33 (`AUDIO_PLAYBACK_PIPELINE_AUDIT.md`). Alignment is UNKNOWN.

## 7. Practical capture feasibility for PhiAPS

| Capability | Status |
|---|---|
| Automatic detection of gameplay audio in PhiAPS | Not implemented. No code emits any audio marker automatically. |
| Read AudioFlinger and AudioTrack log lines | Feasible in principle through the existing logcat path (`phigros_diagnostic/logcat_monitor.py` exists). Not verified for these tags in the repo. |
| Read PCM samples from the output | Not established. No existing component is shown to do this. |
| Read active-track state | Requires polling `dumpsys audio` over ADB or shell. Polling cannot give an onset timestamp. |
| Root or system instrumentation | Not required for logcat. Not determined for PCM capture or `dumpsys`. |
| Usable timestamp | Logcat lines have timestamps, but the round 1 receive times are batched. Device-clock alignment works only for round 2 (device time minus 9 h equals UTC, verified in the prior report). |

## 8. Known limitations and false-positive risks

- No audible-output measurement exists in any round. All "playback" claims are unverified.
- Round 1 receive times are batched in one minute, so offsets cannot be measured there.
- Round 2 replay caveat: logcat backlog was received at 13:08:24 UTC, so only device timestamps are valid.
- C08 buffer retries can come from any audio stream in the same process (for example preview, UI, or SFX). The process attribution is not sufficient.
- S2 frame counts include silence and cannot separate music from other audio.
- The round 3 6144-frame stop is attributed to a process created 2 s earlier; its relation to Game Start is UNKNOWN.
- The manual `FIRST_AUDIO_PEAK` marks are operator judgments, and their timing error is not measured.
- Sample rate is not logged, so frame counts cannot be converted to duration.

## 9. Minimum future validation experiment

This section is a proposal. It was not executed.

Required hardware and tools:

- Android Studio emulator: must be started for this experiment (the device under study is emulator-5554, Android 17). Not yet started in this audit.
- ADB: required, for logcat capture and `adb shell date` for device-clock alignment.
- Physical Pixel 8: not required.
- Host-side loopback or audio capture of the emulator output: required as the independent reference. This is not established in the repo and must be set up before the run.

Procedure (one candidate, one variable):

1. Start the emulator and Phigros in a controlled state. Record the device clock offset.
2. Start one gameplay song with a known chart. Record the manual Play Start from the operator (reference only).
3. Capture the host-side audio recording and the logcat stream with device timestamps for the same window.
4. Record the first C08 event (and, separately, the first S2 frame-submission event) and the audible onset from the host recording. Compute the difference.
5. Repeat for at least 5 starts. Include negative controls: launch Phigros with no song (C08 must not appear with audible output), and open the song with volume muted (events must still be logged; audible onset must be absent).
6. Include a preview-only run, to measure whether C08 fires for preview alone.

What PhiAPS must record: candidate event timestamp (device clock), host audio onset (host clock), and the device-to-host offset.

Success criteria:

- The candidate fires within a fixed window (for example under 200 ms, to be set before the run) of every audible gameplay onset across 5 or more starts.
- The candidate does not fire during preview-only or muted negative controls.
- Standard deviation of the offset is small enough to be useful for PhiAPS (to be set before the run).

Disqualifying results:

- Timing error or variance outside the pre-set window in any start.
- Any firing during preview-only or muted controls that cannot be separated from gameplay.
- No firing at gameplay onset.

## 10. Verdicts

- VERIFIED: No automatic PhiAPS detector for any audio-start marker exists in the repo (only label strings in `timeline.py` and tests).
- VERIFIED: `FIRST_AUDIO_PEAK` in session `session_20261114_211923` is a manual mark at 12:20:32.284 UTC.
- VERIFIED: `PREVIEW_STOPPED` and `GAMEPLAY_AUDIO_STARTED` are absent in that session.
- VERIFIED: No inspected log contains sample data, PCM peak data, or an audible-output measurement.
- VERIFIED: C08 is absent at round 2 Play Start 1 and first appears at 22:10:10.786 device time.
- VERIFIED: Track creation (C01 to C04) occurs about 34 s before round 2 Play Start 1 (prior report).
- SUPPORTED: C08 is the strongest in-playback candidate, but only as a buffer-level signal.
- SUPPORTED: Preview playback precedes the gameplay marks in the examined session, so preview audio is a false-positive risk.
- HYPOTHESIS: A logcat-based detector on C08 (or S2 frame submission) could be built and could align with audible onset. Requires the validation experiment.
- UNKNOWN: Whether any candidate corresponds to audible gameplay onset.
- UNKNOWN: Whether PhiAPS can read PCM samples or AudioFlinger state without ADB or elevated privileges.
- UNKNOWN: Round 1 timing of audio events (batched receive times).
- UNKNOWN: Round 3 alignment of the 6144-frame stop to Game Start.

## Final verdict

NO PRACTICAL SIGNAL ESTABLISHED

Missing evidence: a timestamped audio-output reference (host audio capture or PCM measurement) aligned to a verified gameplay onset, and an automatically observed event that fires at that onset and not during preview. C08 is the first candidate to test, but it does not currently meet the acceptance criteria.
