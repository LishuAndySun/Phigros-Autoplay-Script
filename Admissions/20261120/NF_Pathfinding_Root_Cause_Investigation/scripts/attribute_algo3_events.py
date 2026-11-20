"""Runtime attribution of every Algo3 event to its generating code path.

Wraps (monkeypatches in memory only; no production file is modified) the PointerAllocator
methods to tag each _insert() call with the method that produced it and the SimpleNote
note_id / note_type / pos. Output must match the unmodified capture exactly; this script
verifies that before writing attribution output.

Output: ../captures/algo3_desultory_at_attributed_events.csv
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, REPO)
CAP = os.path.join(HERE, '..', 'captures')
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')

import algo.algo3 as a3  # noqa: E402
from chart import Chart  # noqa: E402

ctx = {'origin': 'UNSET', 'note': None}
records = []  # (timestamp, seq, event, origin, note_id, note_type, note_pos)


def wrap(name):
    orig = getattr(a3.PointerAllocator, name)

    def inner(self, *args, **kwargs):
        prev = ctx['origin']
        ctx['origin'] = name
        try:
            return orig(self, *args, **kwargs)
        finally:
            ctx['origin'] = prev
    setattr(a3.PointerAllocator, name, inner)


for n in ('_tap', '_flick', '_drag', '_down', 'done'):
    wrap(n)

# Record the note type of the SimpleNote passed into _down, so DOWN from _tap and _drag can be separated.
orig_down = a3.PointerAllocator._down


def down_typed(self, pointer, note):
    prev = ctx.get('note_type')
    ctx['note_type'] = note.note_type
    try:
        return orig_down(self, pointer, note)
    finally:
        ctx['note_type'] = prev


a3.PointerAllocator._down = down_typed

orig_insert = a3.PointerAllocator._insert


def tagged_insert(self, timestamp, event):
    orig_insert(self, timestamp, event)
    records.append((timestamp, event, ctx['origin'] + ('' if ctx.get('note_type') is None else f":type{ctx['note_type']}")))


a3.PointerAllocator._insert = tagged_insert

# Tag MOVE emitted directly by allocate() step 3 (matched DRAG continuation)
orig_allocate = a3.PointerAllocator.allocate


def allocate_tagged(self, frame):
    prev = ctx['origin']
    ctx['origin'] = 'allocate:drag_continuation_or_release'
    try:
        return orig_allocate(self, frame)
    finally:
        ctx['origin'] = prev


a3.PointerAllocator.allocate = allocate_tagged

with open(CHART, encoding='utf-8') as f:
    chart = Chart.from_dict(json.load(f))
events = a3.solve(chart, [])

# Consistency check: attributed stream must equal the unmodified capture
flat = []
for ts in sorted(events):
    for seq, ev in enumerate(events[ts]):
        flat.append((ts, seq, ev.pointer, ev.action.name, float(ev.pos[0]), float(ev.pos[1])))
with open(os.path.join(CAP, 'algo3_desultory_at_events.csv'), encoding='utf-8') as f:
    cap_rows = [(int(r['timestamp_ms']), int(r['seq_in_ms']), int(r['pointer']), r['action'],
                 float(r['x']), float(r['y'])) for r in csv.DictReader(f)]
same = flat == cap_rows
print('attributed run identical to capture:', same, len(flat), len(cap_rows))
if not same:
    sys.exit(1)

out = os.path.join(CAP, 'algo3_desultory_at_attributed_events.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['timestamp_ms', 'pointer', 'action', 'x', 'y', 'origin_method'])
    for ts, ev, origin in records:
        w.writerow([ts, ev.pointer, ev.action.name, repr(float(ev.pos[0])), repr(float(ev.pos[1])), origin])
print('wrote', out, len(records))
