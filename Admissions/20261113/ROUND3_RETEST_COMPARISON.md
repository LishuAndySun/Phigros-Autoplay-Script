# Round 3 Retest Comparison: 1311202603 vs 1311202602

Audit only. No code, raw logs, events, reports, or session data were modified. No new experiment was run.

Scope: verify whether C08 (AudioTrackShared obtainBuffer / releaseBuffer) appears during song-select-only interaction, with no song started.

## 1. Data inventory

| Round | Directory | raw_logs lines | events | Notes |
|---|---|---|---|---|
| Round 1 | 1211202605 | see prior analysis | see prior analysis | C08 raw: 12 AudioTrackShared, 6 obtainBuffer benign |
| Round 2 | 1211202606 | see prior analysis | see prior analysis | C08 raw: 16 AudioTrackShared, 8 obtainBuffer benign |
| Negative control | 1311202602 | 90,059 | 90,049 | C08 raw: 0, AudioTrackShared in events: 0 |
| Round 3 (this audit) | 1311202603 | 98,371 | 98,361 | C08 raw: 0, AudioTrackShared in events: 0 |

## 2. C08 presence in 1311202603

- Raw logs: 0 `AudioTrackShared` lines, 0 `obtainBuffer: benign` lines.
- events.json: 0 `AudioTrackShared` matches.
- C08 is absent in this round.

Interpretation is limited. Absence in this round does not show that C08 is gameplay-specific, because the Phigros process has no log coverage during the Song Select marks (section 5). Per the audit rules, C08 presence or absence alone is not used as a conclusion.

## 3. First occurrence and PID/TID for C08 (prior rounds)

Round 2 (1211202606), 8 `obtainBuffer: benign` occurrences:

| Timestamp (device local) | PID | TID | Owner evidence |
|---|---|---|---|
| 11-12 20:46:01.818 | 3307 | 3507 | 23 PigeonGames/Unity-tagged lines for PID 3307. Process died at 21:01:30.935 (ActivityManager "has died", Zygote signal 9). No "Start proc 3307" line found: creation UNKNOWN |
| 11-12 21:10:22.736 | 3730 | 3928 | Start proc 3730 (com.PigeonGames.Phigros) at 21:01:33.487; died 21:16:41.231. Owner = Phigros |
| 11-12 21:12:30.395 | 3730 | 3928 | As above |
| 11-12 21:12:42.159 | 3730 | 3928 | As above |
| 11-12 21:13:05.551 | 3730 | 3928 | As above |
| 11-12 21:14:19.445 | 3730 | 3928 | As above |
| 11-12 22:10:10.786 | 4063 | 4458 | Start proc 4063 (com.PigeonGames.Phigros) at 21:16:45.470. Alive status at 22:10 not re-verified: UNKNOWN |
| 11-12 22:10:58.229 | 4063 | 4458 | As above |

Round 1 (1211202605): PID/TID enumeration was not repeated in this audit. UNKNOWN.

## 4. Process ID changes in 1311202603

Phigros-tagged PIDs observed in the audio stream:

| PID | Audio-tagged lines | Last line | Notes |
|---|---|---|---|
| 2137 | 7 | not re-verified | Earlier Phigros PID |
| 2289 | 25 | not re-verified | Earlier Phigros PID |
| 3158 | 25 | not re-verified | Later Phigros PID |
| 3355 | 12 | 13:13:38.236 | No lines in the 13:13:38–13:14:06 window |
| 504 | 68 | not re-verified | Not identified as Phigros: UNKNOWN |

Phigros PID changed three times (2137 → 2289 → 3158 → 3355). This restart pattern is not part of the protocol. Cause UNKNOWN.

## 5. Song Select marks vs process coverage

Marks read from `experiment_data/sessions.json`: 4 manual marks. Three are in the Song Select window: 13:13:48, 13:13:57, 13:14:01 (device local; session start 04:13:24 UTC matches first log at 13:13:21 device time, consistent with UTC+9).

Coverage in the 13:13:38–13:14:06 window:
- PID 3355 produced 0 lines after 13:13:38.236.
- No Phigros/Unity/PigeonGames/AudioTrack-tagged line appears in the window.
- Active PIDs in the window are system/other processes: 662 (211 lines), 1072 (81), 446 (24), 915 (15), 470 (6), 1005 (6).

Conclusion: the Song Select marks fall after the last Phigros log line. Whether the app was on the song-select screen during these marks is UNKNOWN.

The fourth mark's time and meaning were not re-verified in this audit: UNKNOWN.

## 6. Log continuity and loss

- Logcat has no drop counter. Log loss: UNKNOWN.
- Max gap between consecutive lines: round 3 10.099 s (13:12:05.446), round 2 9.997 s (13:04:03.284). Cause of ~10 s gaps: UNKNOWN.
- Round 2 unique lines (62,580) are all present verbatim in round 3 raw_logs, so round 3 contains round 2 content and extends it from about 13:06 onward.

## 7. Other-process check

- Audio-tagged lines in 1311202603 are dominated by PID 504 (68) and Phigros PIDs. PID 504 identity: UNKNOWN.
- No C08 lines appear from any other PID in round 3.

## 8. Difficulty switching

No marks exist for difficulty switches in this session. Whether any difficulty switch occurred: UNKNOWN.

## 9. Comparison summary

| Item | Round 2 (1211202606) | Negative control (1311202602) | Round 3 (1311202603) |
|---|---|---|---|
| C08 raw count | 16 | 0 | 0 |
| C08 events count | not re-verified | 0 | 0 |
| Phigros PIDs with C08 | 3307, 3730, 4063 | none | none |
| Song-select marks covered by Phigros logs | not checked | not checked | No |

## 10. UNKNOWN list

1. Creation of PID 3307 (no Start proc line found).
2. Alive status of PID 4063 at 22:10.
3. Round 1 PID/TID ownership.
4. Identity of PID 504.
5. Cause of Phigros PID changes (2137 → 2289 → 3158 → 3355).
6. Cause of ~10 s log gaps.
7. Log loss (no drop counter).
8. Whether the app was on song-select during the marks.
9. Difficulty switches.
10. Meaning and timing of the fourth manual mark.

## 11. Conclusion

- C08 is absent in 1311202603 (0 raw, 0 events).
- This absence cannot be attributed to the song-select-only condition, because the Phigros process has no log coverage in the Song Select window.
- C08 is not confirmed as gameplay-specific. This remains UNKNOWN.
- No further experiment is recommended from this audit alone until Phigros process coverage during selection is established.
