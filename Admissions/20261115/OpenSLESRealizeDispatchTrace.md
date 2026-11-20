# OpenSL ES Realize Dispatch Trace

Read-only static analysis. No PhiAPS source or experiment data was modified. No APK or Phigros native library was inspected. No experiments were run and no packages were installed. The emulator was not started and ADB was not used. AOSP main was not used as evidence.

## Inputs

- Library: `libwilhelm.so` from the Android 17 (API 37) scratch copy at `$TMPDIR/android17_libs/libwilhelm.so`.
- SHA-256 prefix checked this turn: `9a630485f4e8e13e`. The full digest was checked in the prior turn and matched the recorded value.
- Companion libraries were hash-checked in the prior turn: `libaudioclient.so`, `libOpenSLES.so`, `libaudiobase.so`.
- Output path `Admissions/OpenSLESRealizeDispatchTrace.md` was confirmed absent before this report was written.

## Library facts

- `.symtab` is absent. `llvm-nm` returns no symbols.
- `.gnu_debugdata` was decompressed to `/tmp/wil_debugdata.elf`. It is used only as a labeling aid, not as proof of function boundaries.
- `.relr.dyn` decodes to 757 targets. `.rela.dyn` (APS2) decodes to 359 entries, matching the declared count, with the end position equal to the section end.
- `.data.rel.ro` covers 0x40000–0x43c68.

## Task A: Function at 0x310dc

Disassembly, 0x310dc–0x310e4:

```
310dc: b 0x207b4
310e0: mov w0, wzr
310e4: ret
```

- The instruction at 0x310dc is a single unconditional branch to 0x207b4. The preceding `ret` at 0x310d8 ends the previous function.
- Debug-table symbol `_Z20CAudioPlayer_RealizePvj` covers 0x310dc with size 0x4 (end 0x310e0). The next debug symbol, `_Z19CAudioPlayer_ResumePvj`, starts at 0x310e0.
- The debug table is not part of the stripped library's loadable tables. Its boundaries are SUPPORTED only; they are not independently verified against a symbol table.
- 0x207b4 is labeled `_Z27android_audioPlayer_realizeP19CAudioPlayer_structj` (size 0xe54) in the debug table. This is a label, not evidence of the interface.

Verdict for Q1 (what is at 0x310dc): VERIFIED that the instruction is a single-instruction tail jump to 0x207b4. SUPPORTED that the block is a 4-byte wrapper with debug name `CAudioPlayer_Realize`. UNKNOWN that the name is authoritative.

## Task B: Slot 0x41fc0 and its readers

RELR neighborhood (index 390 of 757):

| Slot | Value | Note |
|---|---|---|
| 0x41f78 | 0x313c4 | |
| 0x41f80 | 0x313cc | |
| 0x41f88 | 0x31560 | |
| 0x41f90 | 0xf440 | not a function-pointer-like target |
| 0x41fa0 | 0xfa8b | |
| 0x41fa8 | 0xa099 | |
| 0x41fc0 | 0x310dc | target of this trace |
| 0x41fc8 | 0x310e0 | |
| 0x41fd0 | 0x310e8 | |
| 0x41fd8 | 0x31114 | |
| 0x41fe0 | 0xf4b8 | |

The run is non-uniform. Values such as 0xf440 and 0xa099 are not clearly function entries. RELR-stored values are therefore not treated as proof that this is a dispatch table.

Reader search:
- ADRP-pair scan over `/tmp/wil_text_full.s` with a 4-instruction window. 112 ADRP-pair references were found into pages 0x40000–0x43000. None resolves into 0x41f80–0x42020.
- Literal `ldr` search: 0 literal loads into 0x41f80–0x42020.
- A second pass computed effective addresses for all 78 ADRP consumers in pages 0x40000–0x41000. None falls in 0x41f00–0x42100.

Verdict for Q2 (who invokes the entry at 0x41fc0): UNKNOWN. No static reader was found. The slot may be filled at runtime, reached through a base register whose address is built outside the 4-instruction window, or unused in this build. These possibilities are not distinguished by this analysis.

## Task C: Comparison with slot 0x43278

- Slot 0x43278 holds 0x34e58 (RELR, verified in the prior turn).
- The ADRP scan found 0 references into 0x43260–0x43290.
- Neighborhood values (0x34b90, 0x34e10, 0x34e34, 0x34e58, 0x35158, 0x35370, 0x35394) do not match the 0x41fc0 run. Neither table is assumed to be the same table.

Verdict for Q3 (whether the 0x41fc0 table is the same mechanism as 0x43278): UNKNOWN.

## Task D: Direct branches and indirect calls

- Direct `b` to 0x207b4: one site, at 0x310dc (VERIFIED in the prior turn).
- Direct `bl` to 0x207b4: none found (prior turn).
- Direct `bl`/`b` to 0x310dc, 0x310e0, 0x310e8, 0x31114: none found in the grep of `/tmp/wil_text_full.s` this turn.
- Indirect calls: 218 `blr` sites in `.text`. None was linked to a load from the 0x41fc0 region, because no code addresses that region (see Task B).

Verdict for Q4 (whether a verified indirect path reaches 0x310dc through 0x41fc0): UNKNOWN.

## Task E: Verdicts

1. What is at 0x310dc? VERIFIED: a single `b 0x207b4` tail jump. SUPPORTED: a 4-byte wrapper labeled `CAudioPlayer_Realize` by the debug table.
2. Who invokes the entry at 0x41fc0? UNKNOWN. No static reader was found.
3. Does 0x41fc0 represent the OpenSL ES Realize interface? HYPOTHESIS. The debug label `CAudioPlayer_Realize` and the 0x207b4 label suggest it, but symbol names are not sufficient evidence. No reader or interface table layout was found to confirm it.
4. Is there a verified indirect dispatch path through 0x41fc0 to 0x310dc? UNKNOWN.
5. Is there a verified path from CreateAudioPlayer to Realize (0x207b4)? UNKNOWN. The verified chain is CreateAudioPlayer to `android_audioPlayer_create` to TrackPlayerBase (prior reports). No verified path to 0x207b4 was found. The only direct branch to 0x207b4 is the wrapper at 0x310dc, which has no verified caller.
6. Does gameplay execute Realize? UNKNOWN. This static analysis does not cover runtime behavior, and no runtime evidence was collected.

## Limitations

- `libwilhelm.so` is stripped. Function boundaries rely on the decompressed debug table, which is not authoritative.
- The reader search is limited to ADRP-pair and literal forms within a 4-instruction window. Computed or multi-step address formation may be missed.
- RELR and APS2 decoding were validated against declared counts and section ends. Other relocation types were not analyzed.
- No runtime tracing was performed. A verified dispatch chain requires runtime or additional structural evidence.
- The scratch decoder `decode_relocs.py` fails with an IndexError on this APS2 table and was not used.
