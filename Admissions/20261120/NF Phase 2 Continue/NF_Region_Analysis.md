# Task A: NF Region Analysis

Source: [NF_Region_Summary_TaskA.csv](NF_Region_Summary_TaskA.csv), produced by [scripts/region_analysis.py](scripts/region_analysis.py).
Coordinates: screen space, x in [0,1280], y in [0,720], y down.

| NF | Window (s) | Half w x h (px) | Center (screen) | Violation events | First violation offset | Last violation to disable (ms) | Pointers |
|---|---|---|---|---|---|---|---|
| 69 | 64.158 - 66.163 (2004.9 ms) | 640 x 720 (full screen) | (640, 360) | 299 | 0.6 ms | 817.4 | 1000, 1004, 1005 |
| 159 | 85.545 - 88.292 (2747.5 ms) | 27.18 x 359.42 (vertical strip) | (638.67, 360.58) | 236 | 231.4 ms | 52.1 | 1000, 1001 |
| 71 | 65.644 - 89.109 (23465.4 ms) | 192 x 180 | (256, 504) | 101 | 9207.4 ms | 2380.9 | 1000, 1001 |
| 74 | 65.644 - 89.109 (23465.4 ms) | 192 x 180 | (1024, 504) | 92 | 14257.4 ms | 2380.9 | 1000, 1001 |
| 45 | 11.881 - 12.178 (297.0 ms) | 704 x 72 | (576, 720) | 74 | 7.8 ms | 1.2 | 1000, 1001 |
| 4 | 10.405 - 10.656 (250.6 ms) | 704 x 72 | (576, 720) | 62 | 3.7 ms | 6.9 | 1000, 1001 |

## Observations

- NF 69 covers the full screen for about 2.0 s. Its first violation occurs 0.6 ms after it becomes active, so the planner was already inside the region when it was enabled. This is the strongest single case.
- NF 159 is a narrow vertical strip (half width 27 px). Violations start 231 ms in, which is consistent with a pointer that enters the strip during its window.
- NF 71 and NF 74 share a window of 23.5 s. Their violations start 9 s and 14 s in, so they are long-lived windows where the planner drifted in gradually rather than failing at once.
- NF 45 and NF 4 are short horizontal bands at the bottom edge. Their first violations come within 8 ms of activation.

## Limits

- Regions are taken from the chart's enable and disable times. Geometry comes from the validator's `load_blocks`, not production code. Results describe the chart, not a proof about every run.
- "Last violation to disable" measures time left after the last violation. It does not show whether the planner tried to exit.
