"""Cross-check: production BlockAreas.blocked() (read-only import) vs the independent validator
for every captured event at margin 0 and margin 30. Writes ../captures/nf_crosscheck_summary.json.
"""
import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
import validate_nf_independent as V  # noqa: E402
from block_area import BlockAreas  # noqa: E402

CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')
CAP = os.path.join(HERE, '..', 'captures')

with open(CHART, encoding='utf-8') as f:
    raw = json.load(f)
prod = BlockAreas(raw['blockAreaList'])
indep = [b for b in V.load_blocks(raw) if not b['subtract']]

res = Counter()
mismatch = []
with open(os.path.join(CAP, 'algo3_desultory_at_events.csv'), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        t = int(r['timestamp_ms']) / 1000.0
        x, y = float(r['x']), float(r['y'])
        for m in (0.0, 30.0):
            p = prod.blocked(x, y, t, m)
            i = any(b['enable'] <= t <= b['disable'] and V.inside(b, x, y, t, m) for b in indep)
            res[(m, p == i)] += 1
            if p != i and len(mismatch) < 50:
                mismatch.append({'t_ms': r['timestamp_ms'], 'pointer': r['pointer'], 'action': r['action'],
                                 'x': x, 'y': y, 'margin': m, 'production': p, 'independent': i})

summary = {
    'margin0_agree': res[(0.0, True)], 'margin0_disagree': res[(0.0, False)],
    'margin30_agree': res[(30.0, True)], 'margin30_disagree': res[(30.0, False)],
    'sample_mismatches': mismatch,
}
with open(os.path.join(CAP, 'nf_crosscheck_summary.json'), 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps({k: v for k, v in summary.items() if k != 'sample_mismatches'}, indent=2))
print('sample mismatches:', len(mismatch))
