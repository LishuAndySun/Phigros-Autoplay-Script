# Task E: Normal Direction Feasibility

## Source facts (read-only)

- [judge_line.py](../../../judge_line.py#L122): `JudgeLine.angle(t)` returns the rotation in degrees.
- [judge_line.py](../../../judge_line.py#L132): `pos_of(note, t)` offsets the note along `a = -angle * pi / 180` by `note.x * 72`.
- [block_area.py](../../../block_area.py#L38): `judge_line_ends` uses the same `a = -angle * pi / 180`, so the judge line direction is $d = (\cos a, \sin a)$.
- [block_area.py](../../../block_area.py#L172): `search_point` takes `nx_dir`, `ny_dir` and searches along $\pm(n_x, n_y)$ first.

## Derived normal

The normal perpendicular to $d$ is $N = (-\sin a, \cos a)$. Check: $d \cdot N = -\cos a \sin a + \sin a \cos a = 0$.

## Production usage

- [algo/algo3.py](../../../algo/algo3.py#L161): `find_clear_press` defaults to `nx_dir = 0.0`, `ny_dir = 1.0`.
- [algo/algo3.py](../../../algo/algo3.py#L332): the `_tap` call to `find_clear_press` passes `note.line` and `MIN_DIST` but not `nx_dir`/`ny_dir`.
- CORRECTION: this earlier statement was wrong. `_tap` in algo3.py (line 333) passes `(-sin(note.angle), cos(note.angle))`, i.e. the judge-line normal, not (0, 1). The real gap is that the DRAG/HOLD continuation path (`solve` line 465 and `allocate` DRAG branch) has no NF check, and FLICK path sampling uses 5 ms steps.
- The flick path ([algo/algo3.py](../../../algo/algo3.py#L352)) calls `find_clear_flick(blocks, now, note, MIN_DIST)`. Its signature has no `nx_dir`/`ny_dir` parameters, so the flick path cannot receive a normal. It also searches by flick start position, not by normal. This is confirmed by reading the signature.

## Feasibility

- Computing $N$ from `JudgeLine.angle` is straightforward and consistent with the existing convention.
- No tolerance has been invented. A usable search needs the normal to be used with the same `STEP` and `MAX_RELOCATION_DISTANCE` as the existing search, which is not tested here.
- This report is a feasibility check only. No production code was changed.
