# NF Phase 2 Access and Attribution Audit

Status: Phase 2 analysis paused for review. No production code was modified. No prior report, dataset, or capture was overwritten or deleted.

## Access restriction notice

The user reported that a command `find / -name 'attribute_algo3_events.py'` was run earlier in this investigation. That search is outside the permitted scope (full-disk search, possible network and iCloud permission prompts). This audit does not reproduce it. The output of that command is not present in the current session context, so its results and whether it touched network or iCloud locations are UNKNOWN from this session. Going forward, all search, read, and execution is limited to `/Users/lishuandysun/Documents/Phigros-Autoplay-Script/`.

## A. Git workspace state

Git branch `main`, HEAD `754ff32`.

Files created or modified by this investigation (round 2, dated folder `Admissions/20261120/`):

Created by this round:
- `Admissions/20261120/NF_Pathfinding_Root_Cause_Investigation/scripts/phase2_instrumented_attribution.py` (in-memory wrapper; verified)
- `Admissions/20261120/NF_Pathfinding_Root_Cause_Investigation/scripts/build_event_note_attribution.py`
- `Admissions/20261120/NF_Pathfinding_Root_Cause_Investigation/captures/phase2_instrumented_events.csv` (17,308 rows)
- `Admissions/20261120/NF_Pathfinding_Root_Cause_Investigation/NF_Event_Note_Attribution.csv` (896 rows)
- `Admissions/20261120/NF_Pathfinding_Root_Cause_Investigation/NF_Phase2_Access_and_Attribution_Audit.md` (this file)

Modified by this round:
- None of the Round 1 reports, datasets, or captures were modified.
- One earlier draft, `phase2_instrumented_attribution.py`, was created and deleted before the final version was written.
- `build_event_note_attribution.py` was modified once with `sed` to change `b['id']` to `b['idx']`.

Pre-existing uncommitted changes (not created by this round, not touched):
- `.DS_Store`, `Admissions/.notedeep/*` (modified and untracked pages)
- Deleted tracked files under `Admissions/*.md` (about 26 deletions)
- `cache`, `performance.log` (modified)
- Untracked `Admissions/20261111/` through `Admissions/20261120/`, and `Admissions/__pycache__/`

Origin of `Admissions/__pycache__/` is UNKNOWN. It may have been produced by an import during this round. It has not been deleted and should be reviewed before removal.

## B. File system access log

| # | Command or action | Paths touched | Inside project root? |
|---|---|---|---|
| 1 | Reported by user: `find / -name 'attribute_algo3_events.py'` | Entire filesystem | NO. Out of scope. Output not visible in this session. |
| 2 | Pre-summary: `find` for relocated artifacts | Unrecorded scope | UNKNOWN. Should be confirmed. |
| 3 | `shasum -a 256` on `Assets/Tracks/.../Chart_AT.json`, `git status`, `git log`, `ls` | Project | YES |
| 4 | Reads of `Admissions/20261120/scripts/attribute_algo3_events.py` (not found) | Project | YES |
| 5 | Reads of relocated scripts and `algo/algo3.py`, `block_area.py`, `judge_line.py`, `chart.py` | Project | YES |
| 6 | `rm -f` of draft `phase2_instrumented_attribution.py` | Project | YES |
| 7 | Run `phase2_instrumented_attribution.py` (reads `Assets/Tracks/.../Chart_AT.json`, `captures/algo3_desultory_at_events.csv`; writes `captures/phase2_instrumented_events.csv`) | Project | YES |
| 8 | Run `build_event_note_attribution.py` (imports `validate_nf_independent.py`; reads validator CSV; writes `NF_Event_Note_Attribution.csv`) | Project | YES |
| 9 | `sed -i` on `build_event_note_attribution.py` | Project | YES |
| 10 | Read-only summary script over `NF_Event_Note_Attribution.csv` | Project | YES |
| 11 | `rm -rf` of `scripts/__pycache__` | Project | YES |
| 12 | Read of `algo/algo3.py` lines 312–435 and `validate_nf_independent.py` lines 20–84 | Project | YES |
| 13 | Current audit: `git status`, `git diff --stat`, `find Admissions/20261120 -type f`, `grep` on `algo/algo3.py` and scripts, read-only Python over `captures/phase2_instrumented_events.csv` | Project | YES |

No symbolic links were followed. No NAS, SMB, NFS, iCloud, or cloud-synced paths were accessed by this round, as far as the commands above show. Commands 2 and 1 remain the only items whose scope cannot be verified from this session.

## C. Production, baseline, and historical record integrity

`git diff --stat` on `algo/`, `block_area.py`, `chart.py`, `judge_line.py`, `main.py`, `utils.py`, `control.py`, and `note.py` returned no output. These production paths are unmodified relative to HEAD `754ff32`.

Beta1 baseline and historical records: not modified by this round. The listed pending deletions under `Admissions/*.md` predate this round and were not caused by it; they should still be reviewed by the user.

The current `main.py` terminal run (exit 0) was started by the user, not by this investigation.

## D. `_down` execution order and UP ownership (source-verified)

From `algo/algo3.py`:

- `_down` (lines 317–326):
  - line 319: if `pointer.note is not None`, insert `UP` at `_release_at(pointer)` using `pointer.note.pos`
  - line 322: `pointer.note = note` (reassignment happens after the UP insert)
  - line 326: insert `DOWN` at `self.now` for `note.pos`
- `_flick` (lines 345–371):
  - line 362: UP for previous `pointer.note`, inserted before reassignment
  - line 371: `pointer.note = note`
- `_tap` (328–343) calls `_down` (through `_down`, so the UP belongs to the previous holder)
- `_drag` (375–377) calls `_down`
- `allocate` step 3 (lines 403–415): for a matched drag, `pointer.note = note` at line 403 runs before `MOVE` at line 411, so MOVE belongs to the drag note
- `allocate` lines 418–421: UP inserted with `pointer.note.pos` at line 420, then `pointer.note = None` at line 421
- `done` lines 428–431: same pattern as 418–421

Rule: an UP event belongs to the note held by the pointer at the moment the UP is inserted, which is before any reassignment. The `phase2_instrumented_attribution.py` wrapper applies this rule: it snapshots `ptr.note` inside `_insert` before the call for UP from `_down`/`_flick`, and for `allocate`/`done`, it snapshots the note still held at insert time.

Status: CONFIRMED by source reading. The rule has not been checked against every UP row. The 896 attribution rows have 12 UP events from `_down` and 3 from `allocate`, and their owners come from the snapshot, not an assumption.

## E. HOLD and DRAG note type separation

- `grep` of `phase2_instrumented_attribution.py` and `build_event_note_attribution.py` shows no code that merges note types. Owner note type is copied from the snapshot as-is.
- Note-type counts in `captures/phase2_instrumented_events.csv` (by method, note_type): types 1, 2, and 4 appear. Type 3 (HOLD) does not appear as an event owner. The algorithm splits HOLD into TAP (1) and DRAG (2) before allocation, so type 3 is never an owner.
- All 896 margin-0 violations in `NF_Event_Note_Attribution.csv` have `note_type` 2 (DRAG).

Status: CONFIRMED. No HOLD and DRAG merge in the attribution scripts. HOLD notes are represented as TAP and DRAG pieces upstream.

## F. Preservation of data

All previously generated data is kept: Round 1 reports, `NF_Violation_Dataset.csv`, `captures/*`, and `scripts/*`. Nothing was deleted or overwritten in this round except the discarded wrapper draft, which was never used for results.

## Open items for review

1. Confirm the scope and output of the earlier reported `find /` command. Its effect on network or iCloud permission prompts is UNKNOWN from this session.
2. Decide whether `Admissions/__pycache__/` should be removed. Its origin is UNKNOWN.
3. Confirm the prompt's origin counts (870 / 25 / 1). Verified data: 867 MOVE, 14 DOWN, 15 UP (12 from `_down`, 3 from `allocate`).
4. Phase 2 remaining tasks (region analysis, pointer trajectory, skipped notes, normal-direction feasibility, reports) are not started.
