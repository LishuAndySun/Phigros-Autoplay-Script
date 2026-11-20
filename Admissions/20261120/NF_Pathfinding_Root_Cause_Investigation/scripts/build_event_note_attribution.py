"""Build NF_Event_Note_Attribution.csv: one row per margin-0 violation (896 expected).

Joins instrumented events (key: timestamp, seq_in_ms, pointer, action, x, y) with the
independent validator output (same key). Adds pointer-neighbour events, the owning note's
chart fields, and the active NF block IDs at the event time (margin 0 and 30).
"""
import csv
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
ROOT = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation')
CAP = os.path.join(ROOT, 'captures')
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')
sys.path.insert(0, HERE)
import validate_nf_independent as V  # noqa: E402

with open(CHART, encoding='utf-8') as f:
    raw = json.load(f)
blocks = V.load_blocks(raw)

inst = list(csv.DictReader(open(os.path.join(CAP, 'phase2_instrumented_events.csv'), encoding='utf-8')))
chk = {}
for r in csv.DictReader(open(os.path.join(CAP, 'nf_independent_event_check.csv'), encoding='utf-8')):
    chk[(int(r['timestamp_ms']), int(r['pointer']), r['action'], round(float(r['x']), 6),
         round(float(r['y']), 6))] = r
print('validator rows', len(chk), 'instrumented rows', len(inst))

# per-pointer ordered sequence for neighbour lookup
by_ptr = defaultdict(list)
for i, r in enumerate(inst):
    by_ptr[int(r['pointer'])].append(i)
prev_idx, next_idx = {}, {}
for ptr, idxs in by_ptr.items():
    for a, b in zip(idxs, idxs[1:]):
        next_idx[a] = b
        prev_idx[b] = a

def active_ids(t, x, y, margin):
    ph_t = t
    return [b['idx'] for b in blocks if not b['subtract'] and b['enable'] <= ph_t <= b['disable']
            and V.inside(b, x, y, ph_t, margin)]

rows = []
for i, r in enumerate(inst):
    t_ms = int(r['timestamp_ms'])
    x, y = float(r['x']), float(r['y'])
    key = (t_ms, int(r['pointer']), r['action'], round(x, 6), round(y, 6))
    v = chk.get(key)
    if v is None or v['in_nf_m0'] != 'True':
        continue
    p = prev_idx.get(i)
    n = next_idx.get(i)
    rows.append({
        'event_index': i, 'timestamp_ms': t_ms, 'seq_in_ms': r['seq_in_ms'], 'action': r['action'],
        'pointer': r['pointer'], 'x': r['x'], 'y': r['y'], 'method': r['method'],
        'note_id': r['note_id'], 'note_type': r['note_type'],
        'note_orig_x': r['note_orig_x'], 'note_orig_y': r['note_orig_y'], 'note_angle': r['note_angle'],
        'prev_event_index': p if p is not None else '', 'prev_timestamp_ms': inst[p]['timestamp_ms'] if p is not None else '',
        'prev_action': inst[p]['action'] if p is not None else '',
        'next_event_index': n if n is not None else '', 'next_timestamp_ms': inst[n]['timestamp_ms'] if n is not None else '',
        'next_action': inst[n]['action'] if n is not None else '',
        'nf_ids_m0': ';'.join(map(str, active_ids(t_ms / 1000, x, y, 0.0))),
        'nf_ids_m30': ';'.join(map(str, active_ids(t_ms / 1000, x, y, 30.0))),
    })

out = os.path.join(ROOT, 'NF_Event_Note_Attribution.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print('rows', len(rows), 'wrote', out)
