# First Audio Peak Sub-Block Audit

Scope: read-only audit of the existing AudioPlaybackCapture probe (com.phiaps.capprobe, UID 10156) data around the candidate FIRST_AUDIO_PEAK at 09:59:45.346. No detector was implemented. No PCM or timestamps were fabricated.

## 1. Constraints

- Read-only analysis of existing logs and source.
- Derived outputs written only to a new directory: $HOME/AudioCaptureProbe/audit_first_peak_20261115_1007/ (outside the repo).
- Claims are labeled VERIFIED, SUPPORTED, HYPOTHESIS, or UNKNOWN.

## 2. Evidence Inventory

| Item | Path | SHA-256 | Status |
|---|---|---|---|
| Preserved logcat snapshot | $HOME/AudioCaptureProbe/logs/preserved_before_gameplay_20261115_095834.txt | fd92e61b39955dfc507cf9ab52fec85f12f26c85d78aa30eb52cdb079f86a889 | VERIFIED. Covers 2542 blk lines, last at 09:58:35.266 (blk=2541). Does not contain the gameplay window. |
| Live logcat dump (`logcat -d -s CapProbe:V`) | audit_first_peak_20261115_1007/capprobe_live_logcat_dump.txt | 13a6418eb752312badd96729b38c4da8099413d34c184aeb825dec02ac31a138 | VERIFIED. 7463 blk lines, all with samples=9600. Contains the candidate window. |
| Screenshots (phase_e_screen*.png) | $HOME/AudioCaptureProbe/logs/ | Not computed | Not used as timing evidence. |

Note: the preserved snapshot ends before gameplay, so it cannot cross-check the live dump. The live dump's start point is not verified against the session start.

## 3. Raw PCM Availability

- VERIFIED: no .pcm, .wav, or .raw file exists under $HOME/AudioCaptureProbe or the repo.
- VERIFIED: grep for file-write code in the probe's Java sources returns no matches.
- Consequence: sample-level or sub-block analysis (20 ms, 10 ms, 1 ms) is impossible from existing data. Only one RMS/peak value per block is available.

## 4. Block Extraction (09:59:42.3 to 09:59:46.0)

Columns: wall-clock, blk, t_ns (elapsedRealtimeNanos), rms, peak, active.

| Wall clock | blk | t_ns | rms | peak | active |
|---|---|---|---|---|---|
| 09:59:42.743 | 3275 | 2214315813597 | 0.0 | 0 | false |
| 09:59:42.828 | 3276 | 2214401094430 | 8.2 | 68 | true |
| 09:59:42.935 | 3277 | 2214507654389 | 38.7 | 213 | true |
| 09:59:43.041 | 3278 | 2214614274472 | 40.0 | 185 | true |
| 09:59:43.127 | 3279 | 2214700436847 | 427.3 | 4159 | true |
| 09:59:44.642 | 3294 | 2216214773931 | 1678.9 | 6406 | true |
| 09:59:45.048 | 3298 | 2216620843348 | 2348.3 | 8506 | true |
| 09:59:45.132 | 3299 | 2216705240681 | 3372.8 | 14850 | true |
| 09:59:45.239 | 3300 | 2216812521182 | 5585.7 | 25245 | true |
| 09:59:45.346 | 3301 | 2216918730307 | 7833.2 | 30410 | true |
| 09:59:45.430 | 3302 | 2217003455765 | 13948.2 | 31481 | true |
| 09:59:45.538 | 3303 | 2217110844140 | 11660.6 | 29528 | true |
| 09:59:45.943 | 3307 | 2217516083474 | 6443.1 | 23027 | true |

Full window: blk 3271 to 3307 (37 blocks). Block 3301 line (verbatim): `CapProbe: blk=3301 t_ns=2216918730307 samples=9600 rms=7833.2 peak=30410 active=true run=26 frames=15849600`.

## 5. Candidate Identification

- Block 3301 (09:59:45.346) is the first block with peak > 30000 (30410). The preceding block 3300 has peak 25245.
- Block 3302 (09:59:45.430) has the highest RMS in the window (13948.2) and peak 31481.
- The 3301 choice is a criterion chosen for this audit (first peak > 30000). It is not a standard definition. Under a different threshold (e.g., first RMS > 5000, which is block 3300), the candidate moves earlier.
- Classification: SUPPORTED that 3301 is the first block with peak > 30000 in the dump. UNKNOWN whether it is the true first musical onset, because the data is UID-level and cannot separate gameplay from other audio.

## 6. Timestamp Semantics

From CaptureService.java captureLoop() (lines 125 to 130):
- `record.read(buf, 0, buf.length, AudioRecord.READ_BLOCKING)` returns.
- `SystemClock.elapsedRealtimeNanos()` is read immediately after, before the RMS/peak loop.

Classification:
- VERIFIED (code): t_ns is taken after read returns, not before. It marks the read-return time.
- UNKNOWN: its relation to the timestamp of the first sample in the block. The code does not use AudioRecord.getTimestamp() and does not record a read-start time.
- HYPOTHESIS: the block's samples end near t_ns, but this is not verified.

## 7. Sub-Block Resolution

- Nominal block: 9600 samples at 48000 Hz = 100 ms (VERIFIED from the code and log field).
- Measured inter-block spacing of t_ns over the 7462 consecutive pairs: min 64.0 ms, median 106.3 ms, max 1022.6 ms (VERIFIED from the dump).
- Because spacing deviates from 100 ms, t_ns cannot be treated as a fixed 100 ms grid. Block-to-time mapping is therefore non-uniform.
- Resolution supported by the data: one block (about 100 ms nominal, with variable spacing up to about 1 s in gaps).

## 8. Peak Sample

- The peak sample index within block 3301 cannot be identified. Only the block-level maximum absolute value (30410) is recorded.
- UNKNOWN: the sample's offset in the block, its channel (stereo interleaved), and its absolute time.

## 9. Anomalies

- Spacing outliers (max 1022.6 ms) indicate read stalls or scheduling delays. Their effect on block timing is UNKNOWN for this window.
- read errors in the dump: 0 (VERIFIED).

## 10. Classification Summary

| Claim | Class |
|---|---|
| Block 3301 has peak 30410 at t_ns 2216918730307 | VERIFIED |
| No raw PCM exists | VERIFIED |
| t_ns is taken after read returns | VERIFIED (code) |
| Sub-block (20 ms, 10 ms, 1 ms) position is determinable | UNKNOWN (not supported by data) |
| Block 3301 is the true first musical onset | UNKNOWN |
| Block spacing is 100 ms | Refuted: median 106.3 ms, outliers to 1022.6 ms |

## 11. Answers to Final Questions

1. Position of first significant peak: not more precise than one 100 ms block. The candidate is block 3301 at t_ns 2216918730307. Within-block position is UNKNOWN.
2. Peak sample identification: not possible. Only the block maximum (30410) is recorded.
3. Timestamp semantics: VERIFIED that t_ns is post-read. The mapping to first-sample time is UNKNOWN. Do not treat it as the sample time of the peak.
4. Practical window: 100 ms is the only window the data supports. 20 ms and 10 ms require new data.
5. Required next experiment: capture raw PCM with a per-sample index and read-start timestamp, and correlate with AudioRecord.getTimestamp(). This is a new experiment and has not been implemented.

No real-time detector was implemented. Another experiment is required to resolve sub-block timing.
