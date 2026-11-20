# Task B: Pointer Trajectory Analysis

Source: `captures/algo3_desultory_at_events.csv` in the Round 1 folder, read-only. Times are in ms.

## Longest runs

- Pointer 1000: 149 consecutive events from 64159 to 65343 ms. One DOWN followed by 148 MOVE. This is the longest single run.
- Pointer 1005: 149 MOVE events over the same time, 64162 to 65346 ms. The two pointers move in parallel, offset by about 3 ms.
- Pointers 1000 and 1001: 120-event MOVE runs at 85776 to 86728 ms.
- Pointer 1001: a 39-event MOVE run at 85168 to 85472 ms.

## Violation counts by pointer

| Pointer | Violations |
|---|---|
| 1000 | 455 |
| 1001 | 273 |
| 1005 | 149 |
| 1002 | 10 |
| 1003 | 8 |
| 1004 | 1 |

## Interpretation

- The 149-event run on pointer 1000 is one continuous drag rather than a series of separate presses. Its violations cluster inside NF 69, which fits the full-screen window in Task A.
- Pointer 1005 mirrors 1000 for the same duration. This suggests the allocator assigned a second pointer to the same drag, not two independent gestures. This is an inference from timing and is not confirmed by the allocator's internal state.
- Ownership transitions were read from the event rows. The capture does not record which `_down` or `allocate` branch produced each MOVE, so the origin of each MOVE is taken from the Round 1 attribution, not re-derived here.

## Limits

- The capture gives positions and actions only. It does not record the planner's target position or the reason for each move.
