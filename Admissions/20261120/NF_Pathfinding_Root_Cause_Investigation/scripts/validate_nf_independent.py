"""Independent NF validator for the Algo3 DesultorySignals AT capture.

Deliberately does NOT import block_area.py or algo/*. Re-implements the NF rectangle test
from the chart JSON alone, so the result can be compared against the production
BlockArea.contains()/blocked() logic.

Coordinate convention (stated, not inferred from production code):
  screen point (x, y) with x in [0,1280], y in [0,720], y increasing downward (same as TouchEvent.pos).
  NF rectangle is defined in normalized physical coords (y up) from topRight/bottomLeft percentages.
  Conversion used here: ph = (x, 720 - y).

Outputs (in ../captures/):
  nf_independent_event_check.csv  one row per production event, margin 0 and margin 30
  nf_independent_summary.json
"""
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')
CAP = os.path.join(HERE, '..', 'captures')
EVENTS = os.path.join(CAP, 'algo3_desultory_at_events.csv')
SW, SH = 1280.0, 720.0
MARGINS = (0.0, 30.0)


def interp(pts, t, default):
    """piecewise-linear over sorted (time, value-tuple); constant outside range"""
    if not pts:
        return default
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t <= t1:
            if t1 == t0:
                return v1
            k = (t - t0) / (t1 - t0)
            return tuple(a + (b - a) * k for a, b in zip(v0, v1))
    return pts[-1][1]


def load_blocks(raw):
    blocks = []
    for d in raw.get('blockAreaList', []):
        tr, bl = d['topRightPercentage'], d['bottomLeftPercentage']
        hw = (tr['x'] - bl['x']) * SW / 2
        hh = (tr['y'] - bl['y']) * SH / 2
        cx = (tr['x'] + bl['x']) * SW / 2
        cy = (tr['y'] + bl['y']) * SH / 2
        moves = sorted((e['time'], (e['endPosition']['x'] * SW - cx, e['endPosition']['y'] * SH - cy))
                       for e in d.get('moveEvents', []))
        rots = sorted((e['time'], (e['anchor']['x'] * SW, e['anchor']['y'] * SH, e['rotation']))
                      for e in d.get('rotateEvents', []))
        scs = sorted((e['time'], (e['anchor']['x'] * SW, e['anchor']['y'] * SH,
                                  e['scale']['x'], e['scale']['y'])) for e in d.get('scaleEvents', []))
        blocks.append(dict(enable=d['enableTime'], disable=d['disableTime'], subtract=bool(d.get('isSubtract')),
                           hw=hw, hh=hh, cx=cx, cy=cy, moves=moves, rots=rots, scs=scs, idx=len(blocks)))
    return blocks


def inside(b, x, y, t, margin):
    """True if physical point is inside block b at time t (seconds), with margin in px."""
    px, py = x, SH - y
    mx, my = interp(b['moves'], t, (0.0, 0.0))
    px, py = px - mx, py - my
    rx, ry, rot = interp(b['rots'], t, (b['cx'], b['cy'], 0.0))
    th = math.radians(rot)
    dx, dy = px - rx, py - ry
    c, s = math.cos(th), math.sin(th)
    px, py = rx + dx * c + dy * s, ry - dx * s + dy * c
    ax, ay, sx, sy = interp(b['scs'], t, (b['cx'], b['cy'], 1.0, 1.0))
    if abs(sx) < 1e-9 or abs(sy) < 1e-9:
        return False
    px = ax + (px - ax) / sx
    py = ay + (py - ay) / sy
    lx, ly = px - b['cx'], py - b['cy']
    return abs(lx) <= b['hw'] + margin and abs(ly) <= b['hh'] + margin


def main():
    with open(CHART, encoding='utf-8') as f:
        raw = json.load(f)
    blocks = load_blocks(raw)
    adds = [b for b in blocks if not b['subtract'] and b['enable'] <= b['disable']]

    rows = []
    with open(EVENTS, encoding='utf-8') as f:
        rd = csv.DictReader(f)
        for r in rd:
            ts = int(r['timestamp_ms'])
            t = ts / 1000.0
            x, y = float(r['x']), float(r['y'])
            active = [b for b in adds if b['enable'] <= t <= b['disable']]
            out = {'timestamp_ms': ts, 'seq_in_ms': r['seq_in_ms'], 'pointer': r['pointer'],
                   'action': r['action'], 'x': x, 'y': y, 'active_nf_count': len(active)}
            for m in MARGINS:
                hits = [b['idx'] for b in active if inside(b, x, y, t, m)]
                out[f'in_nf_m{int(m)}'] = len(hits) > 0
                out[f'nf_ids_m{int(m)}'] = ' '.join(map(str, hits))
            rows.append(out)

    out_path = os.path.join(CAP, 'nf_independent_event_check.csv')
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    summary = {'total_events': len(rows), 'block_areas_parsed': len(blocks), 'add_blocks': len(adds)}
    for m in MARGINS:
        k = f'in_nf_m{int(m)}'
        for act in ('DOWN', 'MOVE', 'UP'):
            sub = [r for r in rows if r['action'] == act]
            summary[f'{act}_in_nf_margin{int(m)}'] = sum(1 for r in sub if r[k])
            summary[f'{act}_total'] = len(sub)
    with open(os.path.join(CAP, 'nf_independent_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
