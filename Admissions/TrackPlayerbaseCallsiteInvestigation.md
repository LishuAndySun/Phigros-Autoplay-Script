# TrackPlayerBase Call-site Investigation

Date: 2026-11-14
Experiment: `phigros_diagnostic/diags/1411202601/` (session `session_20261114_211923`, device `emulator-5554`, Android 17)
Scope: read-only. No application code, experiment data, sessions, markers, or configuration was modified. No experiment was rerun.

Labels: VERIFIED (directly observed in the cited file), SUPPORTED (consistent with the evidence, not proven), HYPOTHESIS (plausible, untested), UNKNOWN (cannot be determined from available material).

---

## 1. Executive Summary

- VERIFIED: The three constructor pairs are real log lines at [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt#L24600-L24615). They come from PID 2219, TID 2235, tag `onGames.Phigros`, and are not Android framework lines.
- VERIFIED: Each pair is followed within about 1 ms by a `libOpenSLES` line and then by an AudioFlinger `createTrack_l()` line in the audio server (PID 506, TID 738). The three `createTrack_l()` lines carry flags `0x104`.
- VERIFIED: The matching Android source is not in the workspace, and the emulator is not connected to `adb`. The build fingerprint cannot be read, so no AOSP call site can be checked.
- UNKNOWN: The exact caller of `TrackPlayerBase::TrackPlayerBase()` inside the Phigros process. The constructor name is printed by the app's own tag, so the emitting code is not in Android. The game binary or an injected hook would have to be examined, which is out of scope here.
- SUPPORTED: The three bursts are three separate track-creation events by the game's audio layer, each generating one AudioFlinger track. They occur at scene entry, about 0.27 s after Game Start and about 24 s before PREVIEW_PLAYING.
- SUPPORTED: The constructions are initialization, not playback. Nothing in the log shows that audio was audible at the time.

---

## 2. Experiment Evidence

Source: [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt) (lines 24600 to 24615), read with `grep -n` and `sed -n`.

VERIFIED: The raw lines below are the six constructor entries, with the following audio lines.

| Line | Device time (21:19:42.xxx local, UTC+9) | Level | PID/TID | Tag | Message |
|---|---|---|---|---|---|
| 24600 | .072 | D | 2219/2235 | onGames.Phigros | `PlayerBase::PlayerBase()` |
| 24601 | .072 | D | 2219/2235 | onGames.Phigros | `TrackPlayerBase::TrackPlayerBase()` |
| 24602 | .072 | I | 2219/2235 | libOpenSLES | `Emulating old channel mask behavior (ignoring positional mask 0x3, using default mask 0x3 based on channel count of 2)` |
| 24603 | .073 | W | 506/738 | AudioFlinger | `createTrack_l(): mismatch between requested flags (00000104) and output flags (00000002)` |
| 24603 | .073 | D | 506/738 | AudioFlinger | `Client defaulted notificationFrames to 960 for frameCount 4360` |
| 24603 | .073 | I | 506/738 | AF::AfPlaybackCommon | `creating track with enforcement level 1 reason TARGET_SDK shouldHarden 1` |
| 24606 | .077 | D | 2219/2235 | onGames.Phigros | `PlayerBase::PlayerBase()` |
| 24607 | .077 | D | 2219/2235 | onGames.Phigros | `TrackPlayerBase::TrackPlayerBase()` |
| 24608 | .077 | I | 2219/2235 | libOpenSLES | channel mask emulation (same text) |
| 24609 | .077 | W | 506/738 | AudioFlinger | `createTrack_l()` flag mismatch `00000104` |
| 24612 | .080 | D | 2219/2235 | onGames.Phigros | `PlayerBase::PlayerBase()` |
| 24613 | .080 | D | 2219/2235 | onGames.Phigros | `TrackPlayerBase::TrackPlayerBase()` |
| 24614 | .080 | I | 2219/2235 | libOpenSLES | channel mask emulation (same text) |
| 24615 | .081 | W | 506/738 | AudioFlinger | `createTrack_l()` flag mismatch `00000104` |

Note: the grep output lists lines 24602, 24603, 24608, 24609, 24614, and 24615 as the audio lines. The per-line AudioFlinger `Client defaulted` and `creating track` lines are the continuation of line 24603 and 24609, as shown in the `sed` context output.

VERIFIED: Earlier AudioFlinger track creations appear before the constructions and before Game Start (12:19:41.851Z):
- [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt#L23846): 21:19:40.727 (12:19:40.727Z), `createTrack_l()` flags `00000004`, PID 506
- [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt#L24491): 21:19:41.741 (12:19:41.741Z), `createTrack_l()` flags `00000008`, PID 506

These two have no `onGames.Phigros` constructor next to them. Their owner is unknown.

VERIFIED: The constructor lines carry no object address, no audio session ID, and no track name. The AudioFlinger lines carry no client PID, so the link between a game constructor and an AudioFlinger track is by timing only.

VERIFIED: Clock domains. Device local time is UTC+9. Converted to UTC, the bursts are at 12:19:42.072Z, .077Z, and .080Z. The `receive_time` values from the earlier audit were 12:19:42.121Z to .130Z, a lag of about 49 to 50 ms for these live lines.

Excerpt from [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt#L24600-L24603):

```
[11-14 21:19:42.072  2219  2235 D onGames.Phigros: PlayerBase::PlayerBase()]
[11-14 21:19:42.072  2219  2235 D onGames.Phigros: TrackPlayerBase::TrackPlayerBase()]
[11-14 21:19:42.072  2219  2235 I libOpenSLES: Emulating old channel mask behavior (ignoring positional mask 0x3, using default mask 0x3 based on channel count of 2)]
[11-14 21:19:42.073   506   738 W AudioFlinger: createTrack_l(): mismatch between requested flags (00000104) and output flags (00000002)]
```

---

## 3. Android Build Information

VERIFIED: The emulator is not reachable. `adb devices` returns an empty list, and `adb -s emulator-5554 shell getprop ro.build.fingerprint` returns `device 'emulator-5554' not found`.

VERIFIED: No AOSP tree or Android source is present under the home directory (`~/aosp` and `~/android` do not exist) or in the workspace.

VERIFIED: The build information recorded in the experiment is limited to:
- Device model `Android SDK built for arm64`, Android 17, from `sessions.json` (session metadata).
- The audio server dump [audio_flinger.txt](audio_flinger.txt#L1-L10) was captured from a different process set. Its notification client is PID 2215 (`com.PigeonGames.Phigros`, uid 10156) and its timestamp is 12:52 local, not the 21:19 run. It is not the same process as PID 2219, so it is not used as evidence for this run.

UNKNOWN: The exact fingerprint (`ro.build.fingerprint`) and the system library build (`libaudioflinger.so`, `libOpenSLES.so`) for the run. These need to be read from the emulator or from its system image.

Decision: no substitute Android version source was used. Android 17 AudioFlinger behavior is not assumed.

---

## 4. PlayerBase / TrackPlayerBase Class Relationship

VERIFIED (repo, not Android source): The repo treats these as the app's own debug markers. [event_parser.py](phigros_diagnostic/event_parser.py#L14-L17):

```
PLAYER_BASE_CREATED = "PlayerBase::PlayerBase()"
PLAYER_BASE_DESTROYED = "PlayerBase::~PlayerBase()"
TRACK_PLAYER_BASE_CREATED = "TrackPlayerBase::TrackPlayerBase()"
TRACK_PLAYER_BASE_DESTROYED = "TrackPlayerBase::~TrackPlayerBase()"
```

VERIFIED: The regexes at [event_parser.py](phigros_diagnostic/event_parser.py#L78-L81) match the same strings. The parser does not define inheritance, namespace, or the `android::` prefix. The name `android::TrackPlayerBase` in the task statement is not present in the repo or in the log. The log shows `TrackPlayerBase::TrackPlayerBase()` with no namespace.

UNKNOWN: Whether `TrackPlayerBase` derives from `PlayerBase`, and whether the `android::` namespace is correct. The Android source is needed to confirm this. The log does not say.

HYPOTHESIS: Both names are symbols or debug strings inside the game's native audio layer, which is not the Android framework. The `android::` prefix in the task is likely a guess or taken from AOSP naming, and should not be used without evidence.

Constructor and destructor implementations: UNKNOWN. No destructor line exists in the log (see section 9).

---

## 5. Constructor Call-site Search

VERIFIED: Searches run in the workspace (excluding `venv` and `diags`) for `TrackPlayerBase`, `PlayerBase`, and `onGames` returned only:
- [event_parser.py](phigros_diagnostic/event_parser.py) (marker definitions)
- [timeline.py](phigros_diagnostic/timeline.py#L360-L361) (pair statistics: `pb_pairs` and `tp_pairs`, label "Create/Destruct cycles")
- [test_phase2.py](phigros_diagnostic/tests/test_phase2.py) (test fixtures, not production call sites)
- Admissions notes (previous reports that mention these names)

VERIFIED: No `new TrackPlayerBase`, no factory function, and no C++ definition were found in the workspace. No source file in the repo creates these objects.

UNKNOWN: The immediate caller, source file, and line number. These would be in the Phigros binary or an injected hook, neither of which is in the workspace. Finding them would require either:
- the game's debug symbols or a rebuilt debug binary, or
- a disassembly of the APK's native library (`libil2cpp.so` or equivalent). This is reverse engineering and was not started, because it is outside the read-only scope and the log alone has not shown that it is needed to answer the question.

---

## 6. Reconstructed Call Chain

VERIFIED (from the log only):

```
[Phigros process PID 2219, TID 2235]
  PlayerBase::PlayerBase()
  TrackPlayerBase::TrackPlayerBase()
  libOpenSLES: channel mask emulation       (same thread, +0 to +0.001 s)
        |
        v
[audioserver PID 506, TID 738]
  AudioFlinger createTrack_l(): flags 0x104 vs output 0x2   (+1 ms)
  notificationFrames 960, frameCount 4360
  AF::AfPlaybackCommon: creating track, enforcement 1, reason TARGET_SDK
```

SUPPORTED: The OpenSL ES library (`libOpenSLES`) sits between the constructor and the AudioFlinger track request, and it is in the same thread as the constructor. This makes OpenSL ES the most likely audio API path for these objects. It is not proven, because the log does not show the call from `libOpenSLES` into AudioFlinger.

Path classification (task item 3):
- AudioTrack: SUPPORTED as the AudioFlinger track type, based on the `AudioTrack`-style `createTrack_l` and `notificationFrames` lines. The log does not name the AudioTrack client.
- AudioRecord: NOT SUPPORTED. The flags describe a playback track (output flags `0x2`, `AUDIO_DEVICE_OUT_SPEAKER`), and no capture line appears.
- AudioFlinger: VERIFIED as the server-side component that creates the track.
- Another audio subsystem (OpenSL ES, Unity, or the game's own engine): SUPPORTED as the client layer, UNKNOWN in detail.

Caller chain above the constructor (game entry point, scene loader, song preview): UNKNOWN.

---

## 7. Interpretation of the Three Constructor Bursts

VERIFIED: Three bursts occur, each with a `PlayerBase` line followed by a `TrackPlayerBase` line, each followed by a `libOpenSLES` line and a `createTrack_l` line. The gaps are:
- burst 1: 12:19:42.072Z
- burst 2: 12:19:42.077Z (+5 ms)
- burst 3: 12:19:42.080Z (+3 ms)

VERIFIED: Within a burst, the `PlayerBase` and `TrackPlayerBase` lines differ by 0 ms at millisecond resolution. The pair is a single creation step, not two independent events.

SUPPORTED: The three bursts are three separate `TrackPlayerBase` object constructions, each creating one AudioFlinger track. The evidence is the one-to-one sequence of constructor, OpenSL ES line, and track creation for each burst, with the same flags.

Alternative (HYPOTHESIS): One object is constructed three times in a retry or re-initialization loop, for example if a track creation fails and is retried. This is not supported here, because all three AudioFlinger requests have the same flags and succeed in the log, and no error or failure line follows them.

Alternative (HYPOTHESIS): The three bursts are three audio objects of different roles (for example preview, gameplay, and effects). Their flags are identical, so this cannot be checked from the log.

Relation to the experiment: the bursts are at 12:19:42Z. Game Start is 12:19:41.851Z (+0.22 s to +0.23 s before the first burst). The earlier audit gave +0.27 s using the `receive_time` figures, which is the difference in clock domain. The earlier pre-Game-Start AudioFlinger track creation at 12:19:41.741Z is 110 ms before Game Start.

---

## 8. Initialization vs Actual Playback Analysis

VERIFIED timing relative to the manual marks (host UTC):
- Game Start: 12:19:41.851358
- Bursts: 12:19:42.072 to .080 (about 0.22 to 0.23 s after Game Start)
- PREVIEW_PLAYING: 12:20:05.772488 (about 23.7 s after the last burst)
- START_TRIGGER: 12:20:24.275281
- FIRST_AUDIO_PEAK: 12:20:32.284097
- Play End: 12:22:31.867098

Playback-related evidence in this window: none that identifies playback. The log between the bursts and PREVIEW_PLAYING contains no `libOpenSLES` play or start call, no AudioFlinger `start` or `setVolume` line, and no output-thread write that can be attributed to the game. The AudioFlinger output thread in [audio_flinger.txt](audio_flinger.txt#L1-L10) shows `Standby: yes` in the dump, but that dump is from a different process set and time (see section 3).

VERIFIED: The `receive_time` field has about 50 ms latency for these lines. The `FIRST_AUDIO_PEAK` marker was recorded by a human and is not an audio measurement, so no direct audio-to-log comparison is possible.

Conclusion: SUPPORTED. The bursts are initialization of audio objects at scene entry. They are not the start of audible playback. Audible playback is not shown in the log at the time of the bursts, and the constructors alone do not show that sound was produced.

---

## 9. Limitations and Confidence Assessment

Limitations:
- No Android source or emulator access. The build fingerprint and framework version are unknown.
- The constructor messages are app-level debug strings. Their emitter (game code or injected hook) is unknown.
- No destructor lines: the lifecycle matcher returns 0 pairs. The capture ends at 12:22:46.7Z, 7.7 s after Score Screen, so destructors after scene exit are outside the capture or not logged.
- AudioFlinger lines carry no client PID. The link between game constructors and AudioFlinger tracks is by 1 to 5 ms timing only, which is strong for co-occurrence but not proof of causation.
- The `android::` namespace in the request is not present in any available source or log.

Confidence:
- Three separate constructions, each with one AudioFlinger track: SUPPORTED (medium-high).
- Path via OpenSL ES to AudioFlinger: SUPPORTED (medium).
- Exact caller, file, and line: UNKNOWN (no source).
- Initialization, not playback: SUPPORTED (high for "construction is not audible playback"; medium for the timing claim).
- Lifecycle matcher explanation: SUPPORTED that the logs lack destructors and keys, but the matcher source was not reviewed (UNKNOWN for the matcher key).

---

## 10. Recommended Next Investigation

1. Reconnect the emulator (`emulator-5554`) and record `ro.build.fingerprint`, `ro.build.version.release`, and the `libaudioflinger.so` and `libOpenSLES.so` build IDs.
2. Obtain the Android source tag or system image that matches the fingerprint, then check `AudioFlinger::createTrack_l`, `AfPlaybackCommon`, and the OpenSL ES player creation path for the caller chain.
3. Locate the game's native library in the installed APK (`com.PigeonGames.Phigros`). Confirm whether the `PlayerBase` and `TrackPlayerBase` strings come from the game or from an injected hook. Only do this with explicit approval, because it is reverse engineering.
4. Capture a log that includes destructors and track start or stop calls, with a longer tail after Score Screen, to test the lifecycle explanation.
5. Add client identifiers (PID or session ID) to AudioFlinger lines in a controlled capture, to link tracks to constructors without relying on timing.

---

## 11. Sources and File References

- [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt#L23846): `createTrack_l()` flags `00000004`, 12:19:40.727Z, before Game Start.
- [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt#L24491): `createTrack_l()` flags `00000008`, 12:19:41.741Z, before Game Start.
- [raw_logs.txt](phigros_diagnostic/diags/1411202601/raw_logs.txt#L24600-L24615): six constructor lines, three `libOpenSLES` lines, three `createTrack_l()` lines.
- [event_parser.py](phigros_diagnostic/event_parser.py#L14-L17): marker names for PlayerBase and TrackPlayerBase.
- [event_parser.py](phigros_diagnostic/event_parser.py#L78-L81): regex patterns for the same markers.
- [timeline.py](phigros_diagnostic/timeline.py#L360-L361): pair counters labeled "Create/Destruct cycles".
- [audio_flinger.txt](audio_flinger.txt#L1-L10): audio server dump from a different time and PID (2215), not used as run evidence.
- [sessions.json](experiment_data/sessions.json): session metadata (device model and Android version).
- Terminal: `adb devices` returned no device; `adb -s emulator-5554 shell getprop ro.build.fingerprint` returned `device 'emulator-5554' not found`.

Android source files (AudioFlinger, OpenSL ES, Phigros native code): not available in the workspace; no excerpts can be given.
