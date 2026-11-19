# OpenSL ES Realize and Play-State Audit

Read-only analysis. No PhiAPS source, experiment data, session records, emulator state, or APK/Phigros native libraries were modified or inspected. No new experiment was run and no packages were installed. AOSP main was not used as evidence.

## Scope and Identity

- Device: emulator-5554, Android 17 (API 37), fingerprint `Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys`.
- Analyzed binaries (hash-verified scratch copies in `$TMPDIR/android17_libs`):
  - libwilhelm.so `9a630485f4e8e13e94103983f2e9eb0818fd71e5b47df515f8a2c42687b7266b`
  - libaudioclient.so `0189039cd976a25deb1cfed6210932540f07b9719b53958b6671f04841f8bea1`
  - libOpenSLES.so `771ca94c10f7103d0f4e9a966f847d03c83327ac8db6ff2bc528cd36d899bdcc`
  - libaudiobase.so `633890a33aea6497264fd38a130030bb632b22975171b8b79ab7c9608d0b59fe`
- libmedia.so was not device-verified and was not used.
- Tools: llvm-objdump, llvm-nm (Apple LLVM 14.0.3), Python 3 ELF parsing.
- Output-file absence was checked before writing. `sessions.json` SHA-256 `1d201f71f0fd8bd77b4d95294457e3e6fde0c6c5b3d45b069b02ad52fbc0cd2f` was checked and unchanged.

## Corrections to Earlier Notes

- `IEngine_CreateAudioPlayer` is a local symbol in libwilhelm.so, not a dynamic export.
- The `TrackPlayerBase` init bound used earlier (0x75ce8) is wrong. That address is `SelfAudioDeviceCallback::onAudioDeviceUpdate`. The authoritative bound comes from `.dynsym`: `_ZN7android15TrackPlayerBase4initE...` at value 0x756ec, size 0x390, end 0x75a7c.
- The `blr x9` at 0x76248 is outside `TrackPlayerBase::init`. It is not part of init.

## Task A: libwilhelm.so offset 0x43278

- The `.rela.dyn` section uses APS2 packing. It was decoded with the declared entry count (359) and exact section end. No entries fall in 0x40000-0x44000.
- The `.relr.dyn` section uses RELR packing. Decoding it gives:
  - Slot 0x43278 is RELR-relocated. Its stored value is 0x34e58, which is `IEngine_CreateAudioPlayer`.
  - 0x34e58 appears only once in `.data.rel.ro`, at this slot.
  - The slot is part of a RELR run from 0x42f98 to 0x43760 (slot index 92 in the run).
  - Neighbors include `IEngine_CreateAudioRecorder` (0x35158) and `IVolume_GetStereoPosition` (0x3c4dc, near run end). The run is shared with unrelated subsystems.
- No ADRP/ADD or direct address computation produces 0x43278 (zero exact hits).
- The indexed reader of this slot was not identified.

Verdicts:
- Slot content (points to `IEngine_CreateAudioPlayer`): VERIFIED.
- Slot is part of an engine dispatch table: UNKNOWN. The run is shared, and no reader was found.

## Task B: IEngine to Realize Path

Verified direct `bl` edges:
- `IEngine_CreateAudioPlayer` to `android_audioPlayer_create` at 0x350dc.
- `android_audioPlayer_create` to the TrackPlayerBase constructor at 0x203cc.
- `android_audioPlayer_realize` to AudioTrack C1 at 0x21170.
- `android_audioPlayer_realize` to `TrackPlayerBase::init` at 0x21348.
- `android_audioPlayer_realize` to `TrackPlayerBase::getAudioTrack` at 0x21494.

Not verified:
- No direct `bl` or `b` from the IEngine chain to `android_audioPlayer_realize` was found.
- A full `.text` search for all callers of `android_audioPlayer_realize` was not completed.

Verdicts:
- IEngine reaches Realize through a verified direct path: UNKNOWN. No direct edge was found.
- Any indirect path from IEngine to Realize: HYPOTHESIS.

## Task C: TrackPlayerBase::init (libaudioclient.so)

Bounds (from `.dynsym`): 0x756ec to 0x75a7c, size 0x390. The debug table does not contain this function (its entry near 0x756ec is a `ThN96` thunk).

Calls inside init (228 instructions):
- Direct `bl`: `PlayerBase::init` (PLT 0x7b850).
- Direct `bl`: `std::mutex::lock` and `unlock`.
- Direct `bl`: `sp<AudioTrack>::operator=` at 0x75a7c (the address just past init).
- Direct `bl`: `sp<IAudioTrackCallback>::operator=` at 0x75b98.
- Direct `bl`: `operator new` (0x7a6a0), `RefBase::RefBase` (0x7a670), `RefBase::incStrong` and `decStrong`.
- Direct `bl`: `AudioTrack::addAudioDeviceCallback` (0x7b1f0) and `AudioTrack::setPlayerIId` (0x7b1e0).
- Direct `bl`: `__cfi_slowpath` and `__stack_chk_fail`.

Indirect calls (`blr`/`br`): none inside init.

The `blr x9` at 0x76248 is outside init. Its preceding instructions load `[x21]` and an offset. Its containing function is not verified.

Verdicts:
- Init contains no indirect calls: VERIFIED.
- Init reaches an AudioTrack constructor directly: NOT FOUND. Only `AudioTrack` member calls and `sp` operators appear.
- Init reaches an AudioTrack constructor indirectly: UNKNOWN.

## Task D: android_audioPlayer_setPlayState (libwilhelm.so 0x22458)

Direct calls:
- `PlayerBase::baseUpdateDeviceIds` at 0x226f8.
- `PlayerBase::reportEvent` at 0x22708.

Field writes:
- `str wzr, [x19, #2616]` at 0x225e4, 0x22640, 0x226a0.
- `strb w8, [x19, #2672]` at 0x22710 (after `reportEvent`).
- Stack writes at 0x224a4, 0x224f4 are local.

Indirect calls (vtable loads, targets not resolved):
- `blr x9` at 0x224dc: `[x8, #296]` of an object loaded from `[sp, #64]`.
- `blr x9` at 0x22660: `[x8, #40]` of object `[x19, #2632]`.
- `blr x8` at 0x226b4: `[x8, #64]` of object `[x19, #2648]`.

Verdicts:
- `setPlayState` calls `PlayerBase` event reporting and device-ID updates: VERIFIED.
- `setPlayState` stores to a play-state field at offset 2672 (0x2a0): VERIFIED as a write. Its semantic meaning is UNKNOWN.
- `setPlayState` calls AudioTrack start, pause, or stop: UNKNOWN. The virtual call targets are not resolved.

## Task D (Realize Indirect Calls)

Six `blr` sites in `android_audioPlayer_realize` load vtable slots from objects whose types are not established:
- 0x20fbc: `[x8, #40]`, `x0 = x20`, `w1 = 12`.
- 0x213a8: `[x8, #328]`, object from `[sp, #184]`.
- 0x21444: `[x8, #48]`.
- 0x2146c: `[x8, #264]`, `x0 = x21`.
- 0x21484: `[x8, #136]`, `x0 = x21`.
- 0x214d4: `[x8, #1824]`, `x0 = x21`.

Targets cannot be named from the binary alone without object-type evidence. Verdict: UNKNOWN for each target.

## Task E: Summary Verdicts

1. Is 0x43278 part of a verified engine dispatch table? Slot content is VERIFIED (RELR, value 0x34e58). Dispatch role is UNKNOWN (shared run, reader not found).
2. Is there a verified IEngine to Realize path? UNKNOWN. No direct edge found; a HYPOTHESIS remains for an indirect path.
3. What are the Realize callers? UNKNOWN. A full `.text` caller search was not completed.
4. What are the indirect calls in TrackPlayerBase::init? VERIFIED: none inside init. The `blr` at 0x76248 is outside init.
5. What does `setPlayState` do? VERIFIED: device-ID update, `PlayerBase` event report, and a write to offset 2672. UNKNOWN: AudioTrack start/stop/pause.
6. Is there a reliable gameplay-audio-start signal? UNKNOWN. No signal was established. A `PlayerBase` event is not evidence that audio became audible.

## Limitations

- Analysis used scratch copies, not device-side reads at runtime.
- Only direct `bl` edges are treated as verified calls. All `blr` targets are unresolved.
- Debug-symbol names are not runtime proof. The libaudioclient debug table is incomplete for init.
- APS2 `.rela.dyn` was decoded by count validation, not by an independent parser.
- No runtime observation was made. Realize is not assumed to mean Play, and a PlayerBase event is not assumed to mean audible audio.

## Next Steps

- Resolve the object types behind the `blr` sites by tracing construction and layout.
- Run a full `.text` search for callers of `android_audioPlayer_realize`.
- Identify the function containing 0x76248 and its bounds.
