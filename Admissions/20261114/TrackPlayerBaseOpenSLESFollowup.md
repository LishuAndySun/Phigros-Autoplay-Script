# TrackPlayerBase Identity and OpenSL ES Path: Follow-up Audit

Scope: read-only. No PhiAPS source, experiment data, or session exports were modified. The experiment was not rerun. The emulator was not restarted or reconfigured. No APK analysis was performed.

Evidence tags:
- DEVICE: read from emulator-5554 with the device's own `readelf`, `sha256sum`, `stat`.
- LOCAL: read from scratch copies in `$TMPDIR/android17_libs/` on the Mac (copies pulled from the device; sha256 matched the device for every file checked).
- SOURCE: public Android source. No new source was fetched for this report. The earlier AudioTrack.cpp fetch was `refs/heads/main`, not a build revision, and is not used as evidence here.

## 0. Correction to the previous report

The previous report stated that `libwilhelm.so` exports `IEngine_CreateAudioPlayer`. This is wrong.
- DEVICE: `readelf --dyn-syms -W /system/lib64/libwilhelm.so | grep -E "slCreateEngine|IEngine|CreateAudioPlayer"` returned no lines.
- LOCAL: `grep -a -b -o IEngine_CreateAudioPlayer libwilhelm.so` finds two byte offsets (51199 and 53752). The name is present as a string (likely a debug or log string or a symbol-name table), not as a dynamic export.
- Consequence: the OpenSL ES entry point is not established as a dynamic export in this library.

## 1. ELF build identity (Task 1)

Command used for build IDs (device): `adb -s emulator-5554 shell "readelf -n <path>"`
Command used for hashes and sizes (device): `adb -s emulator-5554 shell "sha256sum <path>; stat -c %s <path>"`

| Device path | Size (bytes) | GNU Build ID | SHA-256 | Source |
|---|---|---|---|---|
| /system/lib64/libwilhelm.so | 307672 | b2b8be766a0bb4d0a575e3ae640c6275 | 9a630485f4e8e13e94103983f2e9eb0818fd71e5b47df515f8a2c42687b7266b | DEVICE |
| /system/lib64/libaudioflinger_datapath.so | 51872 | 2b4b99e2cf5e8fee45ee3f4189821be7 | 6a1de1587f80f712a03c3dfc6077468e03781a925fcaf63886a79b1bdf703f87 | DEVICE |
| /system/lib64/libaudioflinger_fastpath.so | 85528 | 63c908c1d2cfae83d378dc003ee0964d | c08bfdde566a91b938802f5112177e36b42d70fad2bb29b16a2997e6c259c4c2 | DEVICE |
| /system/lib64/libaudioflinger_timing.so | 35368 | c846e22386f73a26794acc2ec8627ff8 | 89836d166079d4b332c8f9a6b7f3282a85a2fae72952feb45feaca78446e9155 | DEVICE |
| /system/lib64/libaudioflinger_utils.so | 52648 | d55974b0cc4559001e8dfe4424aea036 | b5ea235e691125a878e652e7ae1ff3ea6286f74500d8f4dbe0fe395e5f0906ad | DEVICE |
| /system/lib64/libaudioclient.so | 553160 | d5e03623b0ca530f899f320ba7c9811d | 0189039cd976a25deb1cfed6210932540f07b9719b53958b6671f04841f8bea1 | DEVICE |
| /system/lib64/libOpenSLES.so | 35896 | 4f9b436de4a0a3b0a1f1886a2c6e44d0 | 771ca94c10f7103d0f4e9a966f847d03c83327ac8db6ff2bc528cd36d899bdcc | DEVICE |
| /system/lib64/libaudiobase.so (new) | 676520 | 3b929bf3dc3d990f4709bedc77f808a9 | 633890a33aea6497264fd38a130030bb632b22975171b8b79ab7c9608d0b59fe | DEVICE (sha); LOCAL copy sha matches |

Local-copy hashes (LOCAL) match the device for every file that was hashed locally. The five libaudioflinger modules were hashed on the device; their local copies were not re-hashed in this session.

Limitation: the device `readelf` has no `--relocs` or `-r` option (`readelf: Unknown option`). Relocation records (`.rela.plt`, `.rela.dyn`) could not be listed with it. Host `readelf` is absent. Relocation-level linkage is therefore NOT CHECKED.

## 2. Class identity and inheritance (Task 2)

### 2.1 Where each class is defined

- DEVICE: `readelf --dyn-syms -W /system/lib64/libaudioclient.so`. `_ZN7android10PlayerBaseC2Ev`, `PlayerBaseD2Ev`, `PlayerBase4init...`, and related PlayerBase members are `UND` (imported) in libaudioclient.so.
- DEVICE: `readelf --dyn-syms -W /system/lib64/libaudiobase.so`. These same PlayerBase symbols are defined (section index 15 for code, 17 for vtables). `_ZTVN7android10PlayerBaseE` is defined at 0x99428.
- DEVICE: `readelf -d /system/lib64/libaudioclient.so | grep NEEDED` includes `[libaudiobase.so]`.
- DEVICE: `readelf --dyn-syms -W /system/lib64/libaudioclient.so`. `_ZN7android15TrackPlayerBaseC2Ev` (0x73264), `C1Ev` (0x732d0), `D0Ev`, `D1Ev`, `D2Ev`, `init`, `destroy`, `doDestroy`, and `_ZTVN7android15TrackPlayerBaseE` (0x7e7b8) are all defined (section index 15 or 17).

Conclusion: `PlayerBase` is defined in `libaudiobase.so`. `TrackPlayerBase` is defined in `libaudioclient.so`. The `TrackPlayerBase` definitions are in libaudioclient.so, not in libaudiobase.so.

### 2.2 Typeinfo and construction vtables

- DEVICE: `readelf --dyn-syms -W` on libaudioclient.so and libaudiobase.so, filtered for `_ZTI` and `_ZTS`, returned no PlayerBase or TrackPlayerBase matches.
- DEVICE: `_ZTCN7android15TrackPlayerBaseE0_NS_10PlayerBaseE` is defined in libaudioclient.so at 0x7e978 (section 17).
- DEVICE: other construction vtables for TrackPlayerBase are defined at 0x80898, 0x7db18, 0x7eb38, 0x7ee58, 0x7ecd8, 0x7ef38, and 0x80cd8.

Interpretation:
- The Itanium C++ ABI emits a construction vtable `_ZTC<Derived>0_<Base>` for each base-class subobject of `Derived`. The presence of `_ZTCN7android15TrackPlayerBaseE0_NS_10PlayerBaseE` therefore strongly indicates that TrackPlayerBase has PlayerBase as a base subobject. This is SUPPORTED by ABI convention, not directly proven.
- Typeinfo (`_ZTI`) for either class is not exported. The typeinfo's base-class entry, which would directly prove inheritance, cannot be read from the dynamic table.

Verdict for question 1 (exact inheritance): SUPPORTED that TrackPlayerBase derives from PlayerBase (construction vtable). NOT VERIFIED. The exact inheritance chain and any multiple-inheritance layout beyond the construction vtable are UNKNOWN.

What would prove it: an unstripped copy of libaudioclient.so with `.symtab` or DWARF (only `.gnu_debugdata` is present on device, MiniDebugInfo), or the `_ZTI` typeinfo exported from the device, or disassembly of the TrackPlayerBase constructor showing the base-class vtable store.

Not used as evidence: `libwilhelm.so` referencing PlayerBase methods (`baseUpdateDeviceIds`, `reportEvent`) does not by itself establish inheritance.

## 3. OpenSL ES relationship (Task 3)

### 3.1 What libwilhelm.so imports (DYNAMIC, DEVICE)

Command: `readelf --dyn-syms -W /system/lib64/libwilhelm.so | grep -E "UND.*(PlayerBase|TrackPlayerBase|AudioTrack|createTrack)"`

The `UND` (imported) symbols include:
- `_ZN7android15TrackPlayerBaseC1Ev` (TrackPlayerBase base-complete constructor)
- `_ZN7android15TrackPlayerBase4initERKNS_2spINS_10AudioTrackEEERKNS1_INS2_19IAudioTrackCallbackEEENS_13player_type_tE13audio_usage_t15audio_session_t`
- `_ZN7android15TrackPlayerBase15setPlayerVolumeEff`
- `_ZN7android10PlayerBase19baseUpdateDeviceIdsERKNSt3__16vectorIiNS1_9allocatorIiEEEE`
- `_ZN7android10PlayerBase11reportEventENS_14player_state_tERKNSt3__16vectorIiNS2_9allocatorIiEEEE`
- `_ZN7android10AudioTrackC1E19audio_stream_type_tj14audio_format_t20audio_channel_mask_tm20audio_output_flags_t...` (AudioTrack constructor)
- `gClsAudioTrackRoutingProxy`, `gMidAudioTrackRoutingProxy_ctor`, `gMidAudioTrackRoutingProxy_release` (JNI-related imports)

Nine dynamic symbols match this filter. The library's dynamic symbol table has no `createTrack_l` import.

### 3.2 What libwilhelm.so defines

- DEVICE: `readelf --dyn-syms -W /system/lib64/libwilhelm.so | grep -E "slCreateEngine|IEngine|CreateAudioPlayer"` returned no lines. No OpenSL ES entry point is exported.
- LOCAL: the string `IEngine_CreateAudioPlayer` appears twice in the file (offsets 51199 and 53752). A symbol-table or debug string is likely, but the binding is not established.

### 3.3 Relationship table

| Relationship | Status | Evidence |
|---|---|---|
| libwilhelm imports TrackPlayerBase constructor and init | VERIFIED (import) | DEVICE dynsym UND |
| libwilhelm imports AudioTrack constructor | VERIFIED (import) | DEVICE dynsym UND |
| libwilhelm imports AudioTrack::createTrack_l | NOT FOUND | DEVICE dynsym has no such import |
| libwilhelm's OpenSL entry point calls TrackPlayerBase::init | UNKNOWN | No defined OpenSL export; no relocation or disassembly available |
| libwilhelm uses the import from within IEngine_CreateAudioPlayer | UNKNOWN | Same reason; the calling function is not identified |
| AudioTrack::createTrack_l is reached from TrackPlayerBase::init | UNKNOWN | Needs disassembly or a call graph; not established |
| TrackPlayerBase constructor is called from libwilhelm | SUPPORTED that libwilhelm can call it (imports C1Ev); call site not identified |

Relocations (`.rela.plt`) were not inspected because of the device `readelf` limitation in section 1. The import table shows the names exist, not which code site uses them.

Interpretation: the symbol-level relationship is that libwilhelm.so imports TrackPlayerBase and AudioTrack constructors and TrackPlayerBase::init. A direct call chain from the OpenSL ES entry point to TrackPlayerBase::init or to createTrack_l is NOT established.

## 4. Flag uncertainty (Task 4)

Observed values, unchanged from the raw log:
- flags requested = 0x104
- output = 0x2

No meaning is assigned in this report. The matching-build headers were not located, and no binary evidence in this session establishes the flag bits. The earlier source-level reading of `input.flags = mFlags` came from main, not from this build, and is not used here.

Status: UNKNOWN.

## 5. Evidence classification (Task 5)

1. Is the exact TrackPlayerBase inheritance relationship known?
   - SUPPORTED that TrackPlayerBase derives from PlayerBase (construction vtable `_ZTCN7android15TrackPlayerBaseE0_NS_10PlayerBaseE` in libaudioclient.so). Not VERIFIED. Typeinfo is not exported, so the exact base chain is UNKNOWN.

2. Is the OpenSL ES to TrackPlayerBase::init relationship directly established?
   - NO. libwilhelm.so imports `TrackPlayerBase::init` (DEVICE dynsym UND). No defined OpenSL ES export exists, and no disassembly or relocation evidence links the two. Status: UNKNOWN for the call; the import is VERIFIED.

3. Is the AudioTrack creation path established?
   - PARTIAL. libwilhelm imports `AudioTrack` constructors (VERIFIED import). libaudioclient exports `AudioTrack::createTrack_l` (VERIFIED export). The link from the OpenSL path to `createTrack_l` is UNKNOWN. Flag meanings are UNKNOWN.

4. Is the Phigros-side constructor caller known?
   - NO. The Phigros-side caller is UNKNOWN. This report did not analyze the APK, per the constraints.

5. Can any observed constructor event be used as a gameplay-start signal?
   - NO. The log strings "PlayerBase::PlayerBase" and "TrackPlayerBase::TrackPlayerBase" were not found in any pulled library (libwilhelm, libaudioclient, libaudiobase, libOpenSLES, libaudioflinger modules). The emitter of these log lines is therefore unknown. The constructors exist as symbols, but the events cannot be tied to gameplay start without the caller and emitter. The constructor events are also not timestamped against the game's own frame or scene events. Do not use them as a gameplay-start signal.

## 6. Limitations

- Device `readelf` lacks relocation listing and full symbol tables; only `.gnu_debugdata` (MiniDebugInfo) is present on device for these libraries.
- No host `readelf`, `nm`, or `objdump` gives a complete answer; `nm` on the Mac does not handle these Android ELF binaries for the purpose of this check.
- No disassembly was performed, so no direct call edges are established.
- The Android build revision for `CE2A.260420.051.A3 / 16571990` is still not verified against any public source. Symbols here describe the device build, not a source revision.

## 7. Recommended next steps

1. Obtain relocation data: pull libwilhelm.so and libaudioclient.so and inspect `.rela.plt` with a host ELF tool that supports Android binaries, or use `llvm-readelf` if available. This would show which code sites reference the TrackPlayerBase and AudioTrack imports.
2. Obtain an unstripped libaudioclient.so with `.symtab` or DWARF from the matching build, if one exists, to read the typeinfo base-class entry.
3. Disassemble only the library code around the imports in libwilhelm.so to locate the calling function, if this is acceptable under the constraints.
4. Verify the flag bits against the headers for build `16571990`, not main.
5. Correlate log lines with PIDs and TIDs before attributing any constructor event to a caller.
