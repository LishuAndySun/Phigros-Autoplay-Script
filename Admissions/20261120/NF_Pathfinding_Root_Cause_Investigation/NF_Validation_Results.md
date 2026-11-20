# NF Validation Results (DesultorySignals AT)

## Chart
- File: `Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json`
- SHA-256: `c9807022245ac1ae9299760422518d124dcffbdbbef448a0c4ade515265b517c`
- Size: 13,096,106 bytes; 160 blockAreas; 24 judge lines. Loads via `Chart.from_dict`.

## Capture
- `scripts/capture_algo3_desultory_at.py` runs unmodified `solve()`.
- 17,308 events; 11,894 distinct timestamps; 54 skipped notes (type 1: 34 RELOCATION_LIMIT_EXCEEDED, 16 NO_VALID_POSITION; type 4: 3 NO_VALID_POSITION, 1 RELOCATION_LIMIT_EXCEEDED).
- Runtime 23.94 s.

## Independent validator
- `scripts/validate_nf_independent.py` imports no production modules.
- Method: for each event, test membership in any NF block active at `t` with `inside(b, x, y, t, margin)`.
- Results: margin 0 → 896 violations (DOWN 14, MOVE 867, UP 15). Margin 30 → 1261 violations (DOWN 14, MOVE 1229, UP 18).

## Production cross-check
- `scripts/crosscheck_nf_production.py` compares `BlockAreas.blocked` against the independent check for every event.
- Margin 0: 17,308 agree, 0 disagree. Margin 30: 17,308 agree, 0 disagree.
- Output: `captures/nf_crosscheck_summary.json`.

## Attribution
- `scripts/attribute_algo3_events.py` wraps the same run in memory. Output identical to the capture (True).
- Joins use the key (timestamp, pointer, action, x, y). A zip join was rejected: it misaligned 10,454 rows.
- 17,308 joined, 0 missing, 0 duplicate keys.

## Dataset
- `NF_Violation_Dataset.csv`: 896 rows at margin 0 plus header.
- Built by `scripts/build_violation_dataset.py`; stats in `captures/nf_violation_stats.json`.

## Limits
- The independent validator and production share the same coordinate convention (NF y up, `(x, 720-y)`) and the same margin definition. A convention error would affect both equally; the cross-check does not detect it.
- The margin gap (896 at m0 vs 1261 at m30) is the margin-30 band around NF edges; the production check agrees at both margins.
- No device acknowledgement exists for touch packets; device-side effect is UNKNOWN.
