# Song Select Log Activity Analysis

Audit only. No code or experiment data was modified. Hypothesis tested: Phigros produces few Unity / PigeonGames / AudioTrack logs on the song-select screen, and these logs appear mainly after gameplay starts.

Time conventions: manual marks are UTC. Raw logcat lines are device local time (UTC+9). Round 2 local = UTC + 9 h (e.g. Map Load Start 13:07:55 UTC = 22:07:55 local).

## 1. Data available per round

| Round | raw_logs | events.json | Log timestamps usable | Manual marks |
|---|---|---|---|---|
| Round 1 (1211202605) | no bracketed timestamps in raw; 368 Unity/PigeonGames/AudioTrack-tagged events total | 28,042 events, all `timestamp` null; only `receive_time` (UTC) | No (receive_time only, 12:16:41–12:19:xx UTC) | 7: Game Start, Map Load Start, Play Start, Pause, Resume, Play End, Score Screen |
| Round 2 (1211202606) | 39,298 events; raw logs with `[MM-DD HH:MM:SS.mmm PID TID ...]` | parsed | Yes | 8: two Map Load/Play pairs, then Play End, Score Screen |
| Round 3 (1311202603) | 98,371 lines | parsed | Yes | 4: Game Start, three Song Select |

Round 1 phases cannot be bucketed from log time. Its only usable time information is `receive_time`, which shows all tagged activity in a 15-second burst at 12:16:41–12:16:56 UTC, which is before the Map Load Start mark (12:17:07). Round 1 selection-phase activity: UNKNOWN.

## 2. Round 2 process identity and lifecycle

Phigros PIDs identified by `com.PigeonGames.Phigros` process start/death lines (ActivityManager):

| PID | Start | Death | Notes |
|---|---|---|---|
| 3307 | before 20:41 local (no start line in capture) | 21:01:30.934 | Died with signal 9 |
| 3730 | 21:01:33.487 | 21:16:41.231 | Alive for the 21:01–21:16 span |
| 4063 | 21:16:45.470 | not observed (no death line) | Alive at capture end (22:11:08) per absence of death line; active lines at 22:10:58 |

Process existence is confirmed by log lines plus start/death lines. PID 4063 has no log lines between about 21:20 and 22:07 local, which is a log gap, not evidence of process absence (no death line found). Whether PID 4063 was idle, on the selection screen, or otherwise quiet during that gap: UNKNOWN.

## 3. Round 2 phase counts

Manual marks converted to local time: Map Load Start 22:07:55, Map Load End 22:08:00, Play Start 22:08:03, second Map Load Start 22:08:50, second Map Load End 22:08:55, second Play Start 22:08:58, Play End 22:11:03, Score Screen 22:11:06.

Caveat: the two Map Load/Play pairs are 45 s apart; the second Play Start (22:08:58) falls before the Play End (22:11:03). Whether the first pair was a real play start is UNKNOWN; this audit treats the first pair as the play-entry candidate and the second as a retry or second load.

Per-PID counts for PIDs that are Phigros in round 2 (3730, 4063):

| Window (local) | PID | Lines | Unity-tagged | PigeonGames-tagged | AudioTrack-tagged | AudioTrackShared |
|---|---|---|---|---|---|---|
| Before 21:16:45 (PID 3730 alive) | 3730 | 264 | 82 | 18 | 21 | 5 |
| 21:16:45 to 22:07:55 (PID 4063 alive; no mark) | 4063 | 234 | 79 | 17 | 11 | 0 |
| 22:07:55 to 22:08:50 (first Map Load to second Map Load) | 4063 | 3 | 0 | 0 | 0 | 0 |
| 22:08:58 to 22:11:03 (Play window) | 4063 | 6 | 0 | 0 | 2 | 2 |

Round 2 whole-process totals and window boundaries are not exact for PID 3307 (no start line; UNKNOWN). Per-window counts for PID 643 (system, not Phigros) and PIDs 1071, 444, 466 are excluded from the Phigros analysis.

Largest single-PID clusters of Unity-tagged activity are at 21:01 (PID 3730: 87 lines) and 21:16 (PID 4063: 87 lines), both immediately after process start. These bursts correspond to process launch, not to the song-select screen, and are not tied to any mark.

## 4. Hypothesis evaluation

Question 1 (selection phase vs play phase counts, round 2): The 22:07:55–22:11:03 window is only 9 raw lines for PID 4063 in total (3 before the second load, 6 in play). Play-window Unity/PigeonGames count: 0. AudioTrackShared in the play window: 2 (both at 22:10:10 and 22:10:58 local, obtainBuffer benign). The earlier high counts (~80 per PID) come from process launch, not from the marked selection phase. The hypothesis "logs cluster around play" is NOT supported by this data: Unity-tagged logs are denser at process start (21:01, 21:16) than in the marked play window.

Question 2 (round 1): not evaluable from log time. UNKNOWN.

Question 3 (Unity logs without AudioTrack logs in a phase): PID 4063 in the 21:16–22:07 window: 79 Unity-tagged lines, 11 AudioTrack-tagged, 0 AudioTrackShared. Unity logs without AudioTrackShared are present in this span. Whether this span is selection screen: UNKNOWN (no mark). In the 22:07:55–22:11:03 window, Unity-tagged count is 0 and AudioTrack-tagged count is 2. So Unity logs without AudioTrack logs occur in the unmarked span; the marked play window shows the reverse.

Question 4 (process persistence): PID 4063 has no death line through capture end. Log absence 21:20–22:07 does not indicate absence of the process. Persistence: confirmed by absence of death line; activity: UNKNOWN for 21:20–22:07.

Question 5 (phase boundaries): Manual marks in round 2 are sufficient to bound the second load and play windows, but not the selection screen (no selection-screen mark exists in round 2). The selection phase in round 2 is UNKNOWN. Round 3 has Song Select marks, but its Phigros PID 3355 has no log lines after 13:13:38.236 local, before those marks, so round 3 selection activity is UNKNOWN.

## 5. Caveats and what this audit cannot show

- No selection-screen mark exists in round 2 or round 1. The selection screen cannot be isolated; the unmarked 21:16–22:07 span may contain selection, menu, or idle time.
- Phigros PID changes across rounds break the per-process comparison. Round 2 uses 3730 then 4063; round 3 uses 2137 → 2289 → 3158 → 3355.
- Absence of AudioTrackShared is not evidence of absence of audio. AudioTrackShared is present in 3 Phigros-window lines in round 2 and absent elsewhere; whether audio was playing in the unmarked spans is UNKNOWN.
- The logcat stream has no drop counter. Gaps (~10 s max in both rounds) are UNKNOWN in cause.
- Round 1 timing is not reconstructable from raw log timestamps; all round 1 `timestamp` fields are null.

## 6. Conclusion

- The data does not support the hypothesis that Phigros logs are sparse on the song-select screen and dense only in play. The densest Phigros Unity/PigeonGames activity in round 2 occurs at process start, and the marked play window contains only 6 Phigros-PID lines.
- The round 2 selection screen cannot be isolated because no mark bounds it and PID 4063 is silent for roughly 47 minutes before the first load mark. Whether this silence reflects the selection screen, an idle process, or logcat loss: UNKNOWN.
- Round 1 selection-phase log activity: UNKNOWN (no usable timestamps).
- Round 3 selection-phase activity: UNKNOWN (no Phigros PID log coverage in the Song Select marks).
- To resolve, a new experiment would need a selection-screen mark and a confirmed active Phigros PID during selection. This audit does not recommend running one.

## 7. UNKNOWN list

1. Round 1 phase boundaries (no timestamps in raw logs or events).
2. PID 3307 start time (no start line in capture).
3. PID 4063 activity 21:20–22:07 local (no marks; no death line).
4. Whether the first Map Load/Play pair in round 2 was a real play start.
5. Round 2 selection-screen presence and duration.
6. Round 3 Song Select activity (PID 3355 silent before marks).
7. Whether audio was playing in unmarked spans.
8. Cause of ~10 s log gaps and any logcat loss.
