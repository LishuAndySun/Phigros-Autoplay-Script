"""DS AT 离线基线审计：统计各算法输出的触点数量、跳过音符与 NF 违规。只读，不修改谱面或缓存。"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chart import Chart  # noqa: E402
from block_area import margin_at  # noqa: E402
import algo.algo3 as algo3  # noqa: E402
import algo.algo3beta1 as algo3b  # noqa: E402

CHART = ROOT / 'Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json'


def summarize(name, events, skipped, violations):
    downs = sum(1 for evs in events.values() for e in evs if e.action.name == 'DOWN')
    moves = [e for evs in events.values() for e in evs if e.action.name == 'MOVE']
    reasons = Counter(getattr(r[4], 'value', str(r[4])) for r in skipped)
    kinds = Counter(v['kind'] for v in violations)
    return {
        'algo': name,
        'down_events': downs,
        'move_events': len(moves),
        'skipped_notes': len(skipped),
        'skip_reasons': dict(reasons),
        'nf_violations': len(violations),
        'violation_kinds': dict(kinds),
    }


def main():
    with open(CHART, encoding='utf-8') as f:
        data = json.load(f)
    results = []

    chart = Chart.from_dict(data)
    stats3: list = []
    ev3 = algo3.solve(chart)
    viol3 = algo3b.validate_pointer_paths(chart.block_areas, ev3)
    results.append(summarize('algo3', ev3, stats3, viol3))

    chart = Chart.from_dict(data)
    stats_b: list = []
    viol_b: list = []
    drag_b: list = []
    ev_b = algo3b.solve(chart, stats_b, viol_b, drag_b)
    results.append(summarize('algo3beta1', ev_b, stats_b, viol_b))

    out = ROOT / 'Admissions/20261121/ds_at_offline_baseline.json'
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    for r in results:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()
