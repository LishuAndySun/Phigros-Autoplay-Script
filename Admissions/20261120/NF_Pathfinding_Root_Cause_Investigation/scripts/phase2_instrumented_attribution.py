"""Phase 2 instrumented attribution wrapper (in-memory only; no production file modified).

Ownership rules (verified against algo/algo3.py _down/_flick/allocate):
  - DOWN emitted inside _tap/_flick/_down: owner = the note passed to that call.
  - UP emitted inside _down/_flick: owner = pointer.note BEFORE reassignment (previous holder).
  - UP emitted in allocate step 4 / done: owner = pointer.note (still the holding note).
  - MOVE emitted in allocate step 3: owner = pointer.note (set to the drag note before insert).
  - MOVE emitted in _flick: owner = the flick note.
Original target position is snapshotted at call entry because _tap mutates note.pos.

Output: captures/phase2_instrumented_events.csv (verified identical to unmodified capture).
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, REPO)
ROOT = os.path.join(REPO, 'Admissions', '20261120', 'NF_Pathfinding_Root_Cause_Investigation')
CAP = os.path.join(ROOT, 'captures')
CHART = os.path.join(REPO, 'Assets', 'Tracks', 'DesultorySignals.technoplanet.0', 'Chart_AT.json')

import algo.algo3 as a3  # noqa: E402
from chart import Chart  # noqa: E402

ctx = {'method': 'UNSET', 'owner': None}
records = []  # (timestamp, event, method, owner_snapshot)


def snap(note):
    if note is None:
        return None
    return dict(note_id=note.note_id, note_type=note.note_type,
                orig_x=note.pos[0], orig_y=note.pos[1], angle=note.angle)


def wrap_method(name):
    orig = getattr(a3.PointerAllocator, name)

    def inner(self, *args, **kwargs):
        prev_m, prev_o = ctx['method'], ctx['owner']
        ctx['method'] = name
        note = next((a for a in args if isinstance(a, a3.SimpleNote)), None)
        ctx['owner'] = snap(note)  # snapshot before any mutation in the call
        try:
            return orig(self, *args, **kwargs)
        finally:
            ctx['method'], ctx['owner'] = prev_m, prev_o
    setattr(a3.PointerAllocator, name, inner)


for n in ('_tap', '_flick', '_drag', '_down'):
    wrap_method(n)

orig_allocate = a3.PointerAllocator.allocate


def allocate_tagged(self, frame):
    prev_m, prev_o = ctx['method'], ctx['owner']
    ctx['method'] = 'allocate'
    ctx['owner'] = None
    try:
        return orig_allocate(self, frame)
    finally:
        ctx['method'], ctx['owner'] = prev_m, prev_o


a3.PointerAllocator.allocate = allocate_tagged

orig_done = a3.PointerAllocator.done


def done_tagged(self):
    prev_m, prev_o = ctx['method'], ctx['owner']
    ctx['method'] = 'done'
    ctx['owner'] = None
    try:
        return orig_done(self)
    finally:
        ctx['method'], ctx['owner'] = prev_m, prev_o


a3.PointerAllocator.done = done_tagged

orig_insert = a3.PointerAllocator._insert


def tagged_insert(self, timestamp, event):
    method = ctx['method']
    owner = ctx['owner']
    if method in ('allocate', 'done') or (event.action.name == 'UP' and method == 'UNSET'):
        ptr = next((p for p in self.pointers if p.id == event.pointer), None)
        owner = snap(ptr.note) if ptr is not None else None
    elif event.action.name == 'UP' and method in ('_down', '_flick'):
        ptr = next((p for p in self.pointers if p.id == event.pointer), None)
        owner = snap(ptr.note) if ptr is not None else None  # previous holder, before reassignment
    orig_insert(self, timestamp, event)
    records.append((timestamp, event, method, owner))


a3.PointerAllocator._insert = tagged_insert

with open(CHART, encoding='utf-8') as f:
    chart = Chart.from_dict(json.load(f))
events = a3.solve(chart, [])

flat = []
for ts in sorted(events):
    for seq, ev in enumerate(events[ts]):
        flat.append((ts, seq, ev.pointer, ev.action.name, float(ev.pos[0]), float(ev.pos[1])))
with open(os.path.join(CAP, 'algo3_desultory_at_events.csv'), encoding='utf-8') as f:
    cap_rows = [(int(r['timestamp_ms']), int(r['seq_in_ms']), int(r['pointer']), r['action'],
                 float(r['x']), float(r['y'])) for r in csv.DictReader(f)]
same = flat == cap_rows
print('instrumented stream identical to capture:', same, len(flat), len(cap_rows))
if not same:
    sys.exit(1)

out = os.path.join(CAP, 'phase2_instrumented_events.csv')
per_ms = {}
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['timestamp_ms', 'seq_in_ms', 'pointer', 'action', 'x', 'y', 'method',
                'note_id', 'note_type', 'note_orig_x', 'note_orig_y', 'note_angle'])
    for ts, ev, method, o in records:
        seq = per_ms.get(ts, 0)
        per_ms[ts] = seq + 1
        w.writerow([ts, seq, ev.pointer, ev.action.name, repr(float(ev.pos[0])), repr(float(ev.pos[1])), method,
                    o['note_id'] if o else -1, o['note_type'] if o else -1,
                    repr(o['orig_x']) if o else '', repr(o['orig_y']) if o else '',
                    repr(o['angle']) if o else ''])
print('wrote', out, len(records))
