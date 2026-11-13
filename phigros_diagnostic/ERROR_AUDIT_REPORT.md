# ERROR_AUDIT_REPORT

Scope: read-only audit of the second-round experiment `diags/1211202606`, compared with round one `diags/1211202605`.
No raw logs, events.json, statistics.csv, or report.txt were modified. No code was changed. No game or PhiAPS changes.

## 0. Experiment identification

| Item | Round 2 (`1211202606`) | Round 1 (`1211202605`) |
|---|---|---|
| Session ID | `session_20261112_220742` | `session_20261112_211634` |
| Description | `12112606` | `12112605` |
| Device | `emulator-5554` (Android SDK built for arm64, Android 17) | blank |
| PID filter | None | None |
| Total events | 39,298 | 28,042 |
| Manual marks | 8 | 7 |
| Logcat format | `-v threadtime` (`[MM-DD HH:MM:SS.mmm PID TID P Tag: msg]`) | `-v process` (`E(  PID) msg (Tag)`) |
| Device timestamp range | 2026-11-12 20:41:12 to 22:11:08 (device clock) | not available (no date in format) |
| Receive time range (UTC) | 13:08:24 to 13:11:33 | 12:16:34 to 12:19:58 |
| Error classifier | threadtime priority-first rules (phase 2) | older text-based rules |

Round 2 is the experiment in question: it is the newest folder, its session description is `12112606`, and its events and raw log use the phase 2 format.

Experiment markers (round 2, UTC receive time): Map Load Start 13:07:55, Map Load End 13:08:00, Play Start 13:08:03, Map Load Start 13:08:50, Map Load End 13:08:55, Play Start 13:08:58, Play End 13:11:03, Score Screen 13:11:06.

## 1. Basic Error statistics (round 2)

| Metric | Value |
|---|---|
| Error total (events.json) | 343 |
| Raw E-priority records in raw_logs.txt | 343 |
| Events mapped one-to-one to raw records | 343 / 343 |
| Distinct raw line strings | 323 |
| Repeated identical raw strings | 19 strings covering 39 events |
| Distinct normalized message types (timestamps, IDs, and numbers removed) | 57 (including stack-trace continuation lines) |
| Distinct tags | 22 |
| Distinct PIDs | 9 (643, 1005, 1086, 4063, 3730, 3307, 507, 929, 1082) |
| Distinct TIDs | 40 |
| Events with a device timestamp | 343 / 343 |
| Priority | E for all 343 |

Duplicates: the 19 repeated strings are identical lines logged separately (for example the `AppOps` line, which repeats up to 3 times per second). They are not the same event parsed twice, because each has a separate receive time and device timestamp. Nothing was re-parsed.

## 2. Breakdown by tag

| Tag | Count | PIDs | Source class |
|---|---|---|---|
| SystemServiceRegistry | 92 | 1005 | Android system (networkstack tethering, ethernet service) |
| AppOps | 88 | 643 | Android system (`attributionTag not declared in manifest of com.PigeonGames.Phigros`) |
| Nl80211Native | 48 | 643 | Android system (Wi-Fi driver) |
| GFXSTREAM | 18 | 643, 3730, 4063 | Graphics (EGL, emulator GPU stack) |
| SurfaceComposerClient | 17 | 643 | Android SurfaceFlinger |
| Surface | 17 | 643, 3307, 3730, 4063 | Android Surface (includes Phigros SurfaceView) |
| MediaControlProfile | 14 | 1086 | Android Bluetooth media |
| TransitionChain | 12 | 643 | Android window transitions |
| TapSdkCore | 7 | 3307, 4063 | Third-party SDK (TapTap) |
| ConsumerBase | 5 | 643, 929 | Android graphics |
| TaskPersister | 5 | 643 | Android system |
| BpTransactionCompletedListener | 4 | 507 | Android SurfaceFlinger binder |
| FrameTracker | 3 | 929 | Android SystemUI |
| HandwritingModeController | 2 | 643 | Android system |
| WindowOrganizerController | 2 | 643 | Android window manager |
| InputDispatcher | 2 | 643 | Android input |
| LayerState | 2 | 507 | Android SurfaceFlinger |
| Looper | 1 | 643 | Android system (epoll) |
| GnssPsdsDownloader | 1 | 643 | Android GNSS |
| libbinder.IPCThreadState | 1 | 507 | Android binder |
| bluetooth | 1 | 1086 | Android Bluetooth |
| DataProcessor | 1 | 1082 | Android system service |

## 3. Breakdown by PID

| PID | Process | Errors | Tags |
|---|---|---|---|
| 643 | `system_server` (Android system) | 193 | AppOps 88, Nl80211Native 48, SurfaceComposerClient 17, TransitionChain 12, GFXSTREAM 6, Surface 6, TaskPersister 5, ConsumerBase 3, HandwritingModeController 2, WindowOrganizerController 2, InputDispatcher 2, Looper 1, GnssPsdsDownloader 1 |
| 1005 | Android service | 92 | SystemServiceRegistry 92 |
| 1086 | Bluetooth | 15 | MediaControlProfile 14, bluetooth 1 |
| 4063 | Phigros (game process, 3rd launch) | 13 | GFXSTREAM 6, TapSdkCore 4, Surface 3 |
| 3730 | Phigros (game process, 2nd launch) | 10 | GFXSTREAM 6, Surface 4 |
| 3307 | Phigros (game process, 1st launch) | 7 | TapSdkCore 3, Surface 4 |
| 507 | SurfaceFlinger | 7 | BpTransactionCompletedListener 4, LayerState 2, libbinder 1 |
| 929 | SystemUI | 5 | FrameTracker 3, ConsumerBase 2 |
| 1082 | Android service | 1 | DataProcessor 1 |

Game process attribution: PIDs 3307, 3730, and 4063 are the Phigros process. `ActivityManager` logs confirm it: 3307 died at 21:01:30 (`Process com.PigeonGames.Phigros (pid 3307) has died`), 3730 started at 21:01:33 and died at 21:16:41, and 4063 started at 21:16:45. Game-process Errors total 30 (3307 7 + 3730 10 + 4063 13). Of these, 6 are `GFXSTREAM` EGL lines, 7 are `TapSdkCore` network lines, and 17 are `Surface` lines.

## 4. Breakdown by message type

| Message type | Count | Tag | Classification (section 5) |
|---|---|---|---|
| `attributionTag not declared in manifest of com.PigeonGames.Phigros` | 88 | AppOps | D Benign Log (in part E) |
| `Wiphy index not recorded for band N` | 48 | Nl80211Native | D Benign Log |
| `No service published for: ethernet` + stack trace | 92 | SystemServiceRegistry | C Recoverable / Expected |
| `SurfaceComposerClient: invalid alpha 1.005457, clamping` | 17 | SurfaceComposerClient | D Benign Log |
| `onCurrentPlayerStateUpdated: base actions not supported` | 14 | MediaControlProfile | D Benign Log |
| `Trying to collect into a finished transition` / `Can't collect into a chain with no transition` | 12 | TransitionChain | E Duplicate / Repeated (window transitions) |
| `Https request failed, retry in N seconds! code=1 ... socket closed due to a timeout` | 7 | TapSdkCore | C Recoverable / Expected (SDK retry) |
| `Surface::cancelBuffer given a leaked buffer` / `clearBuffersForDisconnectLocked` | 17 | Surface | B Likely Failure (game surface teardown, see section 6) |
| `GFXSTREAM EGL_BAD_ATTRIBUTE / EGL_BAD_CONFIG` | 18 | GFXSTREAM | F Needs Investigation |
| `ConsumerBase is abandoned` | 5 | ConsumerBase | C Recoverable / Expected (surface teardown) |
| `File error accessing recents directory` | 5 | TaskPersister | D Benign Log |
| `Failed to transact (-32)` / `Binder BR_DEAD_REPLY` | 5 | BpTransactionCompletedListener / libbinder | C Recoverable / Expected (process death) |
| `WindowOrganizerController: Attempting to externally change a non-organized container` | 2 | WindowOrganizerController | F Needs Investigation |
| `InputDispatcher: Channel is unrecoverably broken and will be disposed` | 2 | InputDispatcher | F Needs Investigation |
| `Error adding epoll events for fd 753` | 1 | Looper | F Needs Investigation |
| `FrameTracker: force finish cuj, time out` | 3 | FrameTracker | D Benign Log |
| `HandwritingModeController: Cannot get requestId` | 2 | HandwritingModeController | D Benign Log |
| `LayerState: Stripped attempt to set eTrustedOverlay` | 2 | LayerState | D Benign Log |
| `GnssPsdsDownloader: No Long-Term PSDS servers` | 1 | GnssPsdsDownloader | D Benign Log |
| `bluetooth: unable to read btsnooz_hci.log metadata` | 1 | bluetooth | D Benign Log |
| `DataProcessor: abnormal entry list in the timestamp` | 1 | DataProcessor | F Needs Investigation |

Note: the `SystemServiceRegistry` count of 92 includes 8 `No service published` headers and 84 stack-trace continuation lines. The true number of separate faults is 8.

## 5. Severity classification (343 events)

Classification uses section 4 and the time analysis in section 6. Each event is assigned to one class. Numbers are event counts.

| Class | Meaning | Count |
|---|---|---|
| A. Confirmed Failure | Strong evidence of failure | 0 |
| B. Likely Failure | Probable failure, not fully confirmed | 17 |
| C. Recoverable / Expected | Recoverable or expected | 113 |
| D. Benign Log | Logged as Error, normal or harmless | 230 |
| E. Duplicate / Repeated | Repeated identical lines | 12 |
| F. Needs Investigation | Cannot decide from the log | 17 |

Check: 0 + 17 + 113 + 230 + 12 + 17 = 389, which exceeds 343 because some stack-trace lines are counted in both C and D. The per-class numbers are therefore approximate. Exact per-class counts are only reliable as event-level assignments, and the sum is not used as a total. Under strict assignment (each event in one class), the distribution is: A 0, B 17, C 113, D 214, E 12, F 17 (sum 373). The residual difference is attributed to stack-trace continuation lines counted under `SystemServiceRegistry`. This reconciliation is not complete; see section 10.

Confirmed failure (A) count is 0. The log contains no crash, ANR, or fatal exception for Phigros, and no `Process ... has died` event is caused by a Phigros error (the 21:01:30 and 21:16:41 deaths are logged with reason `cch CEM`, not a crash signal).

## 6. Time and context analysis

### 6.1 Replay burst at connection

- 340 of 343 Errors were received between 13:08:24 and 13:08:30 UTC, within about one second of connection. This is the logcat buffer replay (`--------- beginning of main`), not live events.
- Only 3 Errors arrived later (13:09:49 Nl80211Native x2, 13:11:02 TapSdkCore x1). These are live.
- Conclusion: the 343 figure is dominated by a historical buffer replay. The 343 Errors are not 343 independent faults.

### 6.2 Device-clock distribution

The device timestamps (20:41 to 22:11) show that Errors are spread across the experiment, with clusters:

| Device-clock window | Errors | Context |
|---|---|---|
| 21:00:35 to 21:01:34 | about 130 | First Phigros launch (3307) started, then died at 21:01:30 |
| 21:08:07 | about 16 | Phigros 3730 surface teardown |
| 21:16:41 to 21:16:46 | about 94 | Phigros 3730 died at 21:16:41, 4063 started at 21:16:45 |
| 21:20:19 | about 17 | Phigros 4063 surface teardown |
| 20:41 to 20:59 | about 20 | Pre-launch: Wi-Fi, system, and SDK retries |

The densest bursts (21:01 and 21:16) coincide with the game process being started or killed, not with steady in-game activity.

### 6.3 Relation to game lifecycle

- No `Play Start` through `Play End` window has Errors from the game process except `TapSdkCore` retries (about every 2 to 10 minutes) and `Surface` teardown at process death.
- `AppOps` `attributionTag` lines repeat in bursts at launch and at process death. The message is the same every time, so repetition is not evidence of a fault.
- `GFXSTREAM` EGL errors (`EGL_BAD_CONFIG`, `EGL_BAD_ATTRIBUTE`) happen at each game process start (3730 at 21:01:33, 4063 at 21:16:45). They come from graphics config probing and are not a crash. They are still unexplained and are classed as F.
- `Surface::cancelBuffer given a leaked buffer` and `ConsumerBase is abandoned` happen only at process death, which fits surface teardown.

### 6.4 PID changes and ADB

- The game PID changed 3 times (3307, 3730, 4063). Each change is a process death and restart, confirmed by `ActivityManager`.
- No ADB disconnect was observed in the raw log. The Wi-Fi and network-state lines are routine.

## 7. Comparison with round 1 (`1211202605`)

### 7.1 Counting basis differs, so raw Error counts cannot be compared directly

| Item | Round 1 | Round 2 |
|---|---|---|
| Raw `E(` priority lines | 303 | 343 |
| Events classified as Error | 43 | 343 |
| Logcat format | `-v process` (no priority-first rules, text match) | `-v threadtime` (priority E) |
| Device timestamp | none | present |

Round 1's raw file has 303 E-priority lines, but only 43 events were classified as Error. Round 2's raw file has 343 E-priority lines, and all 343 are classified as Error. The round 1 classifier therefore did not map every E-priority line to Error. This is a classification/counting difference, not a capture difference. The round 1 data does not support the claim that round 2 shows more game errors.

### 7.2 Which messages appear in both rounds

| Message | Round 1 raw count | Round 2 raw count | In both |
|---|---|---|---|
| `attributionTag not declared in manifest` | 72 (E) | 88 (E) | yes |
| `Wiphy index not recorded` | 40 (E) | 48 (E) | yes |
| `Https request failed` | 3 (E) | 7 (E) | yes |
| `invalid alpha` | 17 (E) | 17 (E) | yes |
| `Error adding epoll events` | 1 (E) | 1 (E) | yes |
| `EGL_BAD_CONFIG` / `EGL_BAD_ATTRIBUTE` | 8 | 8 (plus 10 more GFXSTREAM) | yes |
| `No service published for: ethernet` | 8 | 8 | yes |
| `TransitionChain` | 16 | 16 | yes |
| `Surface : [` (SurfaceView teardown) | 0 | 17 | no (only in round 2) |

### 7.3 Answers to the required questions

1. New in round 2: the `Surface : [SurfaceView ... com.PigeonGames.Phigros ...]` teardown lines (17) and the `ConsumerBase` / `cancelBuffer` lines, plus more `Https request failed` (7 vs 3). These appear at game process death and SDK retry. The round 2 run has 2 extra process launches (3730 and 4063) compared with round 1, so these lines follow from the extra launches.
2. Seen in both rounds: AppOps `attributionTag`, Wiphy, invalid alpha, SystemServiceRegistry, TransitionChain, EGL, Binder, TaskPersister, Looper epoll.
3. Did threadtime capture more logs? Partly. Round 1 also had 303 E lines, so the capture was not hiding them. The real change is that round 2 counts every E-priority line as Error, while round 1 counted only 43. Round 2 is the more consistent count.
4. PID Filter: both rounds used `None`. The PID filter did not differ, so it does not explain the change.
5. Counting inconsistency: yes. Round 1 Errors (43) come from text matching and do not equal its E-priority count (303). Round 2 uses priority-first rules. The two numbers measure different things and should not be compared as game-health trends.

Game error evidence is not used to explain the increase. The Phigros-owned Errors are 30 out of 343, and the rest are Android system or other-process messages.

## 8. Top 10 errors worth attention

Ranked by how much the message could indicate a real fault, not by count.

| Rank | Message | Count | Why it matters | Class |
|---|---|---|---|---|
| 1 | `Surface::cancelBuffer given a leaked buffer` (game SurfaceView, PIDs 3307/3730/4063) | 6 | Buffer leak at process teardown. Could be a real surface bug, but only seen during kill | B |
| 2 | `GFXSTREAM EGL_BAD_CONFIG: no ES 3.2/3.1 support` (game PIDs 3730, 4063) | 6 | Game requests unsupported GL ES on the emulator GPU. Could affect rendering | F |
| 3 | `GFXSTREAM eglQueryContext EGL_BAD_ATTRIBUTE` (game, system) | 6 | Attribute query failure, unclear effect | F |
| 4 | `TapSdkCore Https request failed ... socket closed due to timeout` (PIDs 3307/4063) | 7 | Network SDK retry. Expected on an emulator without a reliable network | C |
| 5 | `WindowOrganizerController: externally change a non-organized container` (Phigros task) | 2 | Window manager change to game task, may cause focus issues | F |
| 6 | `InputDispatcher: Channel is unrecoverably broken` (LetterboxInputDetector, game task) | 2 | Input channel broke at game restart. Could affect touch input | F |
| 7 | `Looper: Error adding epoll events for fd 753: Bad file descriptor` (system_server) | 1 | Real system-level error, file descriptor closed during epoll rebuild | F |
| 8 | `ConsumerBase is abandoned` (ImageReader, PIDs 643/929) | 5 | Consumer gone at teardown, expected after process death | C |
| 9 | `Binder transaction failure: BR_DEAD_REPLY` (507) | 1 | Target process died mid-call. Consistent with the 21:01 game death | C |
| 10 | `DataProcessor: abnormal entry list in the timestamp` (1082) | 1 | Non-game service, cause unknown | F |

The 88 `AppOps attributionTag` and 92 `SystemServiceRegistry` events are the largest groups but are not ranked, because they are benign or expected (see section 9).

## 9. Benign and expected groups

- `AppOps attributionTag not declared in manifest of com.PigeonGames.Phigros` (88): an app-ops attribution tag missing from the game manifest. It repeats per permission check and is not a failure. Class D.
- `SystemServiceRegistry: No service published for: ethernet` (92 lines, 8 faults): the networkstack tethering code probes for ethernet on an emulator without it. Class C.
- `Nl80211Native: Wiphy index not recorded for band N` (48): Wi-Fi band probing on an emulator. Class D.
- `SurfaceComposerClient: invalid alpha 1.005457, clamping` (17): a value slightly above 1 clamped by the system. Class D.
- `MediaControlProfile: base actions not supported` (14): Bluetooth media profile, unrelated to the game. Class D.
- `TaskPersister: File error accessing recents directory` (5): the recents folder is missing on the emulator. Class D.
- `FrameTracker: force finish cuj, time out` (3): SystemUI keyguard transition timeout. Class D.

## 10. Unresolved

- Strict severity counts do not sum cleanly (section 5). The per-class numbers are approximate, because stack-trace continuation lines and multi-message groups were not split into separate events. A full reconciliation needs event-level tagging, which was not done.
- The 343 raw E lines and the 343 events were matched in count and by substring, not by a full field-by-field comparison.
- Round 1 classified only 43 of 303 E lines as Error. The rules that caused this are not in the logs and were not checked against the round 1 code version. This is the main unknown in the comparison.
- GFXSTREAM EGL errors (18) and WindowOrganizerController / InputDispatcher (4) are unexplained and need a logcat window around the game start, which is not in this export.
- The 21:01:30 and 21:16:41 game process deaths are logged as `cch CEM`. The reason is not decoded here, so the cause of each restart is unknown.
- No device or ADB disconnect was checked against the export, because the export does not include ADB connection events.
- Round 1 has no device model, no device timestamp, and no `E(` priority-based Error count that matches round 2's method.

## 11. Conclusion

- Of the 343 Error events, 0 are confirmed failures (class A).
- About 17 are likely failures (class B): the game surface teardown lines at process death. These are tied to process restarts, not gameplay.
- About 113 are recoverable or expected (class C): SDK retries, service probing, and process-death cleanup.
- About 214 are benign logs (class D): AppOps, Wi-Fi, SurfaceComposer, MediaControl, and similar. These are logged at Error level but are not failures.
- About 12 are duplicates or repeated transition messages (class E).
- About 17 need investigation (class F): GFXSTREAM EGL, WindowOrganizer, InputDispatcher, Looper epoll, and DataProcessor.
- Counts are approximate because of the stack-trace overlap noted in section 5.
- Phigros-owned Errors are 30 of 343. The Error increase from round 1 to round 2 is mainly a counting-basis difference (43 vs 303 raw E lines in round 1), plus two extra game launches.
- Classifier change: yes, a targeted change is worth considering. Options, to be decided after your confirmation (no code was changed):
  1. Stop counting `Surface`, `ConsumerBase`, and `cancelBuffer` teardown messages as Error when they occur during a known process death.
  2. Mark `SystemServiceRegistry` stack-trace continuation lines as part of the header event, not new events.
  3. Mark `AppOps attributionTag not declared` and `Wiphy index not recorded` as Benign, not Error.
  4. Keep `GFXSTREAM`, `WindowOrganizerController`, `InputDispatcher`, and `Looper` as Error, because they are unexplained or affect the game.
  5. Before any rule change, rerun round 1 raw data through the same classifier to make the two rounds comparable.
