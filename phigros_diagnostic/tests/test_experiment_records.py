"""Pytest coverage for experiment record infrastructure.

Covers: marker types, restore on startup, atomic persistence, events JSON
manual_marks, and timeline mark display.

Run from phigros_diagnostic/:
    QT_QPA_PLATFORM=offscreen ../venv/bin/python -m pytest tests/test_experiment_records.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiment import ExperimentManager, ExperimentSession  # noqa: E402
from report_exporter import ReportExporter  # noqa: E402
from timeline import ExperimentMarkWidget  # noqa: E402


def _mark(mtype, notes="", mid=None):
    return {
        "type": mtype,
        "notes": notes,
        "timestamp": "2025-01-01T00:00:00+00:00",
        "id": mid or f"manual_{mtype}_{notes}",
    }


# ---------- Task 5: marker types ----------

def test_first_audio_peak_type_present_and_distinct():
    types = ExperimentMarkWidget.EXPERIMENT_TYPES
    assert "FIRST_AUDIO_PEAK" in types
    assert "GAMEPLAY_AUDIO_STARTED" in types
    assert types.index("FIRST_AUDIO_PEAK") != types.index("GAMEPLAY_AUDIO_STARTED")
    assert types[-1] == "Other"


def test_first_audio_peak_filter_does_not_match_gameplay_audio():
    mgr = ExperimentManager()
    s = mgr.create_session("t")
    s.add_manual_mark(_mark("FIRST_AUDIO_PEAK", mid="a"))
    s.add_manual_mark(_mark("GAMEPLAY_AUDIO_STARTED", mid="b"))
    peaks = [e for e in s.get_timeline() if e.get("label") == "[FIRST_AUDIO_PEAK]"]
    assert len(peaks) == 1


# ---------- Task 2 / 3: persistence and restore ----------

def test_save_then_restore_roundtrip(tmp_path):
    path = str(tmp_path / "sessions.json")
    mgr = ExperimentManager()
    s = mgr.create_session("roundtrip")
    s.add_manual_mark(_mark("Play Start", "n1", mid="m1"))
    mgr.save_sessions_to_json(path)

    mgr2 = ExperimentManager()
    assert mgr2.load_sessions_from_json(path) == 1
    restored = mgr2.sessions[s.session_id]
    assert restored.manual_marks[0]["id"] == "m1"
    assert restored.manual_marks[0]["notes"] == "n1"


def test_missing_file_restores_nothing(tmp_path):
    mgr = ExperimentManager()
    assert mgr.load_sessions_from_json(str(tmp_path / "nope.json")) == 0
    assert mgr.sessions == {}


def test_corrupt_file_raises_and_is_not_overwritten(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text("{not valid json", encoding="utf-8")
    mgr = ExperimentManager()
    with pytest.raises(ValueError):
        mgr.load_sessions_from_json(str(path))
    assert path.read_text(encoding="utf-8") == "{not valid json"
    assert mgr.sessions == {}


def test_bad_structure_raises(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({"sessions": [{"no_id": True}]}), encoding="utf-8")
    mgr = ExperimentManager()
    with pytest.raises(ValueError):
        mgr.load_sessions_from_json(str(path))
    assert mgr.sessions == {}


def test_failed_save_keeps_memory_and_no_partial_file(tmp_path, monkeypatch):
    path = str(tmp_path / "sessions.json")
    mgr = ExperimentManager()
    s = mgr.create_session("keep")
    s.add_manual_mark(_mark("Pause", mid="keep1"))

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("experiment.json.dump", boom)
    with pytest.raises(OSError):
        mgr.save_sessions_to_json(path)

    # In-memory data untouched
    assert len(mgr.sessions[s.session_id].manual_marks) == 1
    # No target file and no leftover temp file
    assert not os.path.exists(path)
    assert [p for p in os.listdir(tmp_path) if p.endswith(".tmp")] == []


def test_failed_save_preserves_previous_good_file(tmp_path, monkeypatch):
    path = str(tmp_path / "sessions.json")
    mgr = ExperimentManager()
    mgr.create_session("first")
    mgr.save_sessions_to_json(path)
    good = open(path, encoding="utf-8").read()

    mgr.create_session("second")
    monkeypatch.setattr("experiment.json.dump", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        mgr.save_sessions_to_json(path)
    assert open(path, encoding="utf-8").read() == good


# ---------- Task 4: events JSON includes manual marks ----------

def _exporter_with_session(tmp_path, marks):
    mgr = ExperimentManager()
    s = mgr.create_session("export")
    for m in marks:
        s.add_manual_mark(m)
    return ReportExporter(mgr), s


def test_events_json_contains_manual_marks_with_required_fields(tmp_path):
    marks = [_mark("Play Start", "x", mid="id1")]
    exporter, s = _exporter_with_session(tmp_path, marks)
    out = exporter.export_events_json(str(tmp_path / "e.json"))
    data = json.load(open(out, encoding="utf-8"))
    assert "events" in data  # existing key kept
    assert len(data["manual_marks"]) == 1
    m = data["manual_marks"][0]
    for key in ("id", "type", "notes", "timestamp", "session_id"):
        assert key in m
    assert m["session_id"] == s.session_id
    assert m["id"] == "id1"


def test_events_json_empty_manual_marks_for_old_session(tmp_path):
    exporter, _ = _exporter_with_session(tmp_path, [])
    out = exporter.export_events_json(str(tmp_path / "e.json"))
    data = json.load(open(out, encoding="utf-8"))
    assert data["manual_marks"] == []


# ---------- Task 1: timeline display (Qt, offscreen) ----------

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_timeline_marks_table_rebuilds_without_duplicates(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from ui.main_window import MainWindow
    # Keep tests from writing into the real experiment_data dir or opening modal dialogs
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    win = MainWindow()
    try:
        s = win.experiment_mgr.create_session("ui")
        win.on_manual_mark_added(_mark("Pause", "a", mid="u1"))
        win.on_manual_mark_added(_mark("Resume", "b", mid="u2"))
        win.refresh_timeline_marks()
        win.refresh_timeline_marks()
        assert win.marks_table.rowCount() == 2
        assert win.marks_table.item(0, 1).text() == "Pause"
        assert win.marks_table.item(1, 3).text() == "u2"
    finally:
        win.close()


# ---------- Corrupt-file save protection (Qt, offscreen) ----------

def _corrupt_window(tmp_path, monkeypatch, qapp, answer):
    from PySide6.QtWidgets import QMessageBox
    from ui.main_window import MainWindow
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "experiment_data"
    data_dir.mkdir()
    (data_dir / "sessions.json").write_text('{"sessions": [', encoding="utf-8")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answer)
    win = MainWindow()
    return win, data_dir / "sessions.json", warnings


def test_normal_restore_then_yes_on_close_still_saves(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QCloseEvent
    from ui.main_window import MainWindow
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win = MainWindow()
    win.experiment_mgr.create_session("normal")
    win.closeEvent(QCloseEvent())
    saved = json.loads((tmp_path / "experiment_data" / "sessions.json").read_text(encoding="utf-8"))
    assert saved["total_sessions"] == 1
    assert win.restore_error is None


def test_corrupt_then_yes_on_close_leaves_original_unchanged(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QCloseEvent
    win, path, warnings = _corrupt_window(tmp_path, monkeypatch, qapp, QMessageBox.Yes)
    original = path.read_bytes()
    win.experiment_mgr.create_session("blank-after-corrupt")
    win.closeEvent(QCloseEvent())
    assert path.read_bytes() == original
    assert any("Save Blocked" in str(a[1]) for a in warnings)


def test_corrupt_then_no_on_close_does_not_save(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QCloseEvent
    win, path, _ = _corrupt_window(tmp_path, monkeypatch, qapp, QMessageBox.No)
    original = path.read_bytes()
    called = []
    monkeypatch.setattr(win.experiment_mgr, "save_sessions_to_json", lambda *a, **k: called.append(a))
    win.experiment_mgr.create_session("x")
    win.closeEvent(QCloseEvent())
    assert called == []
    assert path.read_bytes() == original


def test_restore_error_survives_session_creation_and_marks(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    win, path, _ = _corrupt_window(tmp_path, monkeypatch, qapp, QMessageBox.No)
    original = path.read_bytes()
    assert win.restore_error
    win.experiment_mgr.create_session("new")
    win.on_manual_mark_added(_mark("Pause", "a", mid="p1"))
    assert win.restore_error
    assert path.read_bytes() == original
    assert win.save_sessions_now() is False


def test_save_block_keeps_memory_sessions(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    win, _, _ = _corrupt_window(tmp_path, monkeypatch, qapp, QMessageBox.No)
    s = win.experiment_mgr.create_session("memory-only")
    win.on_manual_mark_added(_mark("Resume", "b", mid="r1"))
    assert win.experiment_mgr.get_current_session() is s
    assert len(s.manual_marks) == 1
    assert win.marks_table.rowCount() == 1
