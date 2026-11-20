"""Lifecycle-aware NF diagnosis of an event stream.

Pointer lifecycle = interval from a DOWN to the next UP for the same pointer id.
Each path segment is assigned to exactly one lifecycle, so ID reuse cannot merge
two lifecycles. Each (lifecycle, sampled time) is counted once.
"""
import os
import sys
from collections import Counter, defaultdict

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, REPO)

from algo.algo_base import TouchAction  # noqa: E402
from block_area import margin_at  # noqa: E402

ACTION_ORDER = {TouchAction.UP: 0, TouchAction.DOWN: 1, TouchAction.MOVE: 2}


def lifecycles(events):
    """Split per-pointer event streams into lifecycles at DOWN / UP boundaries.

    Same-timestamp order: UP before DOWN, MOVE last, so a release and reuse at the
    same ms are not merged into one lifecycle.
    """
    flat = []
    for t, evs in events.items():
        for ev in evs:
            flat.append((t, ev))
    flat.sort(key=lambda x: (x[0], ACTION_ORDER[x[1].action], x[1].pointer))

    open_lc = {}  # pointer -> list of (t, action, pos)
    done = []
    lc_id = 0
    for t, ev in flat:
        pid = ev.pointer
        if ev.action == TouchAction.DOWN:
            if pid in open_lc:
                done.append((lc_id, pid, open_lc.pop(pid)))
                lc_id += 1
            open_lc[pid] = [(t, ev.action, ev.pos)]
        elif ev.action == TouchAction.MOVE:
            if pid in open_lc:
                open_lc[pid].append((t, ev.action, ev.pos))
        elif ev.action == TouchAction.UP:
            if pid in open_lc:
                open_lc[pid].append((t, ev.action, ev.pos))
                done.append((lc_id, pid, open_lc.pop(pid)))
                lc_id += 1
    for pid, seq in open_lc.items():
        done.append((lc_id, pid, seq))
        lc_id += 1
    return done


def diagnose(blocks, events, step_ms=1):
    """Return event-point and interpolated-segment NF records, each sampled time counted once."""
    records = []
    for lc_id, pid, seq in lifecycles(events):
        # Event points
        for t, action, pos in seq:
            if blocks.blocked(pos[0], pos[1], t / 1000, margin_at(t / 1000)):
                records.append(dict(lifecycle=lc_id, pointer=pid, kind='EVENT',
                                    action=action.name, time_ms=t, x=pos[0], y=pos[1],
                                    seg_start=t, seg_end=t))
        # Interpolated segments inside the same lifecycle only
        for (t0, _, p0), (t1, _, p1) in zip(seq, seq[1:]):
            if t1 <= t0:
                continue
            seen = set()
            for tt in range(t0 + step_ms, t1, step_ms):
                k = (tt - t0) / (t1 - t0)
                x = p0[0] + (p1[0] - p0[0]) * k
                y = p0[1] + (p1[1] - p0[1]) * k
                if tt in seen:
                    continue
                seen.add(tt)
                if blocks.blocked(x, y, tt / 1000, margin_at(tt / 1000)):
                    records.append(dict(lifecycle=lc_id, pointer=pid, kind='SEGMENT',
                                        action='', time_ms=tt, x=x, y=y,
                                        seg_start=t0, seg_end=t1))
    return records


def summarize(records):
    by_kind = Counter(r['kind'] for r in records)
    by_lc = Counter(r['lifecycle'] for r in records)
    return dict(total=len(records), by_kind=dict(by_kind), lifecycles_with_violation=len(by_lc))
