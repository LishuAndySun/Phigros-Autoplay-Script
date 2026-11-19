# OpenSL ES Dispatch and Realize Caller Audit

Scope: read-only static analysis of scratch copies in $TMPDIR/android17_libs. No PhiAPS source, session records, experiment data, emulator state, APK, or Phigros native libraries were touched. No AOSP main source was used as evidence.

## Inputs and hashes (verified this turn)

| File | SHA-256 |
|---|---|
| libwilhelm.so | 9a630485f4e8e13e94103983f2e9eb0818fd71e5b47df515f8a2c42687b7266b |
| libaudioclient.so | 0189039cd976a25deb1cfed6210932540f07b9719b53958b6671f04841f8bea1 |
| libOpenSLES.so | 771ca94c10f7103d0f4e9a966f847d03c83327ac8db6ff2bc528cd36d899bdcc |
| libaudiobase.so | 633890a33aea6497264fd38a130030bb632b22975171b8b79ab7c9608d0b59fe |

libmedia.so is not device-verified and is excluded.

## Tooling

- Disassembly: `/Library/Developer/CommandLineTools/usr/bin/llvm-objdump -d --no-show-raw-insn --start-address=0x1c000 --stop-address=0x3c688 libwilhelm.so > /tmp/wil_text_full.s` (33186 instruction lines).
- Section mapping: Python `struct` parse of Elf64_Shdr (name, type, flags, addr, offset, size, ...).
- RELR decode: 2-bit-tagged words, 63-slot bitmaps. 757 targets.
- RELA decode: APS2 with ULEB per-relocation offset delta and SLEB addend. The scratch `decode_relocs.py` fails with IndexError on this file, so it was not used. A separate decoder was validated: 359 entries decoded, matching the declared count, and ending exactly at section end 0x4ef3.

## Q1. Readers of the RELR-relocated pointer at VA 0x43278

- Section: `.data.rel.ro`, addr 0x40000, file offset 0x40000. File offset of 0x43278 = 0x43278 (VERIFIED by section header arithmetic).
- Stored value: 0x34e58, which is `IEngine_CreateAudioPlayer` (prior turn; VERIFIED RELR decode).
- RELR run: 0x43260 -> 0x34b90, 0x43268 -> 0x34e10, 0x43270 -> 0x34e34, **0x43278 -> 0x34e58**, 0x43280 -> 0x35158 (IEngine_CreateAudioRecorder), 0x43288 -> 0x35370, 0x43290 -> 0x35394. Index 574 in the decoded RELR list.
- RELA check: no validated RELA entry has r_offset 0x43278 or addend 0x34e58 (VERIFIED).
- Static readers: ADRP-paired scan with a 4-instruction window over the full .text (0x1c000–0x3c688) found 0 instructions that form 0x43278 (or 0x41fc0). Verdict: **UNKNOWN**. Readers may use indirect addressing that the window misses, or may be accessed from outside libwilhelm.so.
- Dispatch-table status: **UNKNOWN**. The slot is in a run of IEngine/IVolume function pointers, which is consistent with a dispatch table, but no reader was found, so it is not verified as one.

## Q2. Is 0x43278 a verified OpenSL ES dispatch table?

Verdict: **UNKNOWN**. A RELR-stored pointer inside a pointer run is not sufficient evidence. No reader or vtable structure was confirmed.

## Q3. Callers of android_audioPlayer_realize (VA 0x207b4)

- Direct `bl 0x207b4`: none found in the full .text (VERIFIED by grep).
- Direct `b 0x207b4`: one instance, at 0x310dc (`b 0x207b4`, tail jump). It sits in the entry starting at 0x310dc. The debug-table nearest symbol is `_Z20CAudioPlayer_RealizePvj`, but the boundary is not verified, so the name is a hypothesis.
- The entry 0x310dc is pointed to by RELR slot 0x41fc0. The same run contains 0x310e0, 0x310e8, and 0x31114 (VERIFIED RELR values).
- Verdict for the direct callers of realize: VERIFIED that 0x310dc is the only direct branch to 0x207b4. The callers of 0x310dc are **UNKNOWN** (no direct `bl`/`b` found; the table at 0x41fc0 has no reader found).
- Prior-turn direct chains (VERIFIED from earlier disassembly): IEngine_CreateAudioPlayer (0x35xxx area, via 0x350dc) -> android_audioPlayer_create (0x350dc) -> TrackPlayerBase C1 (0x203cc). Realize is not reached from this chain by a direct `bl` in the present scan, so that link is **UNKNOWN**.

## Q4. Targets of the three indirect calls in android_audioPlayer_setPlayState (0x22458)

Call sites (from prior turn, VERIFIED):

| Site | Instruction | Source of pointer | Target |
|---|---|---|---|
| 0x224dc | `blr x9` | `[x8,#296]` loaded from `[sp,#64]` (stored at 0x224a4), guarded by `cbz` at 0x224cc | UNKNOWN |
| 0x22660 | `blr x9` | `[x8,#40]` from object at `[x19,#2632]`; vtable loaded via `ldr x8,[x0]` | UNKNOWN |
| 0x226b4 | `blr x8` | `[x8,#64]` from object at `[x19,#2648]`, preceded by `bl 0x2af5c` at 0x226a4 | UNKNOWN |

- Object provenance (constructor, store, or vtable-pointer evidence): not traced in this turn. Verdict: **UNKNOWN** for all three targets.
- Whether any target invokes an AudioTrack start/pause/stop method: **UNKNOWN**.
- Verified direct calls in setPlayState: `PlayerBase::baseUpdateDeviceIds` (0x226f8), `PlayerBase::reportEvent` (0x22708).
- Verified field stores: `str wzr,[x19,#2616]` at 0x225e4, 0x22640, 0x226a0; `strb w8,[x19,#2672]` at 0x22710.

## Q5. Function containing libaudioclient.so VA 0x76248

- `blr x9` at 0x76248, sequence (VERIFIED from prior turn): 0x76238 `adrp x1,0x81000`; 0x7623c `ldr x9,[x21]`; 0x76240 `add x8,sp,#16`; 0x76244 `ldr x1,[x1,#3512]`; 0x76248 `blr x9`; 0x7624c `ldr x21,[sp,#16]`; 0x76250 `cbz x21,0x762bc`.
- Outside TrackPlayerBase::init (0x756ec–0x75a7c, from .dynsym st_size 0x390), which has no indirect calls (VERIFIED).
- Containing function bounds: **UNKNOWN**. The debug table's nearest symbol is `_ZN7android5media13IEffectClient11asInterfaceERKNS_2spINS_7IBinderEEE.cfi` at 0x761cc, and the next boundary is 0x76514. The `.cfi` alias makes the start unreliable. Not established in this turn.
- Q6 (what the indirect call does): **UNKNOWN**. The vtable source `x21` has not been traced.

## Q6. Reliable gameplay-audio-start signal

Verdict: **UNKNOWN**. No verified start signal was established in this turn. The only verified PlayerBase facts are the direct calls to `baseUpdateDeviceIds` and `reportEvent` in setPlayState, which do not by themselves prove playback started.

## Q7. Summary of verdicts

| Question | Verdict |
|---|---|
| Readers of slot 0x43278 | UNKNOWN |
| 0x43278 is a verified OpenSL ES dispatch table | UNKNOWN |
| Only direct branch to realize (0x207b4) | VERIFIED: 0x310dc (`b`, tail jump) |
| Callers of the 0x310dc entry | UNKNOWN |
| Targets of setPlayState blr sites | UNKNOWN |
| Any target invokes AudioTrack start/pause/stop | UNKNOWN |
| Containing function of 0x76248 | UNKNOWN |
| Reliable gameplay-audio-start signal | UNKNOWN |

## Limitations

- The ADRP scan is static. It cannot see readers that are reached through a register loaded from memory, from another library, or through a function-pointer copy.
- RELR run membership and RELA validation establish that the slots are relocated; they do not establish runtime use.
- Debug-table names (for example `CAudioPlayer_Realize`) are nearest-symbol labels, not verified function boundaries.
- Task C (setPlayState object provenance) and Task D (0x76248 containing-function bounds) were not completed in this turn; their verdicts remain UNKNOWN.
- The scratch `decode_relocs.py` is broken for this APS2 table (IndexError). The results here use a separately validated decoder.
- Observed device behavior was not used; no emulator experiment was run.
