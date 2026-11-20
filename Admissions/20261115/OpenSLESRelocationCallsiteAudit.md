# OpenSL ES Relocation and Call-Site Audit (Android 17)

Scope: read-only analysis of scratch copies of device libraries. No PhiAPS source, experiment data, emulator state, APK, or Phigros native library was changed or analyzed. No packages were installed.

## 1. Tools

| Tool | Path | Version / note |
|---|---|---|
| llvm-objdump | /Library/Developer/CommandLineTools/usr/bin/llvm-objdump | Apple LLVM 14.0.3 (clang-1403.0.22.14.1), default target arm64-apple-darwin27.2.0. Used for `-R`, `-d`, `-h`. |
| llvm-nm | /Library/Developer/CommandLineTools/usr/bin/llvm-nm | Used for `-D` and debug-table listing. |
| otool | /usr/bin/otool | Apple cctools-1005.2. Not needed for results. |
| device readelf | /system/bin/readelf (device) | Supports `-n`, `-S`, `-d`, `--dyn-syms`. Does **not** support `-r`, so relocations cannot be listed on device. |
| llvm-readelf, llvm-objcopy | not found | Section extraction done with a short Python ELF section reader. |

## 2. Input identity

Scratch directory: `$(getconf DARWIN_USER_TEMP_DIR)/android17_libs` (resolved to `/var/folders/dd/mm9z8jh96wd2hq5fhsw_03100000gn/T/android17_libs`).

SHA-256 values match the device-recorded hashes (verified before analysis):

| File | SHA-256 |
|---|---|
| libwilhelm.so | 9a630485f4e8e13e94103983f2e9eb0818fd71e5b47df515f8a2c42687b7266b |
| libaudioclient.so | 0189039cd976a25deb1cfed6210932540f07b9719b53958b6671f04841f8bea1 |
| libOpenSLES.so | 771ca94c10f7103d0f4e9a966f847d03c83327ac8db6ff2bc528cd36d899bdcc |
| libaudiobase.so | 633890a33aea6497264fd38a130030bb632b22975171b8b79ab7c9608d0b59fe |

libmedia.so (685376 bytes) is in the scratch directory but is not in the device hash list and was not used as verified input.

Build identity (from earlier audit): ro.build.id CE2A.260420.051.A3, fingerprint `Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys`.

## 3. libwilhelm.so structure

From `llvm-objdump -h`: `.rela.dyn` at 0x49d0 (size 0x523), `.relr.dyn` at 0x4ef8 (0x110), `.rela.plt` at 0x5008 (0x12d8), `.plt` at 0x3c690 (0xcb0), `.text` at 0x1c000 (0x20688), `.got.plt` at 0x44060 (0x660), `.gnu_debugdata` (0x29f0).

Dynamic exports: the device `.dynsym` shows no export for `IEngine_CreateAudioPlayer`. This is confirmed. The string appears only as text, so the earlier statement that libwilhelm exports it was wrong.

## 4. Imported audio symbols: relocations and PLT

Source: `llvm-objdump -R libwilhelm.so`. All six entries are `R_AARCH64_JUMP_SLOT` in `.rela.plt`.

| GOT slot | Symbol | PLT stub | bl sites in .text |
|---|---|---|---|
| 0x44190 | TrackPlayerBase::setPlayerVolume(float,float) | 0x3c8e0 | 0x1fabc |
| 0x441b0 | TrackPlayerBase::TrackPlayerBase() (C1Ev) | 0x3c920 | 0x203cc |
| 0x441c0 | TrackPlayerBase::init(...) | 0x3c940 | 0x21348 |
| 0x441f0 | PlayerBase::baseUpdateDeviceIds(...) | 0x3c9a0 | 0x226f8 |
| 0x441f8 | PlayerBase::reportEvent(...) | 0x3c9b0 | 0x21ba8, 0x22708, 0x22e44 |
| 0x44280 | AudioTrack::AudioTrack() (C1, long overload) | 0x3cac0 | 0x21170 |

Method: PLT stub `adrp x16, 0x44000` plus `ldr x17, [x16, #imm]` gives the GOT slot; this was matched against `.rela.plt` offsets.

Limitations: `.rela.dyn` (ANDROID-packed) was not decoded; `.relr.dyn` was not decoded. Relocations were read from llvm-objdump, which decoded `.rela.plt` correctly.

## 5. Caller functions (names from `.gnu_debugdata`)

`.gnu_debugdata` was extracted (10736 bytes) and decompressed with xz to 53536 bytes. It contains a local symbol table (`llvm-nm`: 674 entries). Names below come from this table. These are local/debug names and are not dynamic exports.

| Call site | Target | Enclosing function (debug symbol) | Function start |
|---|---|---|---|
| 0x203cc | TrackPlayerBase C1Ev | `_Z26android_audioPlayer_createP19CAudioPlayer_struct` | 0x20378 |
| 0x21348 | TrackPlayerBase::init | `_Z27android_audioPlayer_realizeP19CAudioPlayer_structj` | 0x207b4 |
| 0x21170 | AudioTrack C1 (long) | `_Z27android_audioPlayer_realizeP19CAudioPlayer_structj` | 0x207b4 |
| 0x1fabc | TrackPlayerBase::setPlayerVolume | `_Z32android_audioPlayer_volumeUpdateP19CAudioPlayer_struct` | 0x1f920 |
| 0x226f8 | PlayerBase::baseUpdateDeviceIds | `_Z32android_audioPlayer_setPlayStateP19CAudioPlayer_struct` | 0x22458 |
| 0x21ba8 | PlayerBase::reportEvent | `_ZL28sfplayer_handlePrefetchEventiiiPv` | 0x21810 |
| 0x22708 | PlayerBase::reportEvent | `_Z32android_audioPlayer_setPlayStateP19CAudioPlayer_struct` | 0x22458 |
| 0x22e44 | PlayerBase::reportEvent | `_Z44android_audioPlayer_bufferQueue_onRefilled_lP19CAudioPlayer_struct` | 0x22dc4 |

Function bounds come from the next symbol start, not from prologue heuristics. The heuristic prologue scan was discarded.

## 6. Creation chain (direct bl edges, verified)

- `_ZL25IEngine_CreateAudioPlayer...` (0x34e58–0x35158, size 768) contains `bl 0x20378` at 0x350dc to `android_audioPlayer_create`.
- `android_audioPlayer_create` (0x20378–0x204b8, size 320) contains `bl 0x3c920` at 0x203cc to the TrackPlayerBase C1Ev PLT stub.
- `android_audioPlayer_realize` (0x207b4–0x21608, size 3668) contains `bl 0x3c940` at 0x21348 (TrackPlayerBase::init) and `bl 0x3cac0` at 0x21170 (AudioTrack C1).
- `IEngine_CreateAudioPlayer` does not contain a direct `bl` to any of the six target PLT stubs.

So the direct edges are IEngine_CreateAudioPlayer → android_audioPlayer_create → TrackPlayerBase C1Ev. `android_audioPlayer_realize` is reached from this path only if a direct bl from `android_audioPlayer_create` or `IEngine_CreateAudioPlayer` to 0x207b4 exists. That was not found: no bl to 0x207b4 was observed in either function body. Its caller is therefore UNKNOWN.

Function-pointer check: a search for 0x207b4 and 0x20378 as 8-byte values in libwilhelm.so found none. The value 0x34e58 (IEngine_CreateAudioPlayer) appears once, at file offset 0x43278. No relocation covers 0x43278, and the debug table has no data symbol there. Its role is UNKNOWN.

## 7. TrackPlayerBase::init in libaudioclient.so

- Symbol: `_ZN7android15TrackPlayerBase4initERKNS_2spINS_10AudioTrackEEE...` at 0x756ec.
- Bounded at the next symbol (0x75ce8). The bounded range contains 34 bl/blr/br instructions.
- Distinct call targets (direct bl):
  - `PlayerBase::init(player_type_t, audio_usage_t, audio_session_t)` (base init)
  - `AudioTrack::setPlayerIId(int)`
  - `AudioTrack::addAudioDeviceCallback(sp<AudioDeviceCallback>)`
  - std::mutex lock/unlock, RefBase inc/decStrong, sp_report_race, operator new, RefBase ctor/dtor, `__cfi_slowpath`, `__stack_chk_fail`
  - local self-calls to `TrackPlayerBase::init+0x390` (0x75a7c) and `+0x4ac` (0x75b98)
- Indirect call: one `blr x9` at 0x76248 lies outside the bounded range (0x75ce8 onward was not checked), so it is not attributed to init.
- No `AudioTrack::AudioTrack` constructor call appears in the bounded range.

Conclusion: `TrackPlayerBase::init` initializes state and attaches to an AudioTrack that it receives (the `sp<AudioTrack>` argument). It does not create an AudioTrack. The call edge `TrackPlayerBase::init` → `AudioTrack` C1 is not present in the bounded range.

## 8. Construction vtable

`_ZTCN7android15TrackPlayerBaseE0_NS_10PlayerBaseE` is at 0x7e978 in libaudioclient.so (D, data). The exported vtable `_ZTVN7android15TrackPlayerBaseE` is at 0x7e7b8. Support for the inheritance relationship remains SUPPORTED (not VERIFIED), as stated in the earlier follow-up. Raw data references to 0x7e978 were not found in dyn relocations, so the construction vtable is not proven to be used directly.

## 9. Log-string reconciliation

Earlier reports said `TrackPlayerBase::TrackPlayerBase` was absent from all pulled libraries. This is **corrected**.

| Library | "TrackPlayerBase::TrackPlayerBase" count | "PlayerBase::PlayerBase" count |
|---|---|---|
| libaudioclient.so | 1 | 0 |
| libaudiobase.so | 0 | 1 |
| libwilhelm.so | 0 | 0 |
| libaudioflinger_datapath/fastpath/timing/utils.so | 0 | 0 |
| libOpenSLES.so | 0 | 0 |

These are string matches (`grep -a -c`) and do not prove a call edge.

## 10. Answers to the five questions

(a) Functions in libwilhelm.so that reference the TrackPlayerBase constructor (C1Ev, GOT 0x441b0, PLT 0x3c920): `android_audioPlayer_create` at 0x20378 (bl at 0x203cc). **VERIFIED** (direct bl). Its caller `IEngine_CreateAudioPlayer` reaches it through a direct bl at 0x350dc. **VERIFIED**.

(b) Functions referencing TrackPlayerBase::init (GOT 0x441c0, PLT 0x3c940): `android_audioPlayer_realize` at 0x207b4 (bl at 0x21348). **VERIFIED**. No other bl to 0x3c940 found in libwilhelm.so.

(c) Functions referencing AudioTrack constructors (GOT 0x44280, PLT 0x3cac0): `android_audioPlayer_realize` at 0x207b4 (bl at 0x21170). **VERIFIED**. No other bl to 0x3cac0 found.

(d) Whether TrackPlayerBase::init creates or only initializes an AudioTrack: **initializes**. No AudioTrack constructor call exists in the bounded init range (0x756ec–0x75ce8). Init calls `AudioTrack::setPlayerIId` and `addAudioDeviceCallback` on an existing track. **VERIFIED** for the bounded range. Indirect calls outside the bound were not analyzed; **UNKNOWN** for any full call graph.

(e) Whether any function can be reliably identified as the OpenSL ES player creation function: **Yes, partially.** `_ZL25IEngine_CreateAudioPlayer...` (0x34e58) is the local-symbol entry point for OpenSL ES `CreateAudioPlayer`, and it directly calls `android_audioPlayer_create` (VERIFIED by bl and debug name). It is **not a dynamic export**, so it cannot be imported by name. Whether the engine's dispatch table actually routes to it at runtime is **UNKNOWN** (pointer at 0x43278 has no relocation and no named owner).

## 11. Limitations

- Relocations listed only for `.rela.plt`. `.rela.dyn` and `.relr.dyn` (including the 0x43278 pointer) were not decoded.
- Caller names come from `.gnu_debugdata`, not from dynamic exports. They are debug names for a build of the same hash.
- No direct bl to 0x207b4 (`android_audioPlayer_realize`) was found in `android_audioPlayer_create` or `IEngine_CreateAudioPlayer`. Its caller is UNKNOWN.
- `TrackPlayerBase::init` was analyzed only to 0x75ce8. A `blr x9` at 0x76248 lies outside that bound and was not classified.
- Runtime behavior (which path runs during Phigros playback) was not observed. This is static analysis only.
- Function boundaries use the next debug symbol, which assumes no unnamed functions between symbols.

## 12. Commands (summary)

- Relocations: `llvm-objdump -R libwilhelm.so`
- PLT: `llvm-objdump -d --section=.plt libwilhelm.so`
- Text: `llvm-objdump -d --section=.text libwilhelm.so`
- Debug section: Python section reader, then `xz -d`; symbols via `llvm-nm -n`
- Init: `llvm-objdump -d --start-address=0x756ec --stop-address=0x75ce8 libaudioclient.so`
- Log strings: `grep -a -c "<string>" <file>`
- Hashes: `shasum -a 256` on scratch copies; `sha256sum` on device

## 13. Conclusion

The OpenSL ES creation chain in libwilhelm is verified as far as `IEngine_CreateAudioPlayer` (local name) → `android_audioPlayer_create` → TrackPlayerBase C1Ev, and `android_audioPlayer_realize` → TrackPlayerBase::init and AudioTrack C1. `TrackPlayerBase::init` is verified to initialize rather than create an AudioTrack. The link from `IEngine_CreateAudioPlayer` to `android_audioPlayer_realize` is UNKNOWN. The earlier claim that libwilhelm exports `IEngine_CreateAudioPlayer` is incorrect and is retracted. The earlier log-string absence claim for TrackPlayerBase is corrected.
