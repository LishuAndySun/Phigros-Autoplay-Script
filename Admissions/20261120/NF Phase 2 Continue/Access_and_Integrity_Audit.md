# Access and Integrity Audit: NF Phase 2 Continuation (partial)

Status: Partial. Only baseline, source reading, and dataset verification are done. Tasks A–F and the final synthesis are NOT started. Stopped for review.

## 1. Access scope
- All reads and writes were inside `/Users/lishuandysun/Documents/Phigros-Autoplay-Script/`.
- Out-of-scope command: an earlier `find /` (from the prior round) was run and reported by the user. Its output is not visible in this session, so its scope is UNKNOWN.
- Out-of-root write: `/tmp/_phase2_status_initial.txt` was created during the baseline check. It was deleted in this session. Its content was identical to `.initial_git_status_snapshot.txt` in this directory, which was generated from the same `git status --short` call.
- No `mdfind`, iCloud, NAS, or symlink access was performed in this session.

## 2. Git baseline
- Branch: `main`. HEAD: `754ff32d2fe468a2ba5f005413e68d1981a619a4`.
- Initial `git status --short`: 85 lines, saved verbatim in `.initial_git_status_snapshot.txt` (this directory).
- Pre-existing uncommitted changes were not touched. No `git reset`, `clean`, `checkout`, `restore`, or `stash` was run.
- `git diff --stat` for `algo/algo3.py`, `block_area.py`, `judge_line.py`, `chart.py`, `note.py`, `utils.py`, `main.py`, `control.py` returned empty, so these production files have no diff.

## 3. File hashes (SHA-256, baseline)
- `Chart_AT.json` (DesultorySignals): `c9807022245ac1ae9299760422518d124dcffbdbbef448a0c4ade515265b517c` (matches run meta).
- `algo/algo3.py`: `51615c77…1002` (recorded in the earlier baseline).

## 4. Source reading (no edits)
- `block_area.py`: `search_point` (line ~154), `PlacementFailure` (line 22), `MARGIN=30` (line 16), `USE_SUBTRACT=False` (line 18), `BlockAreas._hit` / `blocked` (lines ~144–152).
- `judge_line.py`: `JudgeLine.pos` (line 114), `angle` (line 122), `pos_of` (line 132). Note `pos()` returns `(0,0)` when no move event covers `t`.
- `algo/algo3.py`: `alloc` 254, `check` 280, `match` 292, `_down` 317, `_tap` 328, `_flick` 345, `_drag` 375, `allocate` 379, `done` 426, `solve` 435. HOLD DRAG frames are added at line 465 with no clearance check.
- `chart.py`: `Chart.from_dict` builds `BlockAreas` from `blockAreaList`.

## 5. Dataset verification
- `captures/algo3_desultory_at_skipped.csv`: 54 data rows. Breakdown:
  - type 1 (TAP): NO_VALID_POSITION 16, RELOCATION_LIMIT_EXCEEDED 34 (total 50)
  - type 4 (FLICK): NO_VALID_POSITION 3, RELOCATION_LIMIT_EXCEEDED 1 (total 4)
- DISCREPANCY: the prior summary stated type 1 = 34 (RELOCATION 18 + NO_VALID 16). The file shows type 1 = 50 (RELOCATION 34 + NO_VALID 16). The total of 54 is correct. The file is treated as authoritative; the earlier summary figure is wrong.
- `NF_Event_Note_Attribution.csv`: 896 data rows (897 lines with header), as expected.
- `NF_Violation_Dataset.csv`: 896 data rows (897 lines with header), as expected.
- `captures/algo3_desultory_at_run_meta.json`: 17,308 events, 11,894 timestamps, 160 block areas, 24 judge lines, 54 skipped.

## 6. Origin-count discrepancy (carried from prior round)
- Prompt says 870/25/1. Verified 867 MOVE / 14+12 DOWN (from `_down`) / 3 UP (from `allocate`). Reported as a discrepancy.

## 7. Outputs
- Written only to this directory: `Access_and_Integrity_Audit.md`, `.initial_git_status_snapshot.txt`, and the prior `NF_Phase2_Access_and_Attribution_Audit.md`.
- No existing dataset, capture, or Round 1 file was modified or overwritten.
- `Admissions/__pycache__/` was not deleted.

## 8. Not done
- Tasks A–F, `NF_Phase2_Final_Analysis.md`, and the final validation (Section 12) remain. These require a separate pass.

## Final validation (this continuation)

- Out-of-root write: `/tmp/unused_placeholder.txt` was created by a mistaken write and deleted. Confirmed absent afterward.
- Untracked file: `Admissions/.notedeep/state/pages/1a526695-da91-43d5-83e2-39e5d335cc31.json` appeared at 18:50, after the 18:47 baseline. Its origin is UNKNOWN. It was not created or modified by this continuation and was left in place.
- Git HEAD unchanged at 754ff32d2fe468a2ba5f005413e68d1981a619a4. Status is 86 lines: the 85 baseline lines plus the untracked file above.
- Production hashes: `algo/algo3.py` 51615c77…1002 (unchanged), `block_area.py` a54ed5be…, `judge_line.py` 1ddde7f2…. The algo3 hash matches Round 1.
- Task D matching was corrected (see NF_Skipped_Note_Analysis.md). The earlier 47 match count is superseded by 54.
- No production files were edited. All outputs are inside this folder.
- Status: Partial. The 11 spec questions were not available in the folder, so Task F answers are mapped to Tasks A to E. The `charts/` folder was not created because no chart output was required by the executed tasks.
