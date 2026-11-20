# Task C: Continuous Trajectory Analysis (approximate)

Source: [NF_Continuous_Segment_Check_TaskC.csv](NF_Continuous_Segment_Check_TaskC.csv), produced by [scripts/continuous_segment_check.py](scripts/continuous_segment_check.py).

Method: consecutive captured events are joined by straight-line interpolation. This is an approximation of the real touch path. Sampling is at 5 ms steps. Endpoints are checked at margin 0 and margin 30. Segments are checked for interior hits.

## Counts

| Measure | Count |
|---|---|
| Segments with an interior NF hit at margin 30 | 1,282 |
| Segments with an interior NF hit at margin 0 | 910 |
| Segment endpoints inside NF at margin 0 | 882 |
| Segments that hit NF between two clear endpoints | 28 |

## Interpretation

- Most of the violations are endpoint violations (882 of 910). The planner placed a point inside NF, not one that crossed the region in transit.
- The 28 interior-only hits are the cases where both endpoints were clear and the straight line still crossed NF. These are the only cases where a path-level check beyond endpoints changes the verdict. They are approximate because the real path may curve.
- Margin 30 gives more hits than margin 0, as expected.

## Limits

- This is a linear approximation. It is not proof of the real touch path, and the 5 ms sampling is a finite check. Treat the counts as evidence, not proof.
