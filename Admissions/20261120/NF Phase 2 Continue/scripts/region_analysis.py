"""Task A: NF region analysis for DesultorySignals AT.

Imports the independent validator by path (it does not import production block_area).
Writes CSV outputs only inside the NF Phase 2 Continue directory.
"""
import csv
import importlib.util
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
OUT = os.path.abspath(os.path.join(HERE, '..'))
VAL_PATH = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation',
                        'scripts', 'validate_nf_independent.py')
DATASET = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation',
                       'NF_Violation_Dataset.csv')
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')
REGIONS = [69, 159, 71, 74, 45, 4]

spec = importlib.util.spec_from_file_location('val', VAL_PATH)
val = importlib.util.module_from_spec(spec)
spec.loader.exec_module(val)

with open(CHART, encoding='utf-8') as f:
    raw = json.load(f)
blocks = val.load_blocks(raw)

rows = list(csv.DictReader(open(DATASET, encoding='utf-8')))
viol = defaultdict(list)  # nf id -> list of (ts, pointer, action, x, y, in_m30)
for r in rows:
    ids0 = [s for s in r['violating_nf_ids_margin0'].split(';') if s]
    for nid in ids0:
        viol[int(nid)].append((int(r['timestamp_ms']), r['pointer'], r['action'],
                               float(r['x']), float(r['y']), r['origin_method']))

summary = []
for rid in REGIONS:
    b = blocks[rid]
    ev = viol[rid]
    ts = sorted(e[0] for e in ev)
    enable, disable = b['enable'], b['disable']
    span_ms = (disable - enable) * 1000
    if ts:
        first_off = (ts[0] / 1000 - enable) * 1000
        last_off = (disable - ts[-1] / 1000) * 1000
    else:
        first_off = last_off = float('nan')
    row = dict(
        nf_id=rid, enable_s=round(enable, 3), disable_s=round(disable, 3),
        window_ms=round(span_ms, 1), half_w=round(b['hw'], 2), half_h=round(b['hh'], 2),
        center_phys_x=round(b['cx'], 2), center_phys_y=round(b['cy'], 2),
        center_screen_x=round(b['cx'], 2), center_screen_y=round(720 - b['cy'], 2),
        move_keys=len(b['moves']), rot_keys=len(b['rots']), scale_keys=len(b['scs']),
        violation_events=len(ev), first_violation_s=round(ts[0] / 1000, 3) if ts else '',
        last_violation_s=round(ts[-1] / 1000, 3) if ts else '',
        first_violation_offset_ms=round(first_off, 1) if ts else '',
        last_violation_gap_to_disable_ms=round(last_off, 1) if ts else '',
        pointers=';'.join(sorted(set(e[1] for e in ev))),
        actions=';'.join(sorted(set(e[2] for e in ev))),
        origins=';'.join(sorted(set(e[5] for e in ev))),
    )
    summary.append(row)

out_csv = os.path.join(OUT, 'NF_Region_Summary_TaskA.csv')
with open(out_csv, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
    w.writeheader()
    w.writerows(summary)

for s in summary:
    print(s)
