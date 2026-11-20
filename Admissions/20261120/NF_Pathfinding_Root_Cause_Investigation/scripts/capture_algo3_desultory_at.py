"""Read-only capture: run unmodified production Algo3 solve() on DesultorySignals Chart_AT.json
and dump the full event stream to CSV. Production files are not modified.

Usage (from repo root):
    venv/bin/python -m Admissions.20261120.scripts.capture_algo3_desultory_at
Outputs (written next to this script, in ../captures/):
    algo3_desultory_at_events.csv
    algo3_desultory_at_skipped.csv
    algo3_desultory_at_run_meta.json
"""
import csv
import hashlib
import json
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, REPO)

CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'captures')

from chart import Chart  # noqa: E402
from algo.algo3 import solve  # noqa: E402


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    digest = sha256(CHART)
    with open(CHART, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    chart = Chart.from_dict(raw)

    t0 = time.time()
    stats = []
    events = solve(chart, stats)
    elapsed = time.time() - t0

    rows = []
    for ts in sorted(events):
        for seq, ev in enumerate(events[ts]):
            x, y = ev.pos
            rows.append((ts, seq, ev.pointer, ev.action.name, repr(float(x)), repr(float(y))))

    ev_path = os.path.join(OUT_DIR, 'algo3_desultory_at_events.csv')
    with open(ev_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['timestamp_ms', 'seq_in_ms', 'pointer', 'action', 'x', 'y'])
        w.writerows(rows)

    sk_path = os.path.join(OUT_DIR, 'algo3_desultory_at_skipped.csv')
    with open(sk_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['time_ms', 'note_type', 'raw_x', 'raw_y', 'reason'])
        for t, nt, x, y, reason in stats:
            w.writerow([t, nt, x, y, getattr(reason, 'value', str(reason))])

    meta = {
        'chart_path': os.path.relpath(CHART, REPO),
        'chart_sha256': digest,
        'chart_bytes': os.path.getsize(CHART),
        'block_area_count': len(raw.get('blockAreaList', [])),
        'judge_line_count': len(raw.get('judgeLineList', [])),
        'event_count': len(rows),
        'timestamp_count': len(events),
        'skipped_count': len(stats),
        'solve_seconds': round(elapsed, 2),
        'python': sys.version.split()[0],
    }
    with open(os.path.join(OUT_DIR, 'algo3_desultory_at_run_meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
