import json, sys, math
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chart import Chart
from block_area import margin_at, nearby_points
import algo.algo3beta1 as b

CHART = ROOT / 'Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json'
chart = Chart.from_dict(json.load(open(CHART, encoding='utf-8')))
blocks = chart.block_areas
drag = []
events = b.solve(chart, [], [], drag)

# 真实阶梯路径：事件之间触点静止在上一事件位置
seqs = {}
for t in sorted(events):
    for e in events[t]:
        seqs.setdefault(e.pointer, []).append((t, e.action.name, e.pos))
hit = Counter(); dur = Counter(); examples = []
for pid, seq in seqs.items():
    for i, (t, act, pos) in enumerate(seq):
        if act == 'UP':
            continue
        t_end = seq[i + 1][0] if i + 1 < len(seq) else t
        for tt in range(t, t_end, 2):
            if blocks.blocked(pos[0], pos[1], tt / 1000, margin_at(tt / 1000)):
                hit[act] += 1
                if len(examples) < 5 and act == 'MOVE':
                    examples.append((pid, t, t_end, pos))
                break
print('step-path: segments whose held position enters NF, by starting event:', dict(hit))
print('examples (pid, t_start, t_next, pos):', examples)

# DRAG 失败时：理想目标是否在 NF 内；半径 80 内无解，但更大半径是否有解
tgt_in_nf = 0; far_ok = 0; none_ok = 0; dists = []
sample = drag[::max(1, len(drag) // 400)]
for (t, typ, x, y, _) in sample:
    if blocks.blocked(x, y, t / 1000, margin_at(t / 1000)):
        tgt_in_nf += 1
    best = None
    for px, py in nearby_points(x, y, max_radius=1500, step=8):
        if not blocks.blocked(px, py, t / 1000, margin_at(t / 1000)):
            best = math.hypot(px - x, py - y); break
    if best is None: none_ok += 1
    else:
        dists.append(best)
        if best > 80: far_ok += 1
n = len(sample)
dists.sort()
print(f'sampled {n} drag failures: target inside NF={tgt_in_nf}, safe point exists only beyond 80px={far_ok}, no safe point on screen={none_ok}')
if dists:
    print('nearest-safe distance px: median', dists[len(dists)//2], 'p90', dists[int(len(dists)*.9)], 'max', dists[-1])
