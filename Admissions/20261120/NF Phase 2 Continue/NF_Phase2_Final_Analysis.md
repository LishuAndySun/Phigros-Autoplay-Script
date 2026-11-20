# Task F: Phase 2 Final Analysis

Evidence tiers: CONFIRMED (directly reproduced from source or data), STRONGLY SUPPORTED (multiple consistent lines of evidence, not directly reproduced), SUSPECTED (plausible, not tested), UNKNOWN (not answerable from current evidence).

## Note on the question list

The 11 questions from the continuation spec are not stored in the continuation folder. This report answers the questions implied by Tasks A to E. If the original 11 are provided, this table should be re-mapped to them.

## Findings

| # | Question | Tier | Answer |
|---|---|---|---|
| 1 | Where do NF violations concentrate in time? | CONFIRMED | Task A: NF 69 (2.0 s full screen, first violation 0.6 ms), NF 71/74 (23.5 s window, violations 9 to 14 s in). |
| 2 | Are violations mainly at endpoints or in transit? | CONFIRMED (approximate) | Task C: 882 of 910 margin-0 segments have an endpoint in NF. 28 are interior-only. |
| 3 | Do long pointer runs cause the violations? | STRONGLY SUPPORTED | Task B: pointer 1000 has a 149-event run that overlaps NF 69. Causation not isolated. |
| 4 | Is a second pointer running in parallel? | CONFIRMED | Pointer 1005 has 149 MOVEs at the same time as pointer 1000's run. |
| 5 | Why are notes skipped? | CONFIRMED (grid evidence) | Task D: 34 TAP and 1 FLICK are RELOCATION_LIMIT_EXCEEDED, with valid points 204 to 566 px away. 16 TAP and 3 FLICK are NO_VALID_POSITION, with no valid point found. |
| 6 | Does the production search use the judge line normal? | CONFIRMED | `_tap` passes no normal, so it defaults to (0, 1). `find_clear_flick` takes no normal. |
| 7 | Can the normal be derived from production code? | CONFIRMED | $N = (-\sin a, \cos a)$ with $a = -\text{angle}\cdot\pi/180$. Perpendicular check passes. |
| 8 | Would a normal-first search change outcomes? | UNKNOWN | Not tested. No tolerance was defined, and no simulation was run. |
| 9 | Does the 200 px relocation limit explain the skips? | STRONGLY SUPPORTED | All 35 valid points are beyond 200 px. The 19 NO_VALID cases have no valid point at all. |
| 10 | Is the 8 px grid sufficient to prove no valid point? | UNKNOWN | It is evidence, not proof. Proof would need an exhaustive or analytic search. |
| 11 | Is production unchanged? | CONFIRMED | Hashes match Round 1 records. Git HEAD unchanged. See the audit. |

## Corrections made this session

- Task D matching was fixed. The first run's 47 matches were wrong; all 54 now match (HOLD mapped to TAP, FLICK at ms minus 50). This changes the earlier 47 figure.
- Task E's open item on flick normal direction is resolved: `find_clear_flick` has no normal parameter.

## Not established

- Whether violations are caused by the search ordering, the relocation limit, or pointer reuse. The evidence supports correlation with long runs and the relocation limit, not a single cause.
- Any production fix. None was attempted, per the request.
