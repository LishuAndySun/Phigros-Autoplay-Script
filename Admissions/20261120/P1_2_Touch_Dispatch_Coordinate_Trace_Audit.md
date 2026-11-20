# P1.2 Touch Dispatch Coordinate Trace Audit

Scope: read-only. No production source, Beta1 baseline, or baseline experiment record was modified. No gameplay experiment was run. Offline simulation only.

Evidence tiers used below:
- SRC: confirmed by reading source.
- SIM: confirmed by offline re-run of `algo3.solve` on `Chart_AT.json` (no patch to production code; a read-only monkeypatch on `_insert` was used for tagging).
- ASSUMED: depends on an assumed device size (1920x1080, mirror off). Not measured at runtime.
- UNKNOWN: no evidence in the code or logs.

## 1. Dispatch pipeline overview

| Stage | Location | Evidence |
|---|---|---|
| Generation | `algo/algo3.py` `solve` / `PointerAllocator` | SRC, SIM |
| Coordinate rescale (in place) | `main.py` dispatch block (~L470–495): `x = xoffset + round(x*scale_factor)`, optional mirror, `y = yoffset + round(y*scale_factor)`, `evs[i] = ev._replace(pos=...)` | SRC |
| Ordering | `main.py` `ans_iter = iter(sorted(ans.items()))` (sorted by timestamp key; list order preserved within a timestamp) | SRC |
| Submission loop | `main.py` `while now >= ce_ms - LOOKAHEAD_MS:` calls `sender.submit(ce_ms, ces, ...)`; `LOOKAHEAD_MS = 120` | SRC |
| Queue | `TouchSender.submit` -> `queue.Queue.put` | SRC |
| Consumption | `TouchSender._loop`: `queue.get()`, sleep until `clock() + ms/1000`, late filter, then `ctl.touch(...)` per event | SRC |
| Late filter | if `wait < -0.05`: drop MOVE only (DOWN/UP kept); `self.dropped` counts drops | SRC |
| Send | `DeviceController.touch` -> `_send_touch`: `struct.pack(...)` then `control_socket.sendall(packet)` | SRC |
| Error handling | `_loop` catches `OSError` only (sets `running=False`, returns). Outer dispatch loop has `except Exception: pass` | SRC |
| Device receipt | none. No touch acknowledgement exists in the protocol path | SRC, UNKNOWN |

Note: the main dispatch block exists twice (sync mode and immediate mode, around L570 and L638–668). Both use the same `submit` path. Only the sync-mode path was traced in full; the immediate-mode path has the same `submit` call shape.

## 2. Event accounting

| Item | Value | Tier |
|---|---|---|
| Generated TouchEvents | 6928 | SIM |
| Timestamps (sorted keys) | 5217 | SIM |
| Distinct event-list objects | 5217 (no shared lists) | SIM |
| Pointer IDs | 1000, 1001, 1002, 1003, 1004 | SIM |
| DOWN / MOVE / UP | derived per pointer (see Section 5) | SIM |
| Generated events entering queue | not measured in this round (would require runtime instrumentation) | UNKNOWN |
| Late MOVE drops at runtime | 0 (from user log) | runtime log |
| Events actually passed to `ctl.touch` | not measured | UNKNOWN |
| `sendall` successes / failures | not measured | UNKNOWN |
| Android receipt | UNKNOWN | UNKNOWN |

Caveat: the runtime log line `因迟到丢弃 MOVE 0 个` is printed in the `finally` block at the end of a run. It counts only late MOVE drops. It does not count sends, failures, or receipts. It also does not prove the late filter ran on every batch.

## 3. Full 44-UP trace

Definitions:
- "Previous" = last generated DOWN or MOVE for the same pointer (SIM).
- Coordinates before transform are logical Algo3 coordinates.
- Final coordinates use assumed device 1920x1080, mirror off, scale = 1080/720 = 1.5, xoffset = 420, yoffset = 0 (ASSUMED).
- "UP send invoked" and "sendall returned" are UNKNOWN for every row: no runtime send instrumentation was run. Both fields are recorded as UNKNOWN, not as true.
- All 44 previous events are MOVE. Each UP follows a MOVE.

| # | PID | UP t (ms) | Prev t (ms) | Prev logical (x,y) | UP logical (x,y) | Diff (px, logical) | Prev final (px) | UP final (px) | Final equal | UP send invoked | sendall ok |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1000 | 25229 | 25227 | (512.0, 203.4488) | (512.0, 203.2614) | 0.1875 | (768,305) | (768,305) | Yes | UNKNOWN | UNKNOWN |
| 2 | 1000 | 26047 | 26045 | (512.0, 156.7980) | (512.0, 156.3624) | 0.4356 | (768,235) | (768,235) | Yes | UNKNOWN | UNKNOWN |
| 3 | 1000 | 26456 | 26454 | (768.0, 563.1624) | (768.0, 563.5979) | 0.4356 | (1152,845) | (1152,845) | Yes | UNKNOWN | UNKNOWN |
| 4 | 1000 | 26865 | 26863 | (512.0, 156.8772) | (512.0, 156.4416) | 0.4356 | (768,235) | (768,235) | Yes | UNKNOWN | UNKNOWN |
| 5 | 1000 | 27138 | 27136 | (768.0, 563.2416) | (768.0, 563.6772) | 0.4356 | (1152,845) | (1152,846) | No | UNKNOWN | UNKNOWN |
| 6 | 1001 | 52365 | 52361 | (640.0, 718.2600) | (640.0, 720.0) | 1.7400 | (960,1077) | (960,1080) | No | UNKNOWN | UNKNOWN |
| 7 | 1000 | 71320 | 71317 | (1070.5585, 611.2614) | (1070.5528, 611.3307) | 0.0695 | (1606,917) | (1606,917) | Yes | UNKNOWN | UNKNOWN |
| 8 | 1000 | 72002 | 72000 | (1072.0, 576.0) | (1071.99998, 575.86614) | 0.1339 | (1608,864) | (1608,864) | Yes | UNKNOWN | UNKNOWN |
| 9 | 1000 | 72274 | 72272 | (927.3857, 557.1995) | (927.3826, 557.1522) | 0.0474 | (1391,836) | (1391,836) | Yes | UNKNOWN | UNKNOWN |
| 10 | 1000 | 72547 | 72545 | (783.4520, 563.4502) | (783.4521, 563.4504) | 0.0001 | (1175,845) | (1175,845) | Yes | UNKNOWN | UNKNOWN |
| 11 | 1000 | 73366 | 73363 | (927.3854, 594.8050) | (927.3795, 594.8948) | 0.0900 | (1391,892) | (1391,892) | Yes | UNKNOWN | UNKNOWN |
| 12 | 1000 | 73911 | 73909 | (1071.0747, 604.2600) | (1071.0794, 604.1875) | 0.0727 | (1607,906) | (1607,906) | Yes | UNKNOWN | UNKNOWN |
| 13 | 1000 | 74729 | 74727 | (1070.3562, 538.3499) | (1070.3562, 538.3496) | 0.0003 | (1606,808) | (1606,808) | Yes | UNKNOWN | UNKNOWN |
| 14 | 1000 | 75002 | 75000 | (927.3834, 557.1639) | (927.3864, 557.2107) | 0.0469 | (1391,836) | (1391,836) | Yes | UNKNOWN | UNKNOWN |
| 15 | 1000 | 75274 | 75272 | (783.9999, 575.9668) | (784.0, 576.0) | 0.0332 | (1176,864) | (1176,864) | Yes | UNKNOWN | UNKNOWN |
| 16 | 1003 | 76775 | 76772 | (209.4428, 611.2776) | (209.4484, 611.3458) | 0.0685 | (314,917) | (314,917) | Yes | UNKNOWN | UNKNOWN |
| 17 | 1003 | 77320 | 77317 | (352.2128, 587.0686) | (352.2075, 586.9315) | 0.1372 | (528,881) | (528,880) | No | UNKNOWN | UNKNOWN |
| 18 | 1003 | 78138 | 78135 | (496.5148, 563.8346) | (496.5139, 563.8456) | 0.0110 | (745,846) | (745,846) | Yes | UNKNOWN | UNKNOWN |
| 19 | 1003 | 78956 | 78953 | (352.0011, 575.1933) | (352.0011, 575.2179) | 0.0246 | (528,863) | (528,863) | Yes | UNKNOWN | UNKNOWN |
| 20 | 1001 | 116319 | 116317 | (1088.0, 560.3755) | (1088.0, 560.2723) | 0.1031 | (1632,841) | (1632,840) | No | UNKNOWN | UNKNOWN |
| 21 | 1001 | 116593 | 116591 | (788.48, 591.7370) | (788.48, 591.6339) | 0.1031 | (1183,888) | (1183,887) | No | UNKNOWN | UNKNOWN |
| 22 | 1000 | 117547 | 117545 | (490.24, 549.0319) | (490.24, 548.9663) | 0.0656 | (735,824) | (735,823) | No | UNKNOWN | UNKNOWN |
| 23 | 1000 | 118502 | 118498 | (788.48, 609.8042) | (788.48, 609.7093) | 0.0949 | (1183,915) | (1183,915) | Yes | UNKNOWN | UNKNOWN |
| 24 | 1001 | 118774 | 118772 | (490.24, 609.7194) | (490.24, 609.7543) | 0.0349 | (735,915) | (735,915) | Yes | UNKNOWN | UNKNOWN |
| 25 | 1000 | 119320 | 119317 | (788.48, 542.2975) | (788.48, 542.2300) | 0.0675 | (1183,813) | (1183,813) | Yes | UNKNOWN | UNKNOWN |
| 26 | 1000 | 119729 | 119727 | (1088.0, 602.9809) | (1088.0, 603.0450) | 0.0641 | (1632,904) | (1632,905) | No | UNKNOWN | UNKNOWN |
| 27 | 1000 | 120684 | 120680 | (192.0, 542.2011) | (192.0, 542.2975) | 0.0964 | (288,813) | (288,813) | Yes | UNKNOWN | UNKNOWN |
| 28 | 1000 | 120956 | 120954 | (490.24, 609.7261) | (490.24, 609.7595) | 0.0334 | (735,915) | (735,915) | Yes | UNKNOWN | UNKNOWN |
| 29 | 1001 | 121502 | 121499 | (1088.0, 560.1587) | (1088.0, 560.3567) | 0.1980 | (1632,840) | (1632,841) | No | UNKNOWN | UNKNOWN |
| 30 | 1001 | 121910 | 121908 | (788.48, 548.9326) | (788.48, 548.9944) | 0.0618 | (1183,823) | (1183,823) | Yes | UNKNOWN | UNKNOWN |
| 31 | 1001 | 122183 | 122181 | (490.24, 540.0034) | (490.24, 540.0008) | 0.0027 | (735,810) | (735,810) | Yes | UNKNOWN | UNKNOWN |
| 32 | 1001 | 122866 | 122863 | (192.0, 542.2352) | (192.0, 542.3042) | 0.0690 | (288,813) | (288,813) | Yes | UNKNOWN | UNKNOWN |
| 33 | 1000 | 123138 | 123136 | (788.48, 591.7809) | (788.48, 591.6808) | 0.1001 | (1183,888) | (1183,888) | Yes | UNKNOWN | UNKNOWN |
| 34 | 1000 | 123684 | 123681 | (1088.0, 560.1760) | (1088.0, 560.3755) | 0.1995 | (1632,840) | (1632,841) | No | UNKNOWN | UNKNOWN |
| 35 | 1001 | 124092 | 124090 | (490.24, 549.0638) | (490.24, 548.9944) | 0.0694 | (735,824) | (735,823) | No | UNKNOWN | UNKNOWN |
| 36 | 1001 | 125319 | 125315 | (192.0, 559.9517) | (192.0, 560.2363) | 0.2846 | (288,840) | (288,840) | Yes | UNKNOWN | UNKNOWN |
| 37 | 1000 | 125866 | 125863 | (788.48, 542.2772) | (788.48, 542.2142) | 0.0630 | (1183,813) | (1183,813) | Yes | UNKNOWN | UNKNOWN |
| 38 | 1001 | 126274 | 126272 | (192.0, 603.0450) | (192.0, 602.9809) | 0.0641 | (288,905) | (288,904) | No | UNKNOWN | UNKNOWN |
| 39 | 1000 | 126956 | 126953 | (1088.0, 591.8930) | (1088.0, 591.6995) | 0.1935 | (1632,888) | (1632,888) | Yes | UNKNOWN | UNKNOWN |
| 40 | 1000 | 127502 | 127499 | (192.0, 560.1587) | (192.0, 560.3567) | 0.1980 | (288,840) | (288,841) | No | UNKNOWN | UNKNOWN |
| 41 | 1001 | 128047 | 128044 | (1088.0, 560.1156) | (1088.0, 560.3098) | 0.1943 | (1632,840) | (1632,840) | Yes | UNKNOWN | UNKNOWN |
| 42 | 1001 | 128593 | 128590 | (192.0, 591.8327) | (192.0, 591.6339) | 0.1987 | (288,888) | (288,887) | No | UNKNOWN | UNKNOWN |
| 43 | 1001 | 140456 | 140454 | (783.9998, 575.7592) | (783.9997, 575.6933) | 0.0659 | (1176,864) | (1176,864) | Yes | UNKNOWN | UNKNOWN |
| 44 | 1001 | 141002 | 140999 | (927.8153, 586.3137) | (927.8070, 586.5429) | 0.2294 | (1392,879) | (1392,880) | No | UNKNOWN | UNKNOWN |

Summary of the table (SIM + ASSUMED):
- Final integer coordinates are equal for 30 of 44 rows and differ for 14 rows rows 5, 6, 17, 20, 21, 22, 26, 29, 34, 35, 38, 40, 42, 44.
- Row 6 differs by 3 px on y (1077 vs 1080), because logical Y=720 maps to the screen edge. The other 13 differing rows differ by 1 px on one axis.
- Previous events are all MOVE, not DOWN. The 44 UP events are not preceded by a DOWN in these rows.

## 4. Error and ordering analysis

Ordering:
- Events are emitted by `sorted(ans.items())`. Timestamps are unique keys, so no two batches share a timestamp. Within one timestamp, list order is preserved (SRC). Same-timestamp conflicts (e.g., a MOVE and an UP at the same time) therefore depend on the order Algo3 inserted them (SRC). This was not measured.
- Each UP in the 44-set is at most 4 ms after its previous MOVE (SIM). This is below the 50 ms late-filter threshold and below `LOOKAHEAD_MS = 120`, so the UP itself is never subject to the MOVE drop.

LOOKAHEAD_MS:
- The submit loop enqueues batches up to 120 ms before their time (SRC). This means queue depth at steady state is roughly 120 ms of batches. Not measured.

Late MOVE filter:
- Triggers only when `wait < -0.05` s, i.e., batch is more than 50 ms late (SRC).
- DOWN and UP are never filtered (SRC). MOVE is the only filtered action.
- Consequence: a late batch containing a MOVE followed by an UP will send the UP and drop the MOVE. Pointer lifecycle stays closed (UP is kept), but the final UP coordinate is then not preceded by the MOVE that would have moved the pointer there (SRC reasoning, UNKNOWN effect on device).
- Runtime log shows 0 MOVE drops (log). So this path did not occur in the logged run.

Error handling:
- `_loop` catches `OSError` only. On `OSError` it sets `running=False` and returns. Any remaining queued batches are abandoned; the outer loop's `finally` calls `sender.stop()` (SRC).
- Any non-`OSError` exception raised inside `_loop` (e.g., `struct.error` from an out-of-range coordinate) is NOT caught in `_loop`. It would kill the sender thread silently (threading prints a traceback to stderr, which is not captured in the log file path shown).
- Outer dispatch loop `try: ... except Exception: pass` (SRC). Any exception from `submit`, `next(ans_iter)`, or the rescale path is silently swallowed. The `finally` still runs, so the printed message "因迟到丢弃 MOVE N 个" can appear even if sends failed.
- Therefore a run can look normal in the log while the sender thread has already exited. This is a hidden-failure path (SRC reasoning, not observed).
- `_send_touch` has no try/except. `sendall` raising `OSError` propagates to `_loop`. Non-OSError exceptions are not caught there.
- The user log contained two benign `OSError(9)` thread exits (from prior session). These correspond to a closed socket, meaning sendall was attempted after close (log, prior session). This is consistent with `_loop` catching OSError and returning.

Pointer lifecycle under send failure:
- If `sendall` fails mid-batch, `_loop` returns after the failing event. Later events in that batch and all later batches are never sent. The pointers stay down on the device (device state UNKNOWN; no release is sent). Algo3 state is unaffected because it already generated the full list. This can leave the device with open pointers. Not observed.
- Since `running=False` stops `_loop`, no subsequent UP is sent for these pointers.

## 5. Pointer lifecycle consistency

From SIM (generation only):
- PID 1000: DOWN 259, MOVE 2705, UP 259.
- PID 1001: DOWN 258, MOVE 1612, UP 258.
- PID 1002: DOWN 13, MOVE 92, UP 13.
- PID 1003: DOWN 94, MOVE 1240, UP 94.
- PID 1004: DOWN 5, MOVE 21, UP 5.
- Total DOWN 629 = total UP 629. Each DOWN is matched to one UP in generation order (SIM).
- No orphan UP, no duplicate UP without DOWN, no open pointer at end of solve (SIM).

Dispatch-level consistency (SRC reasoning, not measured):
- Because the late filter never drops DOWN or UP, a lifecycle stays closed in the dispatch stream unless the sender thread exits early.
- If the sender exits early, every pointer open at that moment remains open on the device. This is the main lifecycle-inconsistency risk. Not observed in the logged run (log shows no sender_error record; the two OSError(9) lines are from prior runs).

## 6. Three coordinate states

Per pointer, tracked independently.

| State | Definition | Status |
|---|---|---|
| last_generated_pos | last DOWN/MOVE position produced by Algo3 for this pointer | Defined and measured (SIM) |
| last_dispatched_pos | last position passed to `ctl.touch` for this pointer | Not measured. Source shows `ctl.touch` receives the rescaled value of each event in order (SRC). Equal to last_generated_pos after transform, except when the late filter drops MOVEs in that batch |
| last_socket_send_success_pos | last position for which `sendall` returned without raising | UNKNOWN. Not instrumented. Source shows sendall is called once per event (SRC) |

Divergence conditions (SRC reasoning):
- last_dispatched_pos diverges from last_generated_pos when the late filter drops MOVE events. Observed count in log: 0. Not observed.
- last_socket_send_success_pos diverges from last_dispatched_pos when `sendall` raises or the sender thread exits before reaching an event. Not observed.
- Successful `sendall` does NOT imply device receipt. The protocol has no touch acknowledgement (SRC), so device_received is UNKNOWN for every state.
- No `last_device_received_pos` is introduced: the protocol offers no evidence for it (SRC).

## 7. Confirmed findings vs UNKNOWN findings

Confirmed (SRC or SIM):
1. 44 UP events have logical coordinates that differ from the previous generated MOVE for the same pointer; all 44 previous events are MOVE (SIM).
2. The UP coordinate equals `pointer.note.pos` at generation for all 44 (SIM, prior round).
3. Dispatch rescales each event in place once; no list object is shared across timestamps (SRC, SIM).
4. After assumed-device transform, final integer coordinates are equal for 30 of 44 rows and differ by 1 px on one axis for 13 rows (row 6 differs by 3 px on y) (SIM + ASSUMED device).
5. DOWN and UP are never removed by the late MOVE filter (SRC).
6. `_loop` catches only OSError; outer loop catches all Exception silently (SRC).
7. Runtime log for the inspected run reports 0 late MOVE drops (log).
8. DOWN 629 = UP 629 at generation (SIM).

UNKNOWN:
1. Whether each UP `ctl.touch` call was actually invoked at runtime.
2. Whether any `sendall` raised in the inspected run.
3. Whether the Android device received any event, including all 44 UP events.
4. Whether the game processed any UP coordinate, or whether UP coordinate affects judgement.
5. Whether the assumed device size and mirror setting match the real run (ASSUMED).
6. Whether same-timestamp ordering in real runs matches the simulation.
7. Whether the immediate-mode dispatch path behaves identically to sync-mode (not traced in full).
8. Whether any sender-thread non-OSError exception occurred (traceback goes to stderr, not captured in evidence).

## 8. Recommendations for the next experiment

These are proposals only. None has been validated, and none is authorised for execution in this round.

1. Read-only runtime instrumentation (no behaviour change): log, per event, a sequence ID, `ctl.touch` call entry and exit, and whether `sendall` returned or raised. Record the 44 UP events by sequence ID. Confirm the UP send is invoked and sendall succeeds. This separates "dispatched" and "socket_send_success" from "generated".
2. Record sender-thread exit reason and count of events remaining in the queue at exit, to test the hidden-failure path in Section 4.
3. Record the actual device size and mirror setting for the run, so the ASSUMED transform can be replaced by measured values.
4. Do not change `except Exception: pass` until instrumentation shows whether it hides any failure. Propose logging rather than silent swallow, as a later step.
5. Do not change UP coordinates until the judgement experiment (P1 audit Section 7) shows whether UP position matters. Candidate designs A/B/C from the previous audit remain unvalidated.
6. Compare runs with instrumentation enabled and disabled to confirm instrumentation itself does not change timing (late-filter counts).

## 9. Status

Audit complete for the scope above. No files were changed other than this report. Waiting for review before any further step.
