"""Task C: continuous-segment intersection test (linear interpolation between consecutive events).

Labelled APPROXIMATION: the game's true inter-event path is not verified. Uses the independent validator
for NF membership. For each consecutive pair of events on the same pointer, samples the segment at
1 ms steps and checks membership at margin 0 and margin 30.
"""
import csv
import importlib.util
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
OUT = os.path.abspath(os.path.join(HERE, '..'))
VAL_PATH = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation',
                        'scripts', 'validate_nf_independent.py')
EVENTS = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation',
                      'captures', 'algo3_desultory_at_events.csv')
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')

spec = importlib.util.spec_from_file_location('val', VAL_PATH)
val = importlib.util.module_from_spec(spec)
spec.loader.exec_module(val)
with open(CHART, encoding='utf-8') as f:
    blocks = val.load_blocks(json.load(f))
adds = [b for b in blocks if not b['subtract'] and b['enable'] <= b['disable']]


def nf_hits(x, y, t_s, margin):
    return [b['idx'] for b in adds if b['enable'] <= t_s <= b['disable'] and val.inside(b, x, y, t_s, margin)]


with open(EVENTS, encoding='utf-8') as f:
    events = list(csv.DictReader(f))

by_ptr = defaultdict(list)
for e in events:
    by_ptr[e['pointer']].append(e)

results = []
for ptr, evs in by_ptr.items():
    evs.sort(key=lambda e: (int(e['timestamp_ms']), int(e['seq_in_ms'])))
    for a, b in zip(evs, evs[1:]):
        t0, t1 = int(a['timestamp_ms']), int(b['timestamp_ms'])
        if t1 <= t0 or b['action'] == 'DOWN' or a['action'] == 'UP':
            continue
        x0, y0 = float(a['x']), float(a['y'])
        x1, y1 = float(b['x']), float(b['y'])
        hit0 = hit30 = False
        first_hit_t = None
        for t in range(t0, t1 + 1):
            k = (t - t0) / (t1 - t0)
            x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
            ts = t / 1000
            if nf_hits(x, y, ts, 0.0):
                hit0 = True
                if first_hit_t is None:
                    first_hit_t = t
            if nf_hits(x, y, ts, 30.0):
                hit30 = True
        if hit0 or hit30:
            results.append(dict(pointer=ptr, t0=t0, t1=t1, action_b=b['action'],
                                endpoint_nf_m0=bool(nf_hits(x1, y1, t1 / 1000, 0.0)),
                                segment_hits_m0=hit0, segment_hits_m30=hit30,
                                first_hit_ms=first_hit_t if first_hit_t is not None else '',
                                x0=x0, y0=y0, x1=x1, y1=y1))

out = os.path.join(OUT, 'NF_Continuous_Segment_Check_TaskC.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    keys = ['pointer', 't0', 't1', 'action_b', 'endpoint_nf_m0', 'segment_hits_m0', 'segment_hits_m30',
            'first_hit_ms', 'x0', 'y0', 'x1', 'y1']
    w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
    w.writeheader()
    w.writerows(results)

print('segments with interior NF hit (m0 or m30):', len(results))
print('segments with m0 hit:', sum(r['segment_hits_m0'] for r in results))
print('segments with m30 hit:', sum(r['segment_hits_m30'] for r in results))
print('segment endpoints in NF at m0 (violating events):', sum(r['endpoint_nf_m0'] for r in results))
print('segments with interior hit but endpoints clear:',
      sum(1 for r in results if r['segment_hits_m0'] and not r['endpoint_nf_m0']))
