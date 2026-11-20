# NF Pathfinding Root Cause Investigation (DesultorySignals AT)

## 1. Executive summary
On the AT chart, Algo3 emits 896 touch events (margin 0) and 1261 events (margin 30) that fall inside active NF regions. The cross-check confirms the independent validator and production `BlockAreas.blocked()` agree on all 17,308 events.

Attribution shows that the violations do not come from the NF-checked placement paths (`_tap`, `_flick`), which produce zero DOWN/MOVE violations. They come from paths that emit positions without any NF check: HOLD/DRAG continuation (`allocate` step 3), DRAG/HOLD onset (`_down` for type 2), and the UP of those pointers.

Root cause (source-confirmed): the NF check exists only in `_tap` and `_flick` placement. HOLD body positions, DRAG `_drag` positions, and `allocate` step 3 continuation MOVEs bypass it. `Frame.add` also clamps positions through `recalc_pos`, which is not NF-aware.

## 2. Chart
- Path: `Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json`
- SHA-256: `c9807022245ac1ae9299760422518d124dcffbdbbef448a0c4ade515265b517c`
- 160 blockAreas, 24 judge lines. No blocker; the chart loaded.

## 3. Execution path
See [NF_Execution_Path.md](NF_Execution_Path.md).

## 4. Violation statistics
- Total events: 17,308.
- Margin 0: 896 violations (MOVE 867, DOWN 14, UP 15).
- Margin 30: 1261 violations (MOVE 1229, DOWN 14, UP 18).
- Per pointer (margin 0): 1000: 455; 1001: 273; 1005: 149; 1002: 10; 1003: 8; 1004: 1.
- Top NF IDs (margin 0): 69 (299), 159 (236), 71 (101), 74 (92), 45 (74), 4 (62).
- Time range: 10,409–139,469 ms; 56 pointer runs; longest run 149 events.
- Full data: [NF_Violation_Dataset.csv](NF_Violation_Dataset.csv).

## 5. Representative traces
- Largest run: pointer 1000, 149 consecutive MOVE events inside NF region, all from `allocate:drag_continuation_or_release`. Use the dataset to extract exact timestamps.
- Only TAP-origin violation: UP at 82763 ms, pointer 1000, `_down:type1`, which closes a HOLD.

## 6. Root-cause classification

| # | Cause | Status | Evidence |
|---|---|---|---|
| RC1 | `allocate` step 3 emits DRAG continuation MOVEs with no NF check | Confirmed | 867 margin-0 MOVE violations, all from this origin |
| RC2 | HOLD branch in `solve` emits DRAG positions via `line.pos_of` with no NF check | Confirmed (source); violations match origin | 14 DOWN + 11 UP from `_down:type2` |
| RC3 | `_drag` calls `_down` and deliberately skips NF | Confirmed (source) | DOWN violations from type 2 |
| RC4 | `Frame.add` → `recalc_pos` is not NF-aware | Confirmed (source); no violations attributed to it in data | UNKNOWN whether it moves any point into NF |
| RC5 | UP at `_release_at` after NF-clean placement | Suspected | 3 UP from `allocate`, 1 from `_down:type1` |
| RC6 | `_tap`/`_flick` NF checks are correct | Confirmed by data | 0 DOWN/MOVE violations from these origins |

## 7. Geometry
The NF test is verified against production and independent code. Coordinate convention (y up, `(x, 720-y)`) is an assumption shared by both implementations and is not independently verified against the game. UNKNOWN whether the convention is correct on device.

## 8. Timing
- `BlockAreas` uses 0.5 s buckets. Interval test uses `enable <= t <= disable`.
- MOVE violations occur at 8 ms drag steps; timing of NF entry versus DRAG onset is UNKNOWN in detail.

## 9. Continuous trajectory
The trajectory is generated per 8 ms (DRAG) and per 1 ms (HOLD) without verifying the segment between samples. A segment could cross an NF region between two checked samples. Not measured in this investigation (UNKNOWN).

## 10. Pointer lifecycle
- `PointerAllocator.alloc` reuses only pointers with `age>0` and pressed_at + 40 ms.
- `_down` inserts UP of the previous note at `_release_at`.
- Violating pointers 1000 and 1001 account for 728 of 896 margin-0 events.

## 11. Validator methodology and results
See [NF_Validation_Results.md](NF_Validation_Results.md). Production vs independent: 17,308 agree at both margins.

## 12. Architecture recommendations (not implemented)
1. Apply the same NF check to HOLD/DRAG positions before emission, or constrain the HOLD path to NF-clear points.
2. Make `recalc_pos` NF-aware, or re-check after clamping.
3. Check the segment between consecutive samples, not only the samples.
4. Add a regression gate that runs the independent validator on every chart with blockAreas.

## 13. Regression plan (for review; not executed as a fix)
- Re-run `capture_algo3_desultory_at.py`, then `validate_nf_independent.py`, then `crosscheck_nf_production.py`.
- Expected: zero margin-0 violations for the AT chart after any fix. Current baseline: 896.
- Do not change the Beta1 baseline or historical records.

## 14. Confirmed vs UNKNOWN
- Confirmed: chart load, event counts, violation counts, origin attribution, production/independent agreement, which paths lack NF checks.
- UNKNOWN: device-side effect of violations; whether the game judges these as misses; whether the margin-30 band reflects the game's real NF edge; whether the coordinate convention matches the device; segment-crossing violations between samples.

## 15. Question list
The 12 questions from the original request were not captured in full in the working summary, so they cannot be answered verbatim here. Answers to the questions that map to the findings above are given in sections 4–10. Please provide the question text to complete this section.

Stopping here for review, as requested. No production source was changed.
