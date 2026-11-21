import json, sys, math, bisect
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chart import Chart
from block_area import margin_at
import algo.algo3beta1 as b

CHART = ROOT / 'Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json'
captured = {}
Orig = b.PointerAllocator
class Cap(Orig):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); captured['a'] = self
b.PointerAllocator = Cap

chart = Chart.from_dict(json.load(open(CHART, encoding='utf-8')))
stats, viol, drag = [], [], []
events = b.solve(chart, stats, viol, drag)
al = captured['a']

downs = {}
for (pid, t), (typ, ang) in al.tags.items():
    downs.setdefault(pid, []).append((t, typ))
for v in downs.values():
    v.sort()
names = {1: 'TAP', 2: 'DRAG', 3: 'HOLD?', 4: 'FLICK'}

def owner(pid, t):
    l = downs.get(pid, [])
    i = bisect.bisect_right([x[0] for x in l], t) - 1
    return names.get(l[i][1], l[i][1]) if i >= 0 else 'NONE'

by_owner = Counter(owner(v['pointer'], v['time_ms']) for v in viol)
by_kind_owner = Counter((v['kind'], owner(v['pointer'], v['time_ms'])) for v in viol)
print('violations by owner note type:', dict(by_owner))
print('by (kind, owner):', dict(by_kind_owner))

# DRAG 的目标点本身（判定线上的理想点）是否就在噪域内
inside_target = 0; total_drag_frames = 0
for fr in b.Frames.__iter__ and []: pass
print('drag_failures (no safe point found, held/skipped):', len(drag))
print('drag_failures by reason: all pid=-1 ->', Counter(d[4] for d in drag))

# 违规采样的时间分布与 NF 区间
ts = sorted(v['time_ms'] for v in viol)
print('violation time range ms:', ts[0], ts[-1])
buckets = Counter(t // 5000 * 5 for t in ts)
print('violations per 5s bucket:', dict(sorted(buckets.items())))

# SEGMENT：相邻两个事件端点各自安全，但中间插值穿过噪域
seg = [v for v in viol if v['kind'] == 'SEGMENT']
spans = Counter()
for v in seg:
    a, c = v['segment'].split('->'); spans[int(c) - int(a)] += 1
print('SEGMENT violations by segment length ms (top):', spans.most_common(8))
print('skipped by type:', Counter((names.get(s[1], s[1]), getattr(s[4], 'value', s[4])) for s in stats))
