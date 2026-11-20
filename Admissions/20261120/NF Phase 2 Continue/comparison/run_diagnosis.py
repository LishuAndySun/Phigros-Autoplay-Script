import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
from chart import Chart
from nf_lifecycle_diagnosis import diagnose, summarize
from algo.algo3 import solve as solve3
from algo.algo3beta1 import solve as solve_b1
from algo.algo_base import TouchAction
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')
chart = Chart.from_dict(json.load(open(CHART, encoding='utf-8')))
out = {}
for name, fn in (('algo3', solve3), ('algo3beta1', solve_b1)):
    ch = Chart.from_dict(json.load(open(CHART, encoding='utf-8')))
    stats = []
    events = fn(ch, stats)
    recs = diagnose(ch.block_areas, events)
    s = summarize(recs)
    s['events'] = sum(len(v) for v in events.values())
    s['skipped'] = len(stats)
    out[name] = s
    with open(os.path.join(HERE, f'diag_{name}_records.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['lifecycle','pointer','kind','action','time_ms','x','y','seg_start','seg_end'])
        w.writeheader(); w.writerows(recs)
    print(name, json.dumps(s, ensure_ascii=False))
json.dump(out, open(os.path.join(HERE, 'diag_summary.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
