# Android 17 Audio Creation Path (Emulator emulator-5554)

Scope: read-only analysis. No PhiAPS source or experiment data was modified, the experiment was not rerun, and the emulator was not reconfigured. No APK reverse engineering was performed.

## 1. Build identity (VERIFIED on device, 2026-11-14T12:45:02Z UTC)

- ro.build.fingerprint = Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys
- ro.build.id = CE2A.260420.051.A3
- ro.build.version.incremental = 16571990
- ro.build.version.sdk = 37, release = 17, security_patch = 2026-08-05
- ro.build.tags = test-keys, ro.build.type = userdebug

Library build IDs (GNU build-id, device copies):

| Library | Build ID | Source of check |
|---|---|---|
| /system/lib64/libOpenSLES.so | 4f9b436de4a0a3b0a1f1886a2c6e44d0 | VERIFIED (device) |
| /system/lib64/libaudioclient.so | d5e03623b0ca530f899f320ba7c9811d | VERIFIED (device) |
| /system/lib64/libwilhelm.so | not read (readelf absent locally) | NOT CHECKED |
| /system/lib64/libaudioflinger_*.so | not read | NOT CHECKED |

Local copies (scratch, $TMPDIR/android17_libs/):
- libwilhelm.so sha256 9a630485f4e8e13e94103983f2e9eb0818fd71e5b47df515f8a2c42687b7266b (307672 bytes)

Note: there is no standalone libaudioflinger.so. The AudioFlinger code is split across libaudioflinger_datapath.so, _fastpath.so, _timing.so, and _utils.so.

## 2. Matching source (UNKNOWN)

- Public AOSP AudioTrack.cpp was fetched from android.googlesource.com at refs/heads/main. This is a moving branch, not revision for build 16571990. It is not used as evidence for this build.
- The ci.android.com aosp-android17-release page returned HTTP 404. No build-ID-to-revision mapping was obtained.
- No AOSP tag or revision was verified for CE2A.260420.051.A3. Do not cite a branch or revision for this build.
- Preview/custom-build uncertainty: the build is userdebug with test-keys, which suggests a non-release emulator image. Matching public source may not exist.

## 3. OpenSL ES creation path (SUPPORTED by symbols and strings)

- libwilhelm.so exports `IEngine_CreateAudioPlayer(SLEngineItf, SLObjectItf*, SLDataSource*, SLDataSink*, SLuint32, const SLInterfaceID*, const SLboolean*)`. This is the OpenSL ES player-object creation entry point.
- libwilhelm.so contains the literal "CreateAudioPlayer" in 2 locations and the literal "Invalid buffer type in Android Buffer Queue".
- libwilhelm.so contains the literal string "Emulating old channel mask" (VERIFIED by grep). This matches the observed log line.
- libwilhelm.so contains the strings "PlayerBase" and "TrackPlayerBase" (one occurrence each). It also contains mangled symbols `_ZN7android15TrackPlayerBase4initE...` and `_ZN7android10PlayerBase...` as imported references.
- libwilhelm.so does NOT contain the literal strings "PlayerBase::PlayerBase" or "TrackPlayerBase::TrackPlayerBase". The log-line form of those names is therefore not emitted from libwilhelm.so.

Conclusion for Task 2: the OpenSL ES engine path is in libwilhelm.so, and it creates players that use TrackPlayerBase through libaudioclient. The constructor-log literal `TrackPlayerBase::TrackPlayerBase` is not present in libwilhelm.so.

## 4. AudioFlinger createTrack_l and client API (SUPPORTED for symbols, UNVERIFIED for flags)

- libaudioclient.so exports `_ZN7android10AudioTrack13createTrack_lEv` (android::AudioTrack::createTrack_l()).
- libaudioclient.so exports `_ZN7android10AudioTrackC1E...` and `C2E...` constructors.
- libaudioclient.so contains the strings "notificationFrames=%d not permitted for non-fast track" and "Server adjusted notificationFrames from %u to %zu for frameCount %zu".
- The literal "defaulted notificationFrames" was not found in any pulled library.
- The literal "creating track with enforcement" was not found in any pulled library.
- The literal "mismatch between requested flags" was not found in any pulled library, and not in the device system partitions.
- The host-side AudioFlinger modules (libaudioflinger_*.so) did not match any of the searched log strings. The `flags 0x104` vs `output 0x2` message in the raw log could not be traced to a binary in the pulled set.

Meaning of flags 0x104 (HYPOTHESIS, UNVERIFIED): bit values must be checked against the matching audio-base headers. Do not map them from memory. The observed value is recorded as raw data only.

Client-side request (from the public main-branch source, not build-verified): AudioTrack::createTrack_l() calls `audioFlinger->createTrack(...)` and sets `input.flags = mFlags`. This is a source-level claim for main, not for this build.

## 5. PlayerBase and TrackPlayerBase identity (VERIFIED by symbols)

- Namespace: android (mangled `N7android`).
- libaudioclient.so exports:
  - `_ZN7android10PlayerBaseC1Ev`, `C2Ev`, `D0Ev`, `D1Ev`, `D2Ev` (PlayerBase constructors and destructors)
  - `_ZN7android15TrackPlayerBaseC1Ev`, `C2Ev`, `D0Ev`, `D1Ev`, `D2Ev` (TrackPlayerBase constructors and destructors)
  - `_ZN7android15TrackPlayerBase9doDestroyEv`, `_ZN7android15TrackPlayerBase7destroyEv`
  - `_ZN7android15TrackPlayerBase4initE...` (init taking AudioTrack, callback, player_type_t, usage, session)
  - `_ZN7android15TrackPlayerBase23SelfAudioDeviceCallbackC1ERNS_10PlayerBaseE` (nested callback class)
  - `_ZTVN7android15TrackPlayerBaseE` (vtable, confirms a polymorphic class)
- Inheritance: the mangled name for TrackPlayerBase's base is not directly visible. The symbol `_ZN7android10PlayerBase...` (for example `baseUpdateDeviceIds`, `reportEvent`) is referenced from libwilhelm.so, which indicates TrackPlayerBase derives from or uses PlayerBase. Exact inheritance (`_ZTIN7android15TrackPlayerBaseE` typeinfo base) was not confirmed. Mark as SUPPORTED, not VERIFIED.
- Constructors: C1 and C2 both exist (base and complete object variants).
- Destructors: D0 (deleting), D1 and D2 (complete and base) both exist, with thunk variants `_ZThn8_N7android15TrackPlayerBaseD1Ev` and `_ZTv0_n24_N7android15TrackPlayerBaseD1Ev` (multiple-inheritance thunks).

## 6. Caller separation (Task 5)

- Caller of createTrack_l: the client-side AudioTrack in libaudioclient.so calls createTrack_l, then the AudioFlinger server receives IAudioFlinger::createTrack. The AudioFlinger side is not in a process present in the pulled set, so the server-side call site is UNKNOWN for this build.
- Caller of TrackPlayerBase constructor in the Phigros process: UNKNOWN. The constructor symbols exist in libaudioclient.so, but no call site was found in a Phigros binary. The APK was not analyzed (per constraint).
- The two callers are separate: the AudioTrack client path (libaudioclient) and the TrackPlayerBase constructor (created from libwilhelm's OpenSL ES path, per the imported symbols). Linking them to each raw log event requires PID and TID correlation, which was not done here.

## 7. Raw-log correlation (unchanged from prior audit)

- Constructor pairs at 12:19:42.072, .077, .080 UTC, followed by "Emulating old channel mask behavior" and createTrack_l flags 0x104 vs output 0x2 (PID 506, TID 738 in the November 14 log). The current audioserver PID is 509, so the PIDs do not match the current device state.
- Receive time is host-side; device time requires +9 h alignment.

## 8. Evidence limitations

- libwilhelm.so, libaudioflinger_*.so build IDs were not verified.
- Local readelf is unavailable; device readelf was not used on libwilhelm.so.
- The log literals "defaulted notificationFrames", "creating track with enforcement", and "mismatch between requested flags" were not found in any pulled library.
- Source-level behavior (createTrack_l, flags) is taken from main, not from this build.

## 9. Conclusions

- VERIFIED: fingerprint and library build IDs for libOpenSLES.so and libaudioclient.so.
- VERIFIED: libwilhelm.so contains "Emulating old channel mask" and IEngine_CreateAudioPlayer.
- VERIFIED: libaudioclient.so exports PlayerBase and TrackPlayerBase constructors, destructors, and createTrack_l.
- NOT VERIFIED: matching AOSP source revision.
- NOT FOUND: literal "PlayerBase::PlayerBase" or "TrackPlayerBase::TrackPlayerBase" in any pulled library.
- UNKNOWN: caller of TrackPlayerBase constructor in the Phigros process; flag meanings for 0x104 and 0x2.

## 10. Recommended next steps

1. Read build IDs for libwilhelm.so and libaudioflinger_*.so on device with readelf to complete the identity table.
2. Look for a verified AOSP tag or build-to-revision mapping for CE2A.260420.051.A3 / 16571990. Do not guess a branch.
3. Confirm the 0x104 and 0x2 flag meanings against the audio-base headers of the matching revision, not main.
4. Correlate PID and TID of the raw log with the current audioserver and client processes before trusting any caller attribution.
5. Use the APK only if the user later approves reverse engineering; it is out of scope now.
