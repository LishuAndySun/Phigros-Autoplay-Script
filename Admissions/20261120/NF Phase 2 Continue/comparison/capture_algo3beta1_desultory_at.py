"""Capture: run algo3beta1.solve() on DesultorySignals Chart_AT.json.

Writes only into this folder. Does not modify algo3 or Round 1 captures.
Usage (from project root): venv/bin/python "<this file>"
"""
import csv
import json
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from chart import Chart  # noqa: E402
from algo.algo3beta1 import solve, validate_pointer_paths  # noqa: E402
from block_area import margin_at  # noqa: F401,E402


def main():
    with open(CHART, encoding='utf-8') as f:
        raw = json.load(f)
    chart = Chart.from_dict(raw)
    stats: list = []
    violations: list = []
    t0 = time.time()
    events = solve(chart, stats, violations)
    elapsed = time.time() - t0

    total_events = sum(len(v) for v in events.values())
    max_active = 0
    active = set()
    for t in sorted(events):
        for ev in events[t]:
            if ev.action.name == 'DOWN':
                active.add(ev.pointer)
            elif ev.action.name == 'UP':
                active.discard(ev.pointer)
        max_active = max(max_active, len(active))

    summary = {
        'chart': os.path.relpath(CHART, REPO),
        'total_events': total_events,
        'skipped_notes': len(stats),
        'nf_violation_records': len(violations),
        'nf_violation_event_records': sum(1 for v in violations if v['segment'] == 'event'),
        'nf_violation_segment_records': sum(1 for v in violations if v['segment'] != 'event'),
        'peak_active_pointers': max_active,
        'solve_seconds': round(elapsed, 2),
    }
    with open(os.path.join(OUT_DIR, 'algo3beta1_desultory_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, 'algo3beta1_nf_violations.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['pointer', 'kind', 'time_ms', 'x', 'y', 'segment'])
        w.writeheader()
        for v in violations:
            w.writerow(v)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
