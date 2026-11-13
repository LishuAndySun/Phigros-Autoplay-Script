# PhiAPS Audio Playback Start Signal Investigation

Scope: rounds `diags/1211202605` (round 1) and `diags/1211202606` (round 2). Read-only. No source, log, report, or config file was modified. No game or emulator action was taken.

## 1. Time basis

| Source | Clock | Conversion used |
|---|---|---|
| Round 1 `events.json` `receive_time` | UTC | Used as-is. No device timestamp exists in round 1. |
| Round 2 `events.json` `timestamp` | Device local time | Converted to UTC by subtracting 9 h. Verified: median `receive_time - timestamp` over 1489 live events = -9.0000 h. |
| Manual marks, round 2 (`experiment_data/sessions.json`) | UTC | Used as-is. |
| Manual marks, round 1 (`diags/1211202605/ANALYSIS_REPORT.md` section 5, from `report.txt`) | UTC | Used as-is. |

Round 2 replay caveat: the logcat backlog was received at about 13:08:24 UTC, so only device timestamps are valid for round 2 events.

Round 1 caveat: about 26,397 of 28,042 events have a `receive_time` inside the single minute 12:16. The round 1 receive times are therefore batched and cannot give sub-second or multi-second offsets to the marks. Only the order within a batch is meaningful.

## 2. Verified markers

Round 2 (device time = UTC + 9 h):

| Marker | UTC | Device |
|---|---|---|
| Map Load Start | 13:07:55.897 | 22:07:55.897 |
| Map Load End | 13:08:00.434 | 22:08:00.434 |
| Play Start 1 (PS1) | 13:08:03.522 | 22:08:03.522 |
| Map Load Start | 13:08:50.906 | 22:08:50.906 |
| Map Load End | 13:08:55.568 | 22:08:55.568 |
| Play Start 2 (PS2) | 13:08:58.817 | 22:08:58.817 |
| Play End | 13:11:03.873 | 22:11:03.873 |
| Score Screen | 13:11:06.267 | 22:11:06.267 |

Round 1 (UTC `receive_time`): Game Start 12:16:45.825, Map Load Start 12:17:07.682, Play Start 12:17:13.938, Pause 12:17:17.692, Resume 12:17:21.925, Play End 12:19:21.042, Score Screen 12:19:30.368.

## 3. Audio event discovery

Raw-log counts of audio tags (`raw_logs.txt`):

| Tag | Round 1 | Round 2 |
|---|---|---|
| AudioFlinger | 42 | 50 |
| AudioTrack | 37 | 44 |
| OpenSLES | 12 | 15 |
| AudioTrackShared | 12 | 16 |
| AudioSystem | 8 | 8 |
| APM_AudioPolicyManager | 7 | 8 |
| AudioPolicyService | 2 | 2 |

Audio lines in `events.json`: round 1 has 108 lines, all between 12:16:41.97 and 12:16:45.70 UTC. Round 2 has 130 lines. Of these, 17 are at or after 22:00 device time, and they fall into three clusters: 22:07:29.16–29.50, 22:10:10.79, and 22:10:58.23.

Distinct candidate events (message templates). The `onStateChanged: ... unfrozen` line from AudioFlinger was excluded because it is a freezer notification, not audio.

| ID | Event (message template) | Process | Subsystem | Interpretation |
|---|---|---|---|---|
| C01 | libOpenSLES "Emulating old channel mask behavior" | App (3307, 3730, 4063) | OpenSL ES | Track creation (init) |
| C02 | AudioFlinger "createTrack_l(): mismatch between requested flags ... and output flags" | 500 | AudioFlinger | Track creation (init) |
| C03 | AudioFlinger "Client defaulted notificationFrames to N for frameCount M" | 500 | AudioFlinger | Track creation (init) |
| C04 | AudioTrack "Use of stream types is deprecated..." (plus companion "See the documentation of AudioTrack()") | App | AudioTrack | Track creation (init) |
| C05 | AudioSystem "onNewService: media.audio_policy / media.audio_flinger service obtained" | App | AudioSystem | Process attaches to audio services (init) |
| C06 | AudioFlinger "mixer(...) throttle end: throttle time(N)" | 500 | AudioFlinger mixer | Output thread activity; occurs at creation too |
| C07 | AudioTrack "stop(N): called with X frames delivered" | App | AudioTrack | Track stop/teardown with frame count |
| C08 | AudioTrackShared "obtainBuffer: benign status 'Try again' (recheck)" with companion AudioTrackShared "releaseBuffer: dropped wake" | App (producer) and 500 (consumer) | AudioTrackShared | Active track being pulled by the mixer |
| C09 | AudioFlinger "prepareTracks_l BUFFER TIMEOUT: ... underrun" with AudioTrack "restartIfDisabled(66): ... restarting" | 500 and 3730 | AudioFlinger / AudioTrack | Underrun of a running track |
| C10 | APM_AudioPolicyManager "getNewOutputDevices io 13 recent device override {AUDIO_DEVICE_OUT_SPEAKER}" | 500 | Audio policy | Routing; no playback information |

Round coverage: C01 to C07 and C10 appear in both rounds. C08 appears in both rounds (round 1 at 12:16:41.97 and 12:16:42.53; round 2 at 20:46, 21:10 to 21:14, and 22:10:10 and 22:10:58). C09 appears only in round 2 (21:04:54, process 3730, no marker in that session).

## 4. Correlation with Play Start

Round 2, PS1 (22:08:03.522 device):
- C01, C02, C03, C04, C06 at 22:07:29.16 to 22:07:29.50, which is 34.0 to 34.4 s before PS1. These coincide with the `PlayerBase` construction of process 4063 at 22:07:29.
- C08 nearest occurrence after PS1: 22:10:10.786, which is +127.3 s.
- No audio line exists between 22:07:29.50 and 22:10:10.79.

Round 2, PS2 (22:08:58.817 device):
- No audio line exists in 22:08:40 to 22:09:30 (window count 0).
- Creation cluster at 22:07:29: -89.3 to -89.7 s.
- C08 at 22:10:10.786: +72.0 s. C08 at 22:10:58.229: +119.4 s.
- Play End (22:11:03.873): C08 at 22:10:58.229 is -5.6 s before Play End.

Round 2, Play End and Score Screen: no C07 stop event for process 4063 appears in the window. The last 4063 audio event is C08 at 22:10:58.

Round 1:
- The only audio lines are at 12:16:41.97 to 12:16:45.70 UTC. Game Start was 12:16:45.825, so the creation cluster for 4063 (12:16:45.41 to 45.70) sits 0.1 to 0.4 s before Game Start. Because of the receive-time batching, this offset is not reliable.
- The earlier statement in `ANALYSIS_REPORT.md` (about 28 s between 12:16:45 AudioTrack and Play Start) is not supported and should be considered superseded.
- No audio line exists after 12:16:45.70 in round 1. Map Load Start, Play Start, Pause, Resume, Play End, and Score Screen therefore show no audio evidence. The cause (no audio output, log filter, or truncation) is not determined.

Summary of correlation: track creation (C01 to C04) is reproducible at scene load and is not repeated at PS2. C08 is the only candidate that occurs during the playing interval of round 2, but it is not present at PS1 and first appears 72 s after PS2. This is correlation, not causation.

## 5. Candidate ranking

| Rank | Candidate | Classification | Basis |
|---|---|---|---|
| 1 | C08 AudioTrackShared obtainBuffer benign / releaseBuffer dropped wake | LOW POTENTIAL | Only candidate tied to a running track rather than creation. Not present at PS1. Appears 72 s after PS2. Not observed in round 1 after Play Start. |
| 2 | C09 Underrun and restart | INSUFFICIENT EVIDENCE | One occurrence in round 2 (21:04:54, process 3730) with no marker in that session. |
| 3 | C07 stop with frame count | NOT SUITABLE | Stop events occurred on track teardown. In round 2 and round 1, the short 6144-frame tracks stopped 0.2 s after creation, which is not music-length playback. The sample rate is not logged, so duration is not computed. |
| - | C01 to C04 track creation | NOT SUITABLE | Occur at scene load, 34 s before PS1, and not at PS2. Initialization, not playback. |
| - | C05 service attach | NOT SUITABLE | Process-level initialization. |
| - | C06 mixer throttle | NOT SUITABLE | Co-occurs with creation; not specific to playback. |
| - | C10 output device override | NOT SUITABLE | Routing; repeated throughout both rounds. |

No candidate is HIGH POTENTIAL. No candidate occurs at Play Start in both rounds with stable timing.

## 6. False-positive analysis

| Candidate | Emulator startup | Phigros open, no song | Song loading | Song change | Init without playback | Unrelated audio |
|---|---|---|---|---|---|---|
| C01 to C04 | Yes (round 1 3307 and 3730 creation at 12:16:42) | Yes (scene construction) | Yes (22:07:29) | Not tested: no second scene load in the same process for PS2 | Yes (creation without playback) | Possibly |
| C08 | Yes (round 1 12:16:41, before any mark) | Not checked | Not observed | Not tested | Possible; the obtainBuffer retry does not prove audible sound | Possible |
| C09 | Not observed | Not observed | Not observed | Not observed | Not observed | Possible |
| C07 | Yes (stop at teardown) | Yes | Yes | Not tested | Yes | Possible |

Items marked "Not checked" or "Not tested" require a new experiment. The current datasets cannot separate music from other audio in the same process, and no log shows whether the output is silent or audible.

## 7. Recommended experiment sequence

One candidate per experiment. Each run follows the same procedure:
1. Start the emulator and Phigros in a controlled state.
2. Start the same song using the same procedure (manual or PhiAPS).
3. Capture audible onset with a host-side loopback recording of the emulator audio output, time-aligned with the host clock.
4. Log the candidate with device time (`adb shell date`) and host time, and record the difference between the first candidate event and the audible onset.
5. Repeat at least 5 times.

Experiment 1 (first): C08, AudioTrackShared obtainBuffer benign retry as an active-track indicator.
- Positive: each song start.
- Negative control A: launch Phigros and stop before any song (no playback).
- Negative control B: open a song but mute the emulator (distinguishes event from audible output).
- Question answered: does the first C08 event occur within a fixed window of audible onset, and does it appear only during playback?

Experiment 2: C07 with frame counts, if C08 fails. Compare the frame count at stop with the duration of the audible onset.

Experiment 3: C01 creation timing, as a scene-load negative control. Expect it to precede audible onset by tens of seconds.

Do not implement these experiments yet. Ask before running any of them.

## 8. Questions not answerable from existing logs

1. The exact audible onset of music in either round. No audio output measurement exists.
2. Whether any candidate occurs at PS1 in round 2. None does.
3. Round 1 audio evidence after 12:16:45.70. None is recorded.
4. Whether the round 2 PS2 playback is audible (volume, mute, route).
5. Whether round 2 22:10:10 and 22:10:58 C08 events belong to the song or another audio stream.
6. First-note timing. Chart data was not examined in this investigation.
7. Whether PhiAPS sends an input at all in these sessions. The input dispatch evidence was not located in the round 2 window.

## 9. Conclusion

No reliable music-start signal exists in the current logs.

- The earliest, most reproducible audio events are initialization (track creation) at scene load, not music start.
- C08 is the best playback-state candidate, rated LOW POTENTIAL, and it is not aligned with Play Start 1.
- A new one-variable experiment is required before selecting a signal. The first candidate to test is C08.
