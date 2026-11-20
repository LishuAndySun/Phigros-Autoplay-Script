# Task D: Skipped Note Analysis

Source: [NF_Skipped_Note_Analysis.csv](NF_Skipped_Note_Analysis.csv), produced by [scripts/skipped_note_analysis.py](scripts/skipped_note_analysis.py).

## Fix to the matching step

The first run matched only 47 of 54 skipped notes to a judge line. The lookup did not mirror `solve()`. Production emits a HOLD as a TAP at the same time, and it schedules a FLICK at `ms - 50`. After correcting the keys, all 54 notes match a judge line. The earlier 47 figure is superseded.

## Classification (54 notes)

| Note type | Production reason | Count | Coarse search found valid point |
|---|---|---|---|
| TAP (1) | NO_VALID_POSITION | 16 | No |
| TAP (1) | RELOCATION_LIMIT_EXCEEDED | 34 | Yes, all 34 |
| FLICK (4) | NO_VALID_POSITION | 3 | No |
| FLICK (4) | RELOCATION_LIMIT_EXCEEDED | 1 | Yes |

## Distance check

- All 35 valid points found by the coarse search lie between 204 and 566 px from the original target (median 252 px).
- The production limit is 200 px. So every RELOCATION_LIMIT_EXCEEDED note has a valid point, but only beyond the allowed relocation, which is consistent with production's reason.
- None of the 19 NO_VALID_POSITION notes has a valid point in the coarse search. This is consistent with production.
- Raw positions: 31 of the 54 raw target points lie inside NF at margin 30.

## Limits

- The search uses an 8 px grid and a 300 ms window at 5 ms sampling. A "no valid point" result is grid evidence, not proof that no point exists.
- The `valid()` check in the script uses the same margin and minimum distance as production. It does not reproduce the production code path exactly.
