"""Build NF_Violation_Dataset.csv and episode statistics from the captured, attributed, and independently validated events.

Inputs (../captures/): algo3_desultory_at_attributed_events.csv, nf_independent_event_check.csv
Outputs: ../../NF_Violation_Dataset.csv (all violating events, margin 0),
         ../captures/nf_violation_stats.json
"""
import csv
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, '..', 'captures')
OUT_CSV = os.path.join(HERE, '..', 'NF_Violation_Dataset.csv')


def key(ts, ptr, act, x, y):
    return (int(ts), int(ptr), act, round(float(x), 6), round(float(y), 6))


val = {}
for r in csv.DictReader(open(os.path.join(CAP, 'nf_independent_event_check.csv'), encoding='utf-8')):
    val[key(r['timestamp_ms'], r['pointer'], r['action'], r['x'], r['y'])] = r

rows = []
for i, a in enumerate(csv.DictReader(open(os.path.join(CAP, 'algo3_desultory_at_attributed_events.csv'),
                                          encoding='utf-8'))):
    v = val[key(a['timestamp_ms'], a['pointer'], a['action'], a['x'], a['y'])]
    rows.append({'event_index': i, 'timestamp_ms': int(a['timestamp_ms']), 'pointer': int(a['pointer']),
                 'action': a['action'], 'x': float(a['x']), 'y': float(a['y']),
                 'origin_method': a['origin_method'],
                 'active_nf_count': int(v['active_nf_count']),
                 'violating_nf_ids_margin0': v['nf_ids_m0'],
                 'in_nf_margin0': v['in_nf_m0'] == 'True',
                 'in_nf_margin30': v['in_nf_m30'] == 'True'})

viol = [r for r in rows if r['in_nf_margin0']]

fields = ['event_index', 'timestamp_ms', 'pointer', 'action', 'x', 'y', 'origin_method',
          'active_nf_count', 'violating_nf_ids_margin0', 'in_nf_margin0', 'in_nf_margin30']
with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in viol:
        w.writerow({k: r[k] for k in fields})

# Episodes: consecutive violating MOVE events on the same pointer with no gap > 16 ms
episodes = []
cur = None
for r in sorted(viol, key=lambda r: (r['pointer'], r['timestamp_ms'])):
    if cur and cur['pointer'] == r['pointer'] and r['timestamp_ms'] - cur['end'] <= 16:
        cur['end'] = r['timestamp_ms']
        cur['n'] += 1
        cur['nf'].update(r['violating_nf_ids_margin0'].split())
    else:
        if cur:
            episodes.append(cur)
        cur = {'pointer': r['pointer'], 'start': r['timestamp_ms'], 'end': r['timestamp_ms'], 'n': 1,
               'nf': Counter(r['violating_nf_ids_margin0'].split())}
if cur:
    episodes.append(cur)

stats = {
    'total_events': len(rows),
    'violating_events_margin0': len(viol),
    'violating_by_action': dict(Counter(r['action'] for r in viol)),
    'violating_by_origin_method': dict(Counter(r['origin_method'] for r in viol)),
    'violating_by_origin_and_action': {f'{o}|{a}': n for (o, a), n in
                                       Counter((r['origin_method'], r['action']) for r in viol).items()},
    'violating_by_pointer': dict(Counter(str(r['pointer']) for r in viol)),
    'violating_margin30_total': sum(1 for r in rows if r['in_nf_margin30']),
    'episodes_pointer_runs': len(episodes),
    'episodes_longest_events': max((e['n'] for e in episodes), default=0),
    'violating_time_range_ms': [min(r['timestamp_ms'] for r in viol), max(r['timestamp_ms'] for r in viol)],
    'top_violating_nf_ids': Counter(
        nid for r in viol for nid in r['violating_nf_ids_margin0'].split()).most_common(15),
}
with open(os.path.join(CAP, 'nf_violation_stats.json'), 'w', encoding='utf-8') as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)
print(json.dumps(stats, ensure_ascii=False, indent=2))
