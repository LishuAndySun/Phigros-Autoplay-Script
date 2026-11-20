# Round 3 Audio Control Analysis (C08 Negative Control)

Dataset: `phigros_diagnostic/diags/1311202602`
Session: `session_20261113_130428` (description "13112602")
Candidate under test: C08, `AudioTrackShared: obtainBuffer benign status 'Try again' (recheck)`.

All device timestamps are logcat local time (UTC+9, the same convention verified for Round 2). UTC equivalents are given in brackets where needed.

## 1. Dataset integrity and time coverage

| Item | Value | Source |
|---|---|---|
| Session ID | session_20261113_130428 | [report.txt](diags/1311202602/report.txt) |
| Device | emulator-5554 | run configuration |
| PID filter | None (whole-device capture) | report.txt, raw_logs header |
| Logcat tag filter | None found in capture code (`_build_command` in [logcat_monitor.py](logcat_monitor.py) adds only `-s`, `--pid` if set, and `-v threadtime`) | logcat_monitor.py |
| Log time span | 11:43:03.430 to 13:05:59.173 (UTC+9); 02:43:03 to 04:05:59 UTC | raw_logs.txt |
| Total events | 90,049 (raw_logs.txt has 90,059 lines) | report.txt |
| Manual marks | 4 (see section 3) | report.txt, experiment_data/sessions.json |
| Format | threadtime (PID, TID, priority, tag present) | raw_logs.txt |

Coverage caveats:

- The capture has no dropped-line counter, so logcat buffer loss cannot be excluded from the logs alone.
- The Phigros process (PID 3158) produces no log lines after 13:05:00.461, about 19 s before the first "Song Select" mark. Device-wide logging continues to 13:05:59, so the capture was alive but the game was silent after 13:05:00.

## 2. Phigros process timeline (observed)

| Time (UTC+9) | PID | Event | Source |
|---|---|---|---|
| 11:43:13 (approx.) | 2289 | Earliest PID 2289 activity in the session (start time not re-verified in this pass) | raw_logs.txt |
| 13:03:27.495 to 13:03:27.504 | 2289 | AudioTrack stop(18) to stop(21) calls (C07 family) | raw_logs.txt |
| 13:04:09.079 to 13:04:09.123 | 2289 | PlayerBase constructions and `createTrack_l` mismatches (C01 to C04 family) | raw_logs.txt |
| 13:04:12.044 | 2289 | "Sending signal. PID: 2289 SIG: 9", process exited (Killed) | raw_logs.txt |
| 13:04:45.095 | 3158 | Phigros process re-created ("Process 3158 created for com.PigeonGames.Phigros") | raw_logs.txt |
| 13:04:45.415 to 13:04:45.741 | 3158 | AudioSystem service attach; createTrack_l; AudioTrack stop(26) with 6,144 frames at 13:04:45.618; track creations for libOpenSLES | raw_logs.txt |
| 13:04:46.840 | 3158 | Unity "Target frame rate: 60fps" | raw_logs.txt |
| 13:04:59.839 to 13:05:00.458 | 3158 | Unity initialization, TapSDK init, server time sync | raw_logs.txt |
| 13:05:00.461 | 3158 | Last Phigros-process log line in the capture | raw_logs.txt |

Observation: the Phigros process was killed at 13:04:12 and relaunched at 13:04:45, between the sessions. The first "Game Start" mark (13:04:46.314) falls during the relaunch, not during an established song-selection screen.

## 3. Manual UI actions (session marks)

| Mark ID | Type | UTC timestamp | Device time (UTC+9) | Phigros log state at mark time |
|---|---|---|---|---|
| manual_1 | Game Start | 04:04:46.314065 | 13:04:46.314 | PID 3158 was 1.2 s old; Unity still initializing |
| manual_2 | Game Start | 04:04:46.476377 | 13:04:46.476 | Same as manual_1 |
| manual_3 | Song Select | 04:05:19.842721 | 13:05:19.843 | No Phigros log lines after 13:05:00.461 |
| manual_4 | Song Select | 04:05:24.548033 | 13:05:24.548 | No Phigros log lines after 13:05:00.461 |

The session file records no difficulty selections, waits, or screen-transition marks. The "several difficulties" selections described in the request are not present as marks, so they cannot be correlated with any log event.

## 4. C08 occurrences in Round 3

- `AudioTrackShared` lines in raw_logs.txt: 0
- `obtainBuffer` lines: 0
- `benign status 'Try again' (recheck)` lines: 0
- `releaseBuffer` / "dropped wake" lines: 0
- `AudioTrackShared` in events.json: 0

C08 count in Round 3: 0.

Because the Phigros process logged nothing after 13:05:00.461, C08 absence covers the full game lifetime in this capture only. It does not cover the period in which the Song Select marks were recorded.

## 5. Other audio candidates in Round 3

| Candidate | Round 3 observation | Notes |
|---|---|---|
| C01/C02/C03/C04 (track creation, deprecation warnings) | Present at 13:04:09 (PID 2289) and 13:04:45 (PID 3158); libOpenSLES "Emulating old channel mask" lines at 13:04:45.731 to 13:04:45.740 | Occur at process start, consistent with the Round 1 and 2 pattern |
| C07 (AudioTrack stop with frame count) | Present: stop(18) to stop(21) on PID 2289 at 13:03:27; stop(26) on PID 3158 at 13:04:45.618 (6,144 frames) | Frame counts for the PID 2289 stops were not re-verified in this pass |
| C10 (APM output override) | Present around the 13:03:27, 13:04:12, and 13:04:45 process transitions (exact times not re-verified in this pass) | Routing updates coincide with process start/stop |
| C09 (underrun, buffer timeout) | Not observed | No `BUFFER TIMEOUT` lines found in this capture |
| C05 (AudioSystem service obtained) | Present at 13:04:45.415 to 13:04:45.417 (PID 3158) | Process-start pattern |

Audio tag counts in raw_logs.txt for Round 3: `AudioTrack:` lines 23, `AudioTrackShared` lines 0.

## 6. Comparison with previous rounds

| Dataset | Role | AudioTrackShared lines | obtainBuffer lines | Phigros process observed | Notes |
|---|---|---|---|---|---|
| 1311202601 | Round 1 | 0 | 0 | Not verified in this pass | Round 1 AudioTrack-pattern count: 16 |
| 1211202606 | Round 2 | 16 | 8 | Yes (PIDs 3307, 3730, 4063 in C08 lines) | C08 lines between 20:46:01 and 22:10:58 device time; screen state at those times not verified |
| 1211202605 | Other capture, not a designated round | 12 | 6 | Not verified in this pass | Listed only for completeness |
| 1311202602 | Round 3 (this control) | 0 | 0 | Yes (PID 3158, 13:04:45 to 13:05:00) | Control, intended as song-select with no gameplay |

Round 2 C08 lines (device time, UTC+9): 20:46:01.818 (3307), 21:10:22.736, 21:12:30.395, 21:12:42.159, 21:13:05.551, 21:14:19.445 (3730), 22:10:10.786, 22:10:58.229 (4063).

## 7. Correlation with UI actions

No C08 events exist in Round 3, so no correlation can be drawn. The Song Select marks (13:05:19 and 13:05:24) fall after the last Phigros log line, so even a C08 event in the UI state would be unrecorded. The Game Start marks coincide with process creation and Unity initialization.

## 8. Can C08 be ruled out as a gameplay-specific signal?

Partial. Observed facts:

- C08 is absent from the entire Round 3 capture (11:43:03 to 13:05:59), which includes PID 2289 (active until it was killed at 13:04:12) and PID 3158 (logging from 13:04:45 to 13:05:00). No `AudioTrackShared` lines appear for any PID.
- The Round 3 capture is not verified to contain no gameplay (see section 9). Round 2 C08 events occur in several time windows across PIDs 3307, 3730, and 4063; whether each window was gameplay was not verified in this pass, so Round 2 cannot yet be used to confirm a gameplay-only pattern.

Limitations that prevent a firm ruling-out:

- PID 2289 was active for most of the capture, but its screen state was not logged, so it is unknown whether it was on song selection or another screen.
- Phigros logs stop at 13:05:00, before the Song Select marks, so no song-selection period with logging active was recorded in the 3158 process.
- No gameplay-relevant artifact is present in this dataset, so absence here does not establish that C08 needs gameplay.
- Logging coverage cannot be verified (no drop counter).

Conclusion: C08 is absent in this control, but this control does not confirm the requested no-song, song-selection condition, so it cannot rule C08 out as a gameplay-specific signal.

## 9. Condition verification

The request states that Phigros remained on the song-selection screen with no song started. Log evidence does not confirm this:

- The Phigros process at the time of the marks was PID 3158, launched at 13:04:45 and still initializing at the first mark (13:04:46.314). Its screen state is not logged.
- Screen state is not logged, so "song-selection screen" cannot be verified from logs.
- No difficulty-selection events are recorded.
- The marks labeled "Game Start" conflict with "remained on song-selection", since they were recorded during launch.

## 10. Remaining uncertainties

1. Whether the game was on song selection at any point with Phigros logging active (PID 3158 logs end at 13:05:00; the Song Select marks are at 13:05:19 and 13:05:24).
2. Whether any song was started (no music-start signal in this capture; the 6,144-frame stop is a short track, not music).
3. Whether logcat dropped lines (no drop counter).
4. Whether PID 2289 was on song selection during its 81-minute lifetime (unknown).
5. The meaning of the 231M-frame AudioTrack stops on PID 2289 at 13:03:27 (sample rate not logged).
6. Whether the manual mark timestamps are synchronized with the device clock (verified only for Round 2).

## 11. Recommendation for the next experiment

Round 4 should be a control with a verified log window that spans the full UI interaction:

1. Start logcat capture before launching Phigros, and confirm capture is alive and the buffer is not dropping (`adb logcat -g` before and after).
2. Launch Phigros, wait for the song-selection screen to appear, and record that moment as a mark. Keep the game on song selection for at least 10 minutes, with timestamped marks for each difficulty selection and each wait.
3. Keep the app process alive for the whole session; do not kill or relaunch it.
4. Add a matched positive control in the same session: start one song and record its start mark, so C08 presence can be compared directly against the gameplay state in one process.

This design removes the confounds in Round 3: a relaunch during the marks, no logs after 13:05:00, and no screen-state record.

## 12. Files

- Source data (read-only): [report.txt](diags/1311202602/report.txt), [statistics.csv](diags/1311202602/statistics.csv), [raw_logs.txt](diags/1311202602/raw_logs.txt), [events.json](diags/1311202602/events.json)
- Session marks: [sessions.json](experiment_data/sessions.json)
- Capture command: [logcat_monitor.py](logcat_monitor.py)
