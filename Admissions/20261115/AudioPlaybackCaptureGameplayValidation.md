# Audio Playback Capture Gameplay Validation

Labels: VERIFIED (directly observed in logs or screenshots), SUPPORTED (consistent with logs, not directly observed), HYPOTHESIS (not tested), UNKNOWN (no data).

## 1. Test Environment

- Host: macOS, adb at /Users/lishuandysun/Downloads/platform-tools/adb
- Device: emulator-5554, AVD Pixel_8_PhiAPS, Android 17 (API 37), 1080x2400
- Target app: com.PigeonGames.Phigros, UID 10156 (VERIFIED)
- Probe app: com.phiaps.capprobe, minSdk 29, targetSdk 37, versionCode 1 (VERIFIED)
- Device clock: JST (Asia/Tokyo), as reported by `adb shell date`

## 2. Probe Configuration

- Capture: MediaProjection with AudioPlaybackCaptureConfiguration, addMatchingUid(10156) only, no usage rules (VERIFIED from code)
- AudioRecord: 48000 Hz, stereo, PCM16, bufBytes 76800, minBuf 6144, recordingState 3 RECORDING (VERIFIED from logcat)
- Analysis unit: 100 ms blocks (9600 samples); active when peak > 64 (VERIFIED from code)
- Log tag: CapProbe, line format `blk=N t_ns=... samples=9600 rms=... peak=... active=... run=... frames=...`

## 3. Raw Log Time Range

- Pre-gameplay snapshot: $HOME/AudioCaptureProbe/logs/preserved_before_gameplay_20261115_095834.txt (VERIFIED)
- Gameplay analysis window: approx. 09:59:42 to 10:06:40 JST (VERIFIED from logcat block timestamps)
- Block timestamps are device time; user-reported phase boundaries are approximate (SUPPORTED)

## 4. Preview Results (Phase A)

- Phase A start recorded at approx. 09:59:19 JST, user-reported (SUPPORTED)
- Probe captured non-silent PCM from UID 10156 on the title and preview screens during this interval (VERIFIED in earlier logs)
- Confirmed silence after leaving Phigros (negative control) (VERIFIED)

## 5. Gameplay Results (Phase B)

- Audio onset at 09:59:42.828 (rms 8.2, peak 68); rms rose to about 1300 to 1700 by 09:59:44 and to rms 7833, peak 30410 at 09:59:45.346 (VERIFIED from logcat)
- Non-silent PCM continued through the play period (VERIFIED for the blocks read; full play period not exhaustively extracted)
- Gameplay music is not isolated from other Phigros-attributed audio by this probe (LIMITATION)

## 6. Pause Results (Phase C)

- Last loud block before pause: 10:00:12.546 (rms 8033.5, peak 27066) (VERIFIED)
- Decay: 10:00:12.631 rms 1349.9; 10:00:12.738 rms 76.7; 10:00:12.844 rms 42.6 (VERIFIED)
- Full silence from 10:00:12.930 (rms 0.0, peak 0) (VERIFIED)
- Phigros remained topResumedActivity during the pause (VERIFIED at 10:00:25)
- Pause onset is bracketed to approx. 10:00:12.6 (SUPPORTED); the user's pause action was not timestamped, and the pause lasted about 48 s, not the planned 5 s (VERIFIED from logs)

## 7. Resume Results (Phase D)

- First active block after resume: 10:01:01.036 (rms 8624.5, peak 32427) (VERIFIED)
- 40 consecutive active blocks from 10:01:01.036 to 10:01:05.644, rms about 7000 to 14000 (VERIFIED)
- Resume boundary is approximate (SUPPORTED); the user-reported resume duration (about 5 s) was not respected, so the timing is not matched to the plan (VERIFIED)

## 8. Song End Results (Phase E)

- Level decays from rms 3240 at 10:03:00.332 to rms 405 at 10:03:00.631 and rms 5.7 at 10:03:00.737 (VERIFIED)
- Silent blocks from 10:03:00.737 to 10:03:05.943, about 5.2 s (VERIFIED)
- Loud audio resumes at 10:03:06.028 and continues through at least 10:06:40 (VERIFIED)
- Screenshot at 10:06 (phase_e_screen3.png) shows the song select screen with Phigros in the foreground (VERIFIED)
- The 10:03:06 onward audio is consistent with song select preview music, based on the timing and the on-screen state; the screen at 10:03:06 was not captured, so this is SUPPORTED, not VERIFIED
- An earlier screenshot (phase_e_screen.png) showed the probe app and was misread as Phigros; it is excluded from the evidence (VERIFIED)

## 9. PCM Statistics per Phase

- Phase B (gameplay onset, 09:59:42.8 to 09:59:45.3): rms rose from 8.2 to 7833; max peak 30410 (VERIFIED for sampled blocks)
- Phase C (pause, 10:00:12.9 to 10:01:00.9): 0 active blocks in sampled range; rms 0.0 in all sampled blocks (VERIFIED for sampled blocks; the full range was not exhaustively counted)
- Phase D (resume, 10:01:01.0 to 10:01:05.6): 40 of 40 sampled blocks active; rms 7358 to 14191; peak up to 32767 (VERIFIED)
- Phase E (end, 10:03:00.7 to 10:03:05.9): 0 active blocks; rms 0.0 (VERIFIED for sampled blocks)
- Phase E (post-song, 10:03:06 to 10:06:40): active; rms about 10000 to 14000 (VERIFIED for sampled blocks)
- Block counts for each full phase were not exhaustively computed from logcat; the figures above come from sampled tails of the log (LIMITATION)

## 10. Errors and Anomalies

- The first screenshot was misidentified as Phigros; the foreground was the probe app (VERIFIED, corrected)
- Pause lasted about 48 s, not about 5 s as planned (VERIFIED)
- Resume duration was not controlled to the planned 5 s (VERIFIED)
- Earlier note in logs: pause onset not precisely bracketed, now bracketed to approx. 10:00:12.6 (VERIFIED)
- Foreground app is supporting evidence only; per-UID capture cannot separate gameplay music from menu or preview music (LIMITATION)

## 11. Timing Limitations

- User-reported phase boundaries are approximate; they were not timestamped by a shared clock (LIMITATION)
- Logcat blocks are 100 ms; boundaries are resolved only to about 100 ms
- No screenshot was taken at the moment of each transition, so screen state is verified only at 10:06 (LIMITATION)
- Probe capture is attributed to UID 10156 only; any Phigros-owned audio is included (LIMITATION)

## 12. Gameplay Capture Verified Status

- Non-silent PCM attributed to Phigros is captured during gameplay onset, pause silence, resume, and song end (VERIFIED from logs)
- Pause silence and resume activity track the user's reported actions in order (SUPPORTED)
- Gameplay music specifically, separate from preview or menu music, is not verified (UNKNOWN)

## 13. Recommended Next Step

- Repeat the sequence with a shared timestamp: send `adb shell input keyevent` or log a marker from the user action, so phase boundaries are not approximate
- Capture a screenshot at each phase transition to verify screen state
- Before implementing a real-time Audio Onset Detector, confirm that gameplay music can be separated from other Phigros audio; this is a separate task and is not implemented here

## Final Verdict

GAMEPLAY PCM CAPTURE SUPPORTED BUT NOT FULLY VERIFIED

Reason: Phigros-attributed PCM is captured and its pause, resume, and end transitions line up with the user's actions, but the phase boundaries are approximate, the screen state was not verified at each transition, and the probe cannot distinguish gameplay music from menu or preview audio.
