# PHASE2 Fix Report

Scope: fix findings F1–F8 from `diags/1211202605/ANALYSIS_REPORT.md`.
Phase 1 data (`diags/1211202605`) was read only and is unchanged (md5 verified).

## Changes by finding

| ID | Finding | Change | Where |
|----|---------|--------|-------|
| F1 | Timestamps null for all events | Logcat now uses `-v threadtime`. The device timestamp is parsed as a naive datetime. It is not labelled UTC. `receive_time` stays timezone-aware UTC. | `logcat_monitor.py` (`_build_command`, `_parse_adb_output`, `_read_loop`) |
| F2 | PID missing for lifecycle events | PID, TID, priority, and tag are read from threadtime fields and stored on `ParsedEvent`. PID is no longer guessed from message text. Old process-format lines give `None`. | `logcat_monitor.py`, `event_parser.py` |
| F3 | FIFO pairing ignores PID | `get_lifecycle_pairs` pairs per PID. It returns `unpaired_creates` and `unpaired_destroys` with no leak claim. | `event_parser.py` |
| F4 | False Error matches | Error uses logcat priority E/F/A when available. Text fallback excludes `error 0`, `EGL_SUCCESS`, `_SUCCESS`. | `event_parser.py` |
| F5 | `SecurityException` was Unknown | New `EXCEPTION_LOG` type with a case-sensitive `*Exception`/`*Error` class-name pattern. | `event_parser.py` |
| F6 | `\bDebug\b` text risk | Debug uses priority `D` when available. Text match is a fallback only. | `event_parser.py` |
| F7 | Device blank in report | `get_device_info` reads `ro.product.model` and `ro.build.version.release` per property. Failures are recorded in `errors`. Saved in session `device_info`. | `logcat_monitor.py`, `experiment.py`, `ui/main_window.py`, `report_exporter.py` |
| F8 | Unmatched rules | Rules were checked against real samples. Regexes were not broadened to force matches. | `event_parser.py` |

Report wording changed from "Create/Destruct Pairs" to "Matched pairs (same PID)" with separate unpaired counts.

## Tests

File: `tests/test_phase2.py` (stdlib `unittest`; pytest is not installed).

Run:

    QT_QPA_PLATFORM=offscreen ../venv/bin/python -m unittest discover -s tests -v

Result: 21 tests, 21 passed.

Coverage: threadtime field extraction, non-threadtime lines, `-v threadtime` in the command, naive device timestamp, PID/TID on events, no PID guessing, per-PID pairing, destructor-before-constructor, Error/Exception/Debug rules, device-info success and failure, and read-only regression on `diags/1211202605/raw_logs.txt`.

Regression note: on the Phase 1 raw log, exactly one line is still ERROR_LOG: `E( 643) Error adding epoll events ... Bad file descriptor`. This is a genuine error line and is expected.

GUI smoke test: `MainWindow` constructs offscreen and accepts the new 4-argument signal.

## Known limits

- Phase 1 data has no threadtime fields. Its PID, TID, and device timestamp stay unavailable. It is not re-timed.
- The `Error` text fallback applies only when no priority is known.
- Device model and Android version depend on `adb` being reachable at connect time. Failures are recorded, not hidden.
- Lifecycle counts are observations from the log. They are not leak or track-count claims.
- Not yet verified: a live logcat session on the device with threadtime output. This needs the GUI and the user's game actions (Phase D/E).
