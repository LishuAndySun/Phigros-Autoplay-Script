"""Task D: classify all 54 skipped notes and test whether a valid position existed under a coarser full-screen search.

Validity (mirrors production search_point semantics, see block_area.py):
  - on screen
  - not in NF at any 5 ms sample in [t, t+300] with margin 30 (independent validator)
  - perpendicular distance to the judge line >= 80 px
Relocation distance from the raw target is reported; 200 px is the production limit.
Search is a finite grid (8 px), so a 'no valid point' result here is evidence, not proof.
"""
import csv
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
OUT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, REPO)
VAL_PATH = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation',
                        'scripts', 'validate_nf_independent.py')
SKIP = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation',
                    'captures', 'algo3_desultory_at_skipped.csv')
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')

spec = importlib.util.spec_from_file_location('val', VAL_PATH)
val = importlib.util.module_from_spec(spec)
spec.loader.exec_module(val)

from chart import Chart  # production chart model, used only for note geometry and judge-line lookup

with open(CHART, encoding='utf-8') as f:
    raw = json.load(f)
blocks = val.load_blocks(raw)
adds = [b for b in blocks if not b['subtract'] and b['enable'] <= b['disable']]
chart = Chart.from_dict(raw)

SW, SH = 1280.0, 720.0
MIN_DIST, MAX_REL, DUR, GRID = 80.0, 200.0, 300, 8


def line_ends(center, ang):
    a = -ang * math.pi / 180
    dx, dy = math.cos(a) * SW / 2, math.sin(a) * SW / 2
    return (center[0] + dx, center[1] + dy), (center[0] - dx, center[1] - dy)


def pld(p, line):
    (x1, y1), (x2, y2) = line
    A, B, C = y2 - y1, x1 - x2, x2 * y1 - x1 * y2
    return abs(A * p[0] + B * p[1] + C) / math.hypot(A, B)


# Map (time_ms, note_type) -> candidate (pos, judge line ends); pick nearest to raw position.
# Keys mirror solve(): HOLD emits a TAP at ms; FLICK is scheduled at ms + flick_start (-50).
lookup = {}
for jl in chart.judge_lines:
    for nt in jl.notes_above + jl.notes_below:
        ms = round(jl.seconds(nt.time) * 1000)
        off = nt.x * 72
        x, y = jl.pos(nt.time)
        alpha = -jl.angle(nt.time) * math.pi / 180
        pos = (x + off * math.cos(alpha), y + off * math.sin(alpha))
        entry = (pos, line_ends(jl.pos(nt.time), jl.angle(nt.time)))
        if nt.typ == 3:
            lookup.setdefault((ms, 1), []).append(entry)
        elif nt.typ == 4:
            lookup.setdefault((ms - 50, 4), []).append(entry)
        else:
            lookup.setdefault((ms, nt.typ), []).append(entry)


def valid(px, py, ms, line):
    if not (0 <= px <= SW and 0 <= py <= SH):
        return False
    for tt in range(ms, ms + DUR + 1, 5):
        tsec = tt / 1000
        for b in adds:
            if b['enable'] <= tsec <= b['disable'] and val.inside(b, px, py, tsec, 30.0):
                return False
    return pld((px, py), line) >= MIN_DIST


rows_out = []
for s in csv.DictReader(open(SKIP, encoding='utf-8')):
    ms, typ = int(s['time_ms']), int(s['note_type'])
    rx, ry = float(s['raw_x']), float(s['raw_y'])
    cands = lookup.get((ms, typ), [])
    if cands:
        _, line = min(cands, key=lambda c: math.hypot(c[0][0] - rx, c[0][1] - ry))
    else:
        line = None
    t_s = ms / 1000
    active = [b for b in adds if b['enable'] <= t_s <= b['disable']]
    raw_hits = [b['idx'] for b in active if val.inside(b, rx, ry, t_s, 30.0)]

    best = None
    if line is not None:
        for px in range(0, int(SW) + 1, GRID):
            for py in range(0, int(SH) + 1, GRID):
                d = math.hypot(px - rx, py - ry)
                if best is not None and d >= best[0]:
                    continue
                if valid(px, py, ms, line):
                    best = (d, px, py)
    rows_out.append(dict(
        time_ms=ms, note_type=typ, raw_x=round(rx, 3), raw_y=round(ry, 3),
        reported_reason=s['reason'], judge_line_matched=line is not None,
        active_nf_count=len(active), raw_in_nf_m30=bool(raw_hits),
        nf_ids_raw_m30=';'.join(map(str, raw_hits)),
        coarse_search_found_valid=best is not None,
        nearest_valid_dist_px=round(best[0], 2) if best else '',
        nearest_valid_within_200px=bool(best and best[0] <= MAX_REL),
        nearest_valid_x=round(best[1], 1) if best else '',
        nearest_valid_y=round(best[2], 1) if best else '',
    ))

out = os.path.join(OUT, 'NF_Skipped_Note_Analysis.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
    w.writeheader()
    w.writerows(rows_out)

print('skipped', len(rows_out))
print('judge line matched', sum(r['judge_line_matched'] for r in rows_out))
print('raw position inside NF m30', sum(r['raw_in_nf_m30'] for r in rows_out))
print('coarse search found valid', sum(r['coarse_search_found_valid'] for r in rows_out))
print('valid within 200px', sum(r['nearest_valid_within_200px'] for r in rows_out))
