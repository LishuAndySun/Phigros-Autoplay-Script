# Audio Playback Pipeline Audit

Read-only audit of Round 1 (`1211202605`), Round 2 (`1211202606`), and Round 3 (`1311202603`) raw logs. No raw logs, events.json, report.txt, statistics.csv, sessions.json, source code, or PhiAPS were modified. No experiments were run.

## 1. Scope and Definitions

| Class | Meaning | Can it mark playback start? |
|---|---|---|
| Creation | AudioFlinger creates a track (`AfPlaybackCommon: creating track`) or client creates AudioTrack | No |
| Start request | AudioTrack start (not observed as a distinct log line in these rounds) | UNKNOWN |
| Submission | Client writes/obtains buffers (`obtainBuffer`, `releaseBuffer`) | No |
| Mixing output | Mixer/output-thread activity (`mixer throttle`, `interceptBuffer`) | Proxy only |
| Sound output | Audible sound at the speaker | UNKNOWN (no log proves this) |

Key rule: AudioTrack creation is not playback start. Buffer operations are not sound output.

## 2. Marks and Round Mapping

- Round 2 Play Start: 22:08:03.5 local (UTC+9). Play End: UNKNOWN from this review.
- Round 3 Game Start mark: 04:13:33Z = 13:13:33 local.
- Round 1 Play Start 12:17:13.9Z, Play End 12:19:21.0Z (UTC marks, per session notes).

## 3. Per-Round Evidence

### Round 2 (1211202606)
- Creation: `AfPlaybackCommon: creating track` at 22:07:29.495 (PID 500, TID 543). This is 34 s before Play Start. Classified as creation only.
- Client warnings in window before play: 21:16:45 (PID 4063) and other pre-play lines. Not in play window.
- Play window 22:08:03–22:08:58: no audio-tagged lines in raw_logs.
- C08 pair: `obtainBuffer benign 'Try again'` at 22:10:10.786 and 22:10:58.229 (PID 500 TID 576 releaseBuffer dropped wake at identical ms). Classified as buffer operations only, not sound output.
- Round 2 totals (raw_logs): stop 22, notificationFrames 22, creating track 22, mismatch 17, releaseBuffer dropped 8, obtainBuffer benign 8, deprecation 7+7, mixer throttle 4, unfrozen 4.

### Round 3 (1311202603)
- Only Phigros-process audio event in the start window: PID 3355 TID 3412. Deprecation at 13:13:31.432; `stop(35): called with 6144 frames delivered` at 13:13:31.630; deprecation at 13:13:31.642 (TID 3417).
- Process creation at 13:13:31.113 precedes the Game Start mark (13:13:33), so the alignment is UNKNOWN.
- Raw logs end at 13:14:06.608. No audio lines in 13:13:31.7–13:14:30. Total audio-tagged lines: 120 (timestamped).
- No C08 lines in R3.

### Round 1 (1211202605)
- Raw template counts (100 audio-matching lines): stop 18, notificationFrames 18, creating track 18, mismatch 14, releaseBuffer dropped 6, obtainBuffer benign 6, deprecation 6+6, mixer throttle 3, unfrozen 2, restartIfDisabled 1, BUFFER TIMEOUT 1, interceptBuffer 1.
- PIDs: 3307 (11), 3730 (21), 4063 (5), 500 (6).
- events.json parses as strings only in this review; no audio entries could be matched with receive_time. R1 timing against Play Start/End: UNKNOWN.

## 4. Candidate Summary

See [AUDIO_PLAYBACK_PIPELINE_CANDIDATES.csv](AUDIO_PLAYBACK_PIPELINE_CANDIDATES.csv).

Candidates closest to real audio start (ranked, with limits):
1. **C-03 (R3, PID 3355, 13:13:31.630)**: `stop(35)` with 6144 frames delivered. Shows the client had submitted audio frames. Alignment to Game Start is UNKNOWN; the process was created 2 s before the mark.
2. **C-07 (R2 mixer throttle)**: mixing-path proxy, but no timestamped hit in the play window.
3. **C-05/C-06 (R2 C08, 22:10:10.786 and 22:10:58.229)**: buffer operations with an underrun-like drop. Closer to in-play activity, but not sound output.

C08 is therefore not the best candidate for playback start; the R3 frame delivery at 13:13:31.630 is earlier and carries frame count evidence.

## 5. Verdict

Can the logs identify the true playback start? **No, not with confidence.**

- Creation (R2 22:07:29.495) is 34 s before Play Start, so it cannot mark playback start.
- Frame delivery (R3 stop 6144 frames) shows submitted data, not sound output.
- No log in the play window (R2 22:08:03–22:08:58) shows audio activity; the only in-window events are the two C08 buffer pairs.
- No log proves sound at the speaker. Any playback-start time is UNKNOWN from these logs.

## 6. UNKNOWN List

- R1 timing of all audio lines vs Play Start/End (events.json unreadable as dicts).
- R2 Play End time.
- R3 alignment of PID 3355 audio to Game Start (process created before mark).
- R2 play-window mixer activity (no timestamped hit).
- Sound output at the speaker in every round.
- AudioTrack start request as a distinct log line (not seen in these rounds).
