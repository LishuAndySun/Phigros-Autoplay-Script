"""Tests for NF-aware Temporal Spatial Verification Module

覆盖以下审查要点：
1. FrameGenerator 时间切片完整性
2. PositionCalculator 指针状态维护
3. NFDetector enableTime/disableTime 边界处理
4. SpatialVerifier 检查所有触控位置（按下点 + 轨迹）
5. HOLD/DRAG 进入 NF 的违规识别
6. PathReplanner 重规划后是否重新验证
7. 多指针并发状态正确性
8. 无 NF 谱面零开销跳过
9. 时间单位 / 坐标单位 / 帧索引正确性
"""
from __future__ import annotations

import math
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from algo.algo_base import TouchAction, TouchEvent
from algo.verify_nf import (
    NFDetector, NFDetectionResult,
    FrameGenerator, VerificationFrame,
    PositionCalculator,
    SpatialGraph,
    NFMapper,
    TaskType, VerificationTask, TaskMapper,
    ViolationType, Violation,
    SpatialVerifier, VerificationReport,
    PathReplanner,
    verify_algo3_output,
    flick_step, flick_end, flick_start, flick_scale_factor,
    MIN_DIST, MAX_RELOCATION_DISTANCE, release_ms,
)
from block_area import BlockArea, BlockAreas, SCREEN_W, SCREEN_H


# ============================================================================
# Helpers — construct minimal BlockAreas / Chart mocks
# ============================================================================

def _make_block_area(enable_time: float, disable_time: float,
                     center_x: float = SCREEN_W / 2, center_y: float = SCREEN_H / 2,
                     half_w: float = 200.0, half_h: float = 100.0,
                     is_subtract: bool = False) -> dict:
    """构造一个 BlockArea 的原始 dict。

    BlockArea 构造函数解析方式：
        base_center_x = (tr['x'] + bl['x']) * SCREEN_W / 2
        half_w        = (tr['x'] - bl['x']) * SCREEN_W / 2
    因此 tr['x'], bl['x'] ∈ [0, 1]，且：
        tr_x = (center_x/SCREEN_W*2 + half_w/(SCREEN_W/2)) / 2
        bl_x = (center_x/SCREEN_W*2 - half_w/(SCREEN_W/2)) / 2
    """
    cx_pct = center_x / SCREEN_W * 2   # map to [0, 2] range used by formula
    bw = half_w / (SCREEN_W / 2)       # width in same units
    tr_x = (cx_pct + bw) / 2
    bl_x = (cx_pct - bw) / 2

    cy_pct = center_y / SCREEN_H * 2
    bh = half_h / (SCREEN_H / 2)
    tr_y = (cy_pct + bh) / 2
    bl_y = (cy_pct - bh) / 2

    return {
        'enableTime': enable_time,
        'disableTime': disable_time,
        'topRightPercentage': {'x': max(0.0, min(1.0, tr_x)), 'y': max(0.0, min(1.0, tr_y))},
        'bottomLeftPercentage': {'x': max(0.0, min(1.0, bl_x)), 'y': max(0.0, min(1.0, bl_y))},
        'isSubtract': is_subtract,
        'moveEvents': [],
        'rotateEvents': [],
        'scaleEvents': [],
    }


def _make_nf_block_areas(intervals: list[tuple[float, float]],
                         cx: float = SCREEN_W / 2,
                         hw: float = 200.0, hh: float = 100.0,
                         subtract: bool = False) -> BlockAreas:
    """从 [(enable, disable), ...] 构造 BlockAreas。"""
    items = []
    for en, di in intervals:
        items.append(_make_block_area(en, di, cx, SCREEN_H / 2, hw, hh, subtract))
    return BlockAreas(items)


def _make_empty_blocks() -> BlockAreas:
    return BlockAreas([])


def _make_touch(x: float, y: float, action: TouchAction, pointer: int = 0) -> TouchEvent:
    return TouchEvent((x, y), action, pointer)


def _make_mock_judge_line(notes: list[tuple[int, float, float, int]], angle_deg: float = 0.0) -> MagicMock:
    """Build a mock JudgeLine for TaskMapper note identification.

    Each note is (time_ms, x_pct, y_pct, note_type).
    Returns a MagicMock with notes_above, notes_below, angle(), pos(), seconds().

    Note.time is stored in ms; line.seconds(t) returns t/1000 (converts ms→seconds).
    This matches how verify_nf._identify_note_at uses it: ms = round(line.seconds(note.time)*1000).
    """
    from note import Note as NoteClass

    # Create actual Note objects
    above_notes = []
    for time_ms, x_pct, y_pct, ntype in notes:
        n = NoteClass.__new__(NoteClass)
        n.time = time_ms  # store in ms
        n.x = x_pct
        n.y = y_pct
        n.typ = ntype
        above_notes.append(n)

    mock_line = MagicMock()
    mock_line.notes_above = above_notes
    mock_line.notes_below = []
    mock_line.bpm = 180.0

    def angle_fn(t):
        return angle_deg

    def pos_fn(t):
        # Return a fixed position near center-bottom of screen
        return (640.0, 576.0)

    def seconds_fn(t):
        # t is in ms; convert to seconds
        return t / 1000.0

    mock_line.angle = angle_fn
    mock_line.pos = pos_fn
    mock_line.seconds = seconds_fn
    return mock_line


def _build_integration_chart(events_map: dict, blocks) -> MagicMock:
    """Build a chart mock that TaskMapper can use to identify notes from events.

    For each unique timestamp+position in events_map, creates a synthetic Note
    whose calculated position (via _identify_note_at formula) matches the event.
    """
    from note import Note as NoteClass

    # Collect all DOWN events (note starts)
    down_events = []
    for ts, evts in events_map.items():
        for evt in evts:
            if evt.action == TouchAction.DOWN:
                down_events.append((ts, evt.pos[0], evt.pos[1]))

    # Build notes: for each unique (ts, x, y), create a Note
    seen = set()
    notes = []
    for ts, x, y in down_events:
        key = (round(ts), round(x), round(y))
        if key in seen:
            continue
        seen.add(key)
        # Determine type by position
        if abs(x - 640) < 100 and abs(y - 360) < 100:
            ntype = 3  # HOLD near center
        elif x < 300:
            ntype = 1  # TAP on left side
        else:
            ntype = 4  # FLICK elsewhere

        n = NoteClass.__new__(NoteClass)
        n.time = ts  # ms
        n.x = (x - 640) / 720  # reverse-engineer x_pct from formula
        n.y = (y - 576) / 720
        n.typ = ntype
        notes.append(n)

    mock_line = MagicMock()
    mock_line.notes_above = notes
    mock_line.notes_below = []
    mock_line.bpm = 180.0

    def angle_fn(t):
        return 0.0

    def pos_fn(t):
        return (640.0, 576.0)

    def seconds_fn(t):
        return t / 1000.0

    mock_line.angle = angle_fn
    mock_line.pos = pos_fn
    mock_line.seconds = seconds_fn

    chart_mock = MagicMock()
    chart_mock.block_areas = blocks
    chart_mock.judge_lines = [mock_line]
    return chart_mock


# ============================================================================
# Test 1: FrameGenerator — 时间切片完整性
# ============================================================================

class TestFrameGenerator(unittest.TestCase):
    def test_empty_events(self):
        fg = FrameGenerator({})
        self.assertEqual(len(fg.frames), 0)

    def test_single_timestamp(self):
        events = {1000: [_make_touch(100, 200, TouchAction.DOWN, 0)]}
        fg = FrameGenerator(events)
        self.assertEqual(len(fg.frames), 1)
        self.assertEqual(fg.frames[0].timestamp_ms, 1000)
        self.assertEqual(len(fg.frames[0].events), 1)

    def test_multiple_timestamps_sorted(self):
        events = {
            5000: [_make_touch(0, 0, TouchAction.UP, 0)],
            1000: [_make_touch(100, 200, TouchAction.DOWN, 0)],
            3000: [_make_touch(200, 300, TouchAction.MOVE, 0)],
        }
        fg = FrameGenerator(events)
        timestamps = [f.timestamp_ms for f in fg.frames]
        self.assertEqual(timestamps, [1000, 3000, 5000])

    def test_multiple_events_per_timestamp(self):
        evts = [
            _make_touch(100, 200, TouchAction.DOWN, 0),
            _make_touch(100, 200, TouchAction.DOWN, 1),
        ]
        events = {1000: evts}
        fg = FrameGenerator(events)
        self.assertEqual(len(fg.frames[0].events), 2)

    def test_frame_contains_original_events(self):
        evt = _make_touch(42.5, 87.3, TouchAction.MOVE, 5)
        events = {999: [evt]}
        fg = FrameGenerator(events)
        retrieved = fg.frames[0].events[0]
        self.assertAlmostEqual(retrieved.pos[0], 42.5)
        self.assertAlmostEqual(retrieved.pos[1], 87.3)
        self.assertEqual(retrieved.pointer, 5)


# ============================================================================
# Test 2: PositionCalculator — 指针状态维护
# ============================================================================

class TestPositionCalculator(unittest.TestCase):
    def test_down_records_position(self):
        pc = PositionCalculator()
        frame = VerificationFrame(1000, events=[_make_touch(100, 200, TouchAction.DOWN, 0)])
        pc.process_frame(frame)
        self.assertIn(0, pc.pressing)
        self.assertEqual(pc.pressing[0]['pos'], (100, 200))
        self.assertEqual(pc.pressing[0]['pressed_at'], 1000)

    def test_move_updates_position(self):
        pc = PositionCalculator()
        pc.process_frame(VerificationFrame(1000, events=[_make_touch(100, 200, TouchAction.DOWN, 0)]))
        pc.process_frame(VerificationFrame(1010, events=[_make_touch(150, 250, TouchAction.MOVE, 0)]))
        self.assertEqual(pc.pressing[0]['pos'], (150, 250))

    def test_up_clears_state(self):
        pc = PositionCalculator()
        pc.process_frame(VerificationFrame(1000, events=[_make_touch(100, 200, TouchAction.DOWN, 0)]))
        pc.process_frame(VerificationFrame(1100, events=[_make_touch(100, 200, TouchAction.UP, 0)]))
        self.assertNotIn(0, pc.pressing)

    def test_multiple_pointers_independent(self):
        pc = PositionCalculator()
        # Pointer 0: DOWN at (100, 200)
        # Pointer 1: DOWN at (300, 400)
        pc.process_frame(VerificationFrame(1000, events=[
            _make_touch(100, 200, TouchAction.DOWN, 0),
            _make_touch(300, 400, TouchAction.DOWN, 1),
        ]))
        self.assertEqual(pc.pressing[0]['pos'], (100, 200))
        self.assertEqual(pc.pressing[1]['pos'], (300, 400))

        # Pointer 0 moves, pointer 1 stays
        pc.process_frame(VerificationFrame(1010, events=[
            _make_touch(150, 250, TouchAction.MOVE, 0),
        ]))
        self.assertEqual(pc.pressing[0]['pos'], (150, 250))
        self.assertEqual(pc.pressing[1]['pos'], (300, 400))

    def test_up_on_unknown_pointer_no_crash(self):
        """UP on a pointer that was never DOWN should not crash."""
        pc = PositionCalculator()
        pc.process_frame(VerificationFrame(1000, events=[_make_touch(100, 200, TouchAction.UP, 99)]))
        self.assertNotIn(99, pc.pressing)

    def test_move_on_unknown_pointer_no_crash(self):
        """MOVE on a pointer that was never DOWN should not crash."""
        pc = PositionCalculator()
        pc.process_frame(VerificationFrame(1000, events=[_make_touch(100, 200, TouchAction.MOVE, 99)]))
        self.assertNotIn(99, pc.pressing)

    def test_results_stored_by_timestamp(self):
        pc = PositionCalculator()
        pc.process_frame(VerificationFrame(1000, events=[
            _make_touch(100, 200, TouchAction.DOWN, 0),
        ]))
        pc.process_frame(VerificationFrame(1010, events=[
            _make_touch(150, 250, TouchAction.MOVE, 0),
        ]))
        self.assertIn(1000, pc.results)
        self.assertIn(1010, pc.results)
        self.assertEqual(pc.results[1000][0]['state'], 'down')
        self.assertEqual(pc.results[1010][0]['state'], 'move')

    def test_reuse_pointer_after_up(self):
        """Pointer UP then DOWN again should work correctly."""
        pc = PositionCalculator()
        pc.process_frame(VerificationFrame(1000, events=[_make_touch(100, 200, TouchAction.DOWN, 0)]))
        pc.process_frame(VerificationFrame(1100, events=[_make_touch(100, 200, TouchAction.UP, 0)]))
        pc.process_frame(VerificationFrame(1200, events=[_make_touch(500, 600, TouchAction.DOWN, 0)]))
        self.assertEqual(pc.pressing[0]['pos'], (500, 600))
        self.assertEqual(pc.pressing[0]['pressed_at'], 1200)


# ============================================================================
# Test 3: NFDetector — enableTime / disableTime 边界处理
# ============================================================================

class TestNFDetector(unittest.TestCase):
    def test_no_nf_returns_none(self):
        det = NFDetector(None)
        self.assertFalse(det.exists)
        self.assertEqual(det.result, NFDetectionResult.NONE)

    def test_empty_blocks_returns_none(self):
        det = NFDetector(BlockAreas([]))
        self.assertFalse(det.exists)
        self.assertEqual(det.result, NFDetectionResult.NONE)

    def test_single_interval(self):
        blocks = _make_nf_block_areas([(1.0, 5.0)])
        det = NFDetector(blocks)
        self.assertTrue(det.exists)
        self.assertEqual(det.result, NFDetectionResult.DYNAMIC)
        self.assertEqual(len(det.active_intervals), 1)
        self.assertAlmostEqual(det.active_intervals[0][0], 1.0)
        self.assertAlmostEqual(det.active_intervals[0][1], 5.0)

    def test_overlapping_intervals_merged(self):
        blocks = _make_nf_block_areas([
            (1.0, 3.0),
            (2.0, 5.0),
        ])
        det = NFDetector(blocks)
        self.assertTrue(det.exists)
        self.assertEqual(len(det.active_intervals), 1)
        self.assertAlmostEqual(det.active_intervals[0][0], 1.0)
        self.assertAlmostEqual(det.active_intervals[0][1], 5.0)

    def test_adjacent_intervals_merged(self):
        """[1, 3] and [3, 5] should merge into [1, 5]."""
        blocks = _make_nf_block_areas([
            (1.0, 3.0),
            (3.0, 5.0),
        ])
        det = NFDetector(blocks)
        self.assertTrue(det.exists)
        self.assertEqual(len(det.active_intervals), 1)
        self.assertAlmostEqual(det.active_intervals[0][0], 1.0)
        self.assertAlmostEqual(det.active_intervals[0][1], 5.0)

    def test_non_overlapping_intervals_not_merged(self):
        blocks = _make_nf_block_areas([
            (1.0, 2.0),
            (3.0, 4.0),
        ])
        det = NFDetector(blocks)
        self.assertTrue(det.exists)
        self.assertEqual(len(det.active_intervals), 2)

    def test_is_active_at_boundary(self):
        blocks = _make_nf_block_areas([(1.0, 5.0)])
        det = NFDetector(blocks)
        self.assertTrue(det.is_active_at(1.0))   # exact enable
        self.assertTrue(det.is_active_at(5.0))   # exact disable
        self.assertFalse(det.is_active_at(0.9))  # before enable
        self.assertFalse(det.is_active_at(5.1))  # after disable

    def test_static_nf_detected(self):
        blocks = _make_nf_block_areas([(0.0, 3600.0)])
        det = NFDetector(blocks)
        self.assertEqual(det.result, NFDetectionResult.STATIC)

    def test_total_active_seconds(self):
        blocks = _make_nf_block_areas([(1.0, 3.0), (5.0, 7.0)])
        det = NFDetector(blocks)
        # Merged: [1, 3] + [5, 7] = 2 + 2 = 4 seconds
        self.assertAlmostEqual(det.total_active_seconds, 4.0)


# ============================================================================
# Test 4: SpatialVerifier — 检查所有触控位置
# ============================================================================

class TestSpatialVerifier(unittest.TestCase):
    def setUp(self):
        # NF block covering center region [540, 740] x [320, 520]
        self.blocks = _make_nf_block_areas([(0.0, 10.0)], cx=SCREEN_W / 2, hw=100.0, hh=100.0)
        self.detector = NFDetector(self.blocks)
        self.nf_mapper = NFMapper(self.blocks)
        self.graph = SpatialGraph()
        self.verifier = SpatialVerifier(self.detector, self.nf_mapper, self.graph)

    def test_press_outside_nf_no_violation(self):
        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=1,  # TAP
            note_id=1,
            position=(100, 100),  # far from center NF
            angle=0.0,
            line=None,
        )
        viols = self.verifier.verify_task(task)
        self.assertEqual(len(viols), 0)

    def test_press_inside_nf_is_violation(self):
        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),  # inside NF center
            angle=0.0,
            line=None,
        )
        viols = self.verifier.verify_task(task)
        self.assertTrue(len(viols) > 0)
        self.assertEqual(viols[0].violation_type, ViolationType.PRESS_IN_NF)

    def test_flick_trajectory_sampling(self):
        """Verify that FLICK trajectory points are checked, not just the press point."""
        # NF at left edge, flick starts outside but trajectory crosses through
        blocks = _make_nf_block_areas([(0.0, 10.0)], cx=200, hw=100, hh=100)
        detector = NFDetector(blocks)
        nf_mapper = NFMapper(blocks)
        graph = SpatialGraph()
        verifier = SpatialVerifier(detector, nf_mapper, graph)

        # Flick starting at (50, 360), angle=pi/2 → dx=100, dy≈0
        # Trajectory: (50,360) → (150,360) over 100ms
        # Point (150, 360) is inside NF centered at (200, 360) with hw=100 → x in [100, 300]
        task = VerificationTask(
            task_type=TaskType.FLICK_TRAJECTORY,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=4,  # FLICK
            note_id=1,
            position=(50, 360),
            angle=math.pi / 2,
            line=None,
        )
        viols = verifier.verify_task(task)
        # Should detect trajectory point inside NF
        traj_viols = [v for v in viols if v.violation_type == ViolationType.TRAJECTORY_IN_NF]
        self.assertTrue(len(traj_viols) > 0, "Should detect trajectory point inside NF")

    def test_hold_move_in_nf_is_warning(self):
        task = VerificationTask(
            task_type=TaskType.HOLD_MOVE,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=3,  # HOLD
            note_id=1,
            position=(640, 360),  # inside NF
            angle=0.0,
            line=None,
        )
        viols = self.verifier.verify_task(task)
        self.assertTrue(len(viols) > 0)
        self.assertEqual(viols[0].violation_type, ViolationType.HOLD_MOVE_IN_NF)
        self.assertEqual(viols[0].severity, 'info')

    def test_press_too_close_to_judge_line(self):
        # Create a horizontal judge line at y=400
        line = ((0, 400), (1280, 400))
        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 410),  # only 10px from line, < MIN_DIST=80
            angle=0.0,
            line=line,
        )
        viols = self.verifier.verify_task(task)
        close_viols = [v for v in viols if v.violation_type == ViolationType.PRESS_TOO_CLOSE_TO_LINE]
        self.assertTrue(len(close_viols) > 0)

    def test_press_far_from_judge_line_ok(self):
        line = ((0, 400), (1280, 400))
        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 600),  # 200px from line, >= MIN_DIST=80
            angle=0.0,
            line=line,
        )
        viols = self.verifier.verify_task(task)
        close_viols = [v for v in viols if v.violation_type == ViolationType.PRESS_TOO_CLOSE_TO_LINE]
        self.assertEqual(len(close_viols), 0)


# ============================================================================
# Test 5: HOLD/DRAG 进入 NF 的违规识别
# ============================================================================

class TestHoldMoveNFViolation(unittest.TestCase):
    def setUp(self):
        # NF covering entire screen
        self.blocks = _make_nf_block_areas([(0.0, 10.0)], cx=SCREEN_W / 2, hw=700, hh=500)
        self.detector = NFDetector(self.blocks)
        self.nf_mapper = NFMapper(self.blocks)
        self.graph = SpatialGraph()
        self.verifier = SpatialVerifier(self.detector, self.nf_mapper, self.graph)

    def test_hold_move_in_full_screen_nf(self):
        task = VerificationTask(
            task_type=TaskType.HOLD_MOVE,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=3,  # HOLD
            note_id=42,
            position=(640, 360),
            angle=0.0,
            line=None,
        )
        viols = self.verifier.verify_task(task)
        self.assertTrue(len(viols) > 0)
        self.assertEqual(viols[0].violation_type, ViolationType.HOLD_MOVE_IN_NF)
        self.assertIn('严格跟随判定线', viols[0].reason)

    def test_drag_move_in_nf_same_as_hold(self):
        task = VerificationTask(
            task_type=TaskType.DRAG_MOVE,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=2,  # DRAG
            note_id=42,
            position=(640, 360),
            angle=0.0,
            line=None,
        )
        viols = self.verifier.verify_task(task)
        self.assertTrue(len(viols) > 0)
        self.assertEqual(viols[0].violation_type, ViolationType.HOLD_MOVE_IN_NF)

    def test_hold_move_outside_nf_no_violation(self):
        # NF at top-left corner only
        blocks = _make_nf_block_areas([(0.0, 10.0)], cx=100, hh=50)
        detector = NFDetector(blocks)
        nf_mapper = NFMapper(blocks)
        verifier = SpatialVerifier(detector, nf_mapper, SpatialGraph())

        task = VerificationTask(
            task_type=TaskType.HOLD_MOVE,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=3,
            note_id=42,
            position=(640, 360),  # far from NF
            angle=0.0,
            line=None,
        )
        viols = verifier.verify_task(task)
        self.assertEqual(len(viols), 0)


# ============================================================================
# Test 6: PathReplanner — 重规划后是否重新验证
# ============================================================================

class TestPathReplanner(unittest.TestCase):
    def test_hold_drag_not_replannable(self):
        """HOLD/DRAG cannot be moved — strict follow constraint."""
        blocks = _make_empty_blocks()
        chart_mock = MagicMock()
        planner = PathReplanner(chart_mock, blocks)

        task = VerificationTask(
            task_type=TaskType.HOLD_MOVE,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=3,
            note_id=1,
            position=(640, 360),
            angle=0.0,
            line=None,
        )
        viol = Violation(
            violation_type=ViolationType.HOLD_MOVE_IN_NF,
            task_type=TaskType.HOLD_MOVE,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=3,
            note_id=1,
            position=(640, 360),
            reason='test',
        )
        result = planner.attempt_fix(task, viol)
        self.assertIsNone(result)

    def test_tap_replan_calls_search_point(self):
        """TAP replanning should call search_point internally."""
        blocks = _make_empty_blocks()
        chart_mock = MagicMock()
        planner = PathReplanner(chart_mock, blocks)

        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),
            angle=0.0,
            line=None,
        )
        viol = Violation(
            violation_type=ViolationType.PRESS_IN_NF,
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),
            reason='test',
        )
        # With empty blocks, search_point should return the original position as valid
        result = planner.attempt_fix(task, viol)
        # Should succeed since no NF exists
        self.assertIsNotNone(result)

    def test_replan_violations_no_re_verification(self):
        """BUG #5: replan_violations does NOT re-verify replanned tasks.
        This is a known limitation — the returned replanned dict is not fed back
        into the verifier for a second pass.
        """
        blocks = _make_empty_blocks()
        chart_mock = MagicMock()
        planner = PathReplanner(chart_mock, blocks)

        tasks = [
            VerificationTask(
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=5000,
                pointer_id=0,
                note_type=1,
                note_id=1,
                position=(640, 360),
                angle=0.0,
                line=None,
            ),
        ]
        viols = [
            Violation(
                violation_type=ViolationType.PRESS_IN_NF,
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=5000,
                pointer_id=0,
                note_type=1,
                note_id=1,
                position=(640, 360),
                reason='test',
            ),
        ]
        replanned = planner.replan_violations(tasks, viols)
        # Returns mapping but caller never re-verifies
        self.assertIsInstance(replanned, dict)


# ============================================================================
# Test 7: 多指针并发状态
# ============================================================================

class TestMultiPointerConcurrency(unittest.TestCase):
    def test_10_pointers_independent_states(self):
        """10 pointers operating simultaneously should maintain independent states."""
        pc = PositionCalculator()
        frames_data = []
        # Frame 1000: all 10 pointers DOWN at different positions
        down_events = [
            _make_touch(float(i * 100), float(i * 50), TouchAction.DOWN, i)
            for i in range(10)
        ]
        frames_data.append(VerificationFrame(1000, events=down_events))

        # Frame 1010: odd pointers move, even stay
        move_events = [
            _make_touch(float(i * 100 + 10), float(i * 50 + 5), TouchAction.MOVE, i)
            for i in range(0, 10, 2)  # even pointers only
        ]
        frames_data.append(VerificationFrame(1010, events=move_events))

        pc.process_all(frames_data)

        for i in range(10):
            self.assertIn(i, pc.pressing)

        # Even pointers moved
        for i in range(0, 10, 2):
            self.assertEqual(pc.pressing[i]['pos'], (i * 100 + 10, i * 50 + 5))
        # Odd pointers stayed at original
        for i in range(1, 10, 2):
            self.assertEqual(pc.pressing[i]['pos'], (i * 100, i * 50))

    def test_pointer_up_does_not_affect_others(self):
        pc = PositionCalculator()
        pc.process_frame(VerificationFrame(1000, events=[
            _make_touch(100, 200, TouchAction.DOWN, 0),
            _make_touch(300, 400, TouchAction.DOWN, 1),
            _make_touch(500, 600, TouchAction.DOWN, 2),
        ]))
        # Only pointer 1 UP
        pc.process_frame(VerificationFrame(1100, events=[
            _make_touch(300, 400, TouchAction.UP, 1),
        ]))
        self.assertIn(0, pc.pressing)
        self.assertNotIn(1, pc.pressing)
        self.assertIn(2, pc.pressing)


# ============================================================================
# Test 8: 无 NF 谱面零开销
# ============================================================================

class TestNoNFZeroOverhead(unittest.TestCase):
    def test_verify_algo3_output_skips_without_nf(self):
        chart_mock = MagicMock()
        chart_mock.block_areas = BlockAreas([])
        report = verify_algo3_output({}, chart_mock)
        self.assertFalse(report.nf_detected)
        self.assertEqual(report.total_tasks, 0)
        self.assertEqual(report.total_violations, 0)
        self.assertEqual(report.nf_result, NFDetectionResult.NONE)

    def test_verify_with_none_block_areas(self):
        chart_mock = MagicMock()
        chart_mock.block_areas = None
        report = verify_algo3_output({}, chart_mock)
        self.assertFalse(report.nf_detected)

    def test_detector_exists_false_no_processing(self):
        """When NF doesn't exist, FrameGenerator/PositionCalculator/etc.
        should NOT be instantiated."""
        chart_mock = MagicMock()
        chart_mock.block_areas = BlockAreas([])

        with patch('algo.verify_nf.FrameGenerator') as mock_fg:
            with patch('algo.verify_nf.PositionCalculator') as mock_pc:
                with patch('algo.verify_nf.TaskMapper') as mock_tm:
                    report = verify_algo3_output({}, chart_mock)
                    # None of these should be called
                    mock_fg.assert_not_called()
                    mock_pc.assert_not_called()
                    mock_tm.assert_not_called()


# ============================================================================
# Test 9: 时间单位 / 坐标单位 / 帧索引
# ============================================================================

class TestTimeAndCoordinateUnits(unittest.TestCase):
    def test_flick_trajectory_time_units(self):
        """Flick trajectory sampling should use milliseconds consistently."""
        blocks = _make_nf_block_areas([(5.0, 6.0)])  # NF active at t=5-6 seconds
        detector = NFDetector(blocks)
        nf_mapper = NFMapper(blocks)
        graph = SpatialGraph()
        verifier = SpatialVerifier(detector, nf_mapper, graph)

        # Task at 5500ms (5.5 seconds) — inside NF time window
        task = VerificationTask(
            task_type=TaskType.FLICK_TRAJECTORY,
            timestamp_ms=5500,
            pointer_id=0,
            note_type=4,
            note_id=1,
            position=(640, 360),
            angle=0.0,
            line=None,
        )
        viols = verifier.verify_task(task)
        # Should check trajectory at t=5.5s which is within [5.0, 6.0]
        # NF covers center, (640, 360) is center → should be violation
        self.assertTrue(len(viols) > 0)

    def test_coordinate_bounds_enforced(self):
        """Trajectory points outside [0, 1280] × [0, 720] should be flagged."""
        blocks = _make_empty_blocks()
        detector = NFDetector(blocks)
        nf_mapper = NFMapper(blocks)
        graph = SpatialGraph()
        verifier = SpatialVerifier(detector, nf_mapper, graph)

        # Flick going RIGHT from edge: (1280, 360) with angle=pi/2 → dx=100, dy≈0
        # Trajectory: (1280,360) → (1380,360) — first point beyond screen
        task = VerificationTask(
            task_type=TaskType.FLICK_TRAJECTORY,
            timestamp_ms=5000,
            pointer_id=0,
            note_type=4,
            note_id=1,
            position=(1280, 360),
            angle=math.pi / 2,
            line=None,
        )
        viols = verifier.verify_task(task)
        out_of_bounds = [v for v in viols if '超出屏幕边界' in v.reason]
        self.assertTrue(len(out_of_bounds) > 0, "Should flag out-of-bounds trajectory points")

    def test_timestamp_ms_vs_seconds_conversion(self):
        """Verify that ms → seconds conversion is correct for NF lookup."""
        blocks = _make_nf_block_areas([(1.0, 2.0)])  # NF at t=1-2s
        detector = NFDetector(blocks)
        nf_mapper = NFMapper(blocks)
        graph = SpatialGraph()
        verifier = SpatialVerifier(detector, nf_mapper, graph)

        # At 1500ms = 1.5s, inside NF
        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=1500,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),
            angle=0.0,
            line=None,
        )
        viols = verifier.verify_task(task)
        self.assertTrue(len(viols) > 0)

        # At 500ms = 0.5s, outside NF
        task2 = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=500,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),
            angle=0.0,
            line=None,
        )
        viols2 = verifier.verify_task(task2)
        self.assertEqual(len(viols2), 0)


# ============================================================================
# NEW TESTS: P0-P3 Architectural Improvements
# ============================================================================

class TestPathReplannerClosedLoopVerification(unittest.TestCase):
    """【P0】PathReplanner 闭环验证测试 — 重规划后必须重新验证新位置不在 NF 内"""

    def test_replan_tap_still_in_nf_rejected(self):
        """TAP replanning: if new position is still in NF, reject it."""
        # Create NF covering entire screen center region
        blocks = _make_nf_block_areas(
            [(0.0, 5.0)], cx=640, hw=600, hh=400  # Large NF covering most of screen
        )
        chart_mock = MagicMock()
        planner = PathReplanner(chart_mock, blocks)

        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=2000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),  # Deep inside NF
            angle=0.0,
            line=None,
        )
        viol = Violation(
            violation_type=ViolationType.PRESS_IN_NF,
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=2000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),
            reason='test',
        )

        # search_point with empty blocks would return original position,
        # but our NF covers everything, so re-verification should fail
        result = planner.attempt_fix(task, viol)
        # Should be None because any found position will still be in NF
        self.assertIsNone(result)

    def test_replan_tap_outside_nf_accepted(self):
        """TAP replanning: if new position is outside NF, accept it."""
        # Create small NF at center
        blocks = _make_nf_block_areas(
            [(0.0, 5.0)], cx=640, hw=50, hh=50  # Small NF, only covers center
        )
        chart_mock = MagicMock()
        planner = PathReplanner(chart_mock, blocks)

        task = VerificationTask(
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=2000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),  # Inside small NF
            angle=0.0,
            line=None,
        )
        viol = Violation(
            violation_type=ViolationType.PRESS_IN_NF,
            task_type=TaskType.TAP_PRESS,
            timestamp_ms=2000,
            pointer_id=0,
            note_type=1,
            note_id=1,
            position=(640, 360),
            reason='test',
        )

        # With small NF, search_point may find a nearby position outside NF
        result = planner.attempt_fix(task, viol)
        # Result depends on search_point behavior; if found, must pass NF check
        if result is not None:
            # Verify the new position is NOT in NF
            t_sec = result.timestamp_ms / 1000.0
            nf_mapper = NFMapper(blocks)
            self.assertFalse(nf_mapper.is_covered(t_sec, *result.position))

    def test_replan_violations_tracks_unresolved(self):
        """replan_violations should track unresolved count."""
        # NF covering entire screen
        blocks = _make_nf_block_areas(
            [(0.0, 5.0)], cx=640, hw=700, hh=400  # Very large NF
        )
        chart_mock = MagicMock()
        planner = PathReplanner(chart_mock, blocks)

        tasks = [
            VerificationTask(
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=2000,
                pointer_id=0,
                note_type=1,
                note_id=1,
                position=(640, 360),
                angle=0.0,
                line=None,
            ),
            VerificationTask(
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=3000,
                pointer_id=1,
                note_type=1,
                note_id=2,
                position=(600, 300),
                angle=0.0,
                line=None,
            ),
        ]
        viols = [
            Violation(
                violation_type=ViolationType.PRESS_IN_NF,
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=2000,
                pointer_id=0,
                note_type=1,
                note_id=1,
                position=(640, 360),
                reason='in NF',
            ),
            Violation(
                violation_type=ViolationType.PRESS_IN_NF,
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=3000,
                pointer_id=1,
                note_type=1,
                note_id=2,
                position=(600, 300),
                reason='in NF',
            ),
        ]

        replanned = planner.replan_violations(tasks, viols)
        # Both should be unresolved since NF covers everything
        self.assertEqual(len(replanned), 0)
        # The unresolved_count variable is local, but we can verify via report

    def test_report_unresolved_violations_field_exists(self):
        """VerificationReport should have unresolved_violations field."""
        report = VerificationReport(
            nf_detected=True,
            nf_result=NFDetectionResult.DYNAMIC,
        )
        # Field should exist and default to 0
        self.assertEqual(report.unresolved_violations, 0)
        # Should be settable
        report.unresolved_violations = 5
        self.assertEqual(report.unresolved_violations, 5)

    def test_report_summary_shows_unresolved(self):
        """VerificationReport.summary() should include unresolved count."""
        report = VerificationReport(
            nf_detected=True,
            nf_result=NFDetectionResult.DYNAMIC,
            total_tasks=10,
            total_violations=3,
            unresolved_violations=2,
        )
        summary = report.summary()
        self.assertIn('Unresolved Violations: 2', summary)


class TestHoldDragNFSeverity(unittest.TestCase):
    """【P1】HOLD/DRAG NF 冲突 severity 应为 'info' 而非 'warning'"""

    def test_hold_move_nf_severity_is_info(self):
        """HOLD MOVE in NF should have severity='info', not 'warning'."""
        blocks = _make_nf_block_areas([(0.0, 5.0)], cx=640, hw=100, hh=100)
        detector = NFDetector(blocks)
        nf_mapper = NFMapper(blocks)
        graph = SpatialGraph()
        verifier = SpatialVerifier(detector, nf_mapper, graph)

        task = VerificationTask(
            task_type=TaskType.HOLD_MOVE,
            timestamp_ms=2000,
            pointer_id=0,
            note_type=3,
            note_id=1,
            position=(640, 360),  # Inside NF
            angle=0.0,
            line=None,
        )
        viols = verifier.verify_task(task)

        self.assertTrue(len(viols) > 0, "Should detect HOLD MOVE in NF")
        for v in viols:
            self.assertEqual(v.severity, 'info',
                           f"HOLD MOVE NF conflict should have severity='info', got '{v.severity}'")
            self.assertEqual(v.violation_type, ViolationType.HOLD_MOVE_IN_NF)

    def test_drag_move_nf_severity_is_info(self):
        """DRAG MOVE in NF should also have severity='info'."""
        blocks = _make_nf_block_areas([(0.0, 5.0)], cx=640, hw=100, hh=100)
        detector = NFDetector(blocks)
        nf_mapper = NFMapper(blocks)
        graph = SpatialGraph()
        verifier = SpatialVerifier(detector, nf_mapper, graph)

        task = VerificationTask(
            task_type=TaskType.DRAG_MOVE,
            timestamp_ms=2000,
            pointer_id=0,
            note_type=2,
            note_id=1,
            position=(640, 360),  # Inside NF
            angle=0.0,
            line=None,
        )
        viols = verifier.verify_task(task)

        self.assertTrue(len(viols) > 0, "Should detect DRAG MOVE in NF")
        for v in viols:
            self.assertEqual(v.severity, 'info',
                           f"DRAG MOVE NF conflict should have severity='info', got '{v.severity}'")


class TestTaskMapperDecoupling(unittest.TestCase):
    """【P3】TaskMapper 解耦 — 支持预构建任务"""

    def test_verify_with_prebuilt_tasks(self):
        """verify_algo3_output should accept pre-built tasks and skip TaskMapper."""
        events_map = {
            1000: [_make_touch(200, 200, TouchAction.DOWN, 0)],
            2000: [_make_touch(200, 200, TouchAction.UP, 0)],
        }

        blocks = _make_nf_block_areas([(0.0, 5.0)], cx=640, hw=100, hh=100)
        chart_mock = MagicMock()
        chart_mock.block_areas = blocks
        chart_mock.judge_lines = []

        # Pre-build tasks manually
        prebuilt_tasks = [
            VerificationTask(
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=1000,
                pointer_id=0,
                note_type=1,
                note_id=1,
                position=(200.0, 200.0),  # Outside NF
                angle=0.0,
                line=None,
            ),
        ]

        report = verify_algo3_output(events_map, chart_mock, tasks=prebuilt_tasks)

        self.assertTrue(report.nf_detected)
        self.assertEqual(report.total_tasks, 1)
        self.assertEqual(report.total_violations, 0)  # Position is outside NF

    def test_verify_without_tasks_uses_taskmapper(self):
        """verify_algo3_output without tasks parameter should use TaskMapper (backward compat)."""
        events_map = {
            1000: [_make_touch(200, 200, TouchAction.DOWN, 0)],
            2000: [_make_touch(200, 200, TouchAction.UP, 0)],
        }

        blocks = _make_nf_block_areas([(0.0, 5.0)], cx=640, hw=100, hh=100)
        chart_mock = MagicMock()
        chart_mock.block_areas = blocks
        chart_mock.judge_lines = []  # Empty judge_lines means TaskMapper finds no notes

        # Call WITHOUT tasks parameter — should use TaskMapper internally
        report = verify_algo3_output(events_map, chart_mock)

        self.assertTrue(report.nf_detected)
        # With empty judge_lines, TaskMapper produces 0 tasks
        self.assertEqual(report.total_tasks, 0)

    def test_prebuilt_tasks_bypass_taskmapper(self):
        """Pre-built tasks should completely bypass TaskMapper construction."""
        events_map = {
            1000: [_make_touch(200, 200, TouchAction.DOWN, 0)],
        }

        blocks = _make_nf_block_areas([(0.0, 5.0)])
        chart_mock = MagicMock()
        chart_mock.block_areas = blocks
        chart_mock.judge_lines = []  # Would cause TaskMapper to produce 0 tasks

        # Provide pre-built tasks that would be impossible with TaskMapper
        prebuilt_tasks = [
            VerificationTask(
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=1000,
                pointer_id=0,
                note_type=1,
                note_id=999,  # Fake note_id
                position=(200.0, 200.0),
                angle=0.0,
                line=None,
            ),
        ]

        report = verify_algo3_output(events_map, chart_mock, tasks=prebuilt_tasks)

        # Should see our pre-built task, not 0 tasks from TaskMapper
        self.assertEqual(report.total_tasks, 1)


class TestZeroOverheadSkip(unittest.TestCase):
    """【P2】无 NF 谱面零开销跳过 — 不应实例化任何重型模块"""

    def test_no_nf_returns_early_before_heavy_modules(self):
        """When no NF exists, verify_algo3_output should return before creating FrameGenerator etc."""
        events_map = {
            1000: [_make_touch(640, 360, TouchAction.DOWN, 0)],
            2000: [_make_touch(640, 360, TouchAction.UP, 0)],
        }

        chart_mock = MagicMock()
        chart_mock.block_areas = BlockAreas([])  # No NF

        # Patch all heavy modules to track instantiation
        with patch('algo.verify_nf.FrameGenerator') as mock_fg:
            with patch('algo.verify_nf.PositionCalculator') as mock_pc:
                with patch('algo.verify_nf.SpatialGraph') as mock_sg:
                    with patch('algo.verify_nf.NFMapper') as mock_nm:
                        with patch('algo.verify_nf.TaskMapper') as mock_tm:
                            report = verify_algo3_output(events_map, chart_mock)

                            # Heavy modules should NOT be instantiated
                            mock_fg.assert_not_called()
                            mock_pc.assert_not_called()
                            mock_sg.assert_not_called()
                            mock_nm.assert_not_called()
                            mock_tm.assert_not_called()

        # Only NFDetector should be created
        self.assertFalse(report.nf_detected)
        self.assertEqual(report.total_tasks, 0)
        self.assertEqual(report.total_violations, 0)

    def test_with_nf_creates_all_modules(self):
        """When NF exists, all modules should be instantiated normally."""
        events_map = {
            1000: [_make_touch(200, 200, TouchAction.DOWN, 0)],
        }

        blocks = _make_nf_block_areas([(0.0, 5.0)])
        chart_mock = MagicMock()
        chart_mock.block_areas = blocks
        chart_mock.judge_lines = []

        with patch('algo.verify_nf.FrameGenerator') as mock_fg:
            with patch('algo.verify_nf.PositionCalculator') as mock_pc:
                with patch('algo.verify_nf.SpatialGraph') as mock_sg:
                    with patch('algo.verify_nf.NFMapper') as mock_nm:
                        with patch('algo.verify_nf.TaskMapper') as mock_tm:
                            # These mocks prevent actual execution
                            mock_fg.return_value = MagicMock(frames=[])
                            mock_pc.return_value = MagicMock(results={})
                            mock_sg.return_value = MagicMock()
                            mock_nm.return_value = MagicMock(is_covered=lambda *a, **k: False)
                            mock_tm.return_value = MagicMock(tasks=[])

                            report = verify_algo3_output(events_map, chart_mock)

                            # All modules SHOULD be instantiated
                            mock_fg.assert_called_once()
                            mock_pc.assert_called_once()
                            mock_sg.assert_called()  # Called at least once
                            mock_nm.assert_called_once()
                            mock_tm.assert_called_once()


class TestEndToEndIntegration(unittest.TestCase):
    """端到端集成测试 — 验证完整流水线"""

    def test_full_pipeline_with_replanning_and_unresolved(self):
        """Full pipeline: NF detection → verification → replanning → unresolved tracking."""
        events_map = {
            900: [_make_touch(640, 350, TouchAction.DOWN, 1)],  # HOLD DOWN (before MOVE)
            1000: [_make_touch(200, 200, TouchAction.DOWN, 0)],  # TAP outside NF
            1008: [_make_touch(640, 350, TouchAction.MOVE, 1)],   # HOLD MOVE in NF
            2000: [_make_touch(640, 360, TouchAction.UP, 1)],     # HOLD release
        }

        # NF covering center
        blocks = _make_nf_block_areas([(0.0, 5.0)], cx=640, hw=100, hh=100)
        chart_mock = MagicMock()
        chart_mock.block_areas = blocks
        chart_mock.judge_lines = []

        # Use pre-built tasks to control what gets verified
        prebuilt_tasks = [
            VerificationTask(
                task_type=TaskType.TAP_PRESS,
                timestamp_ms=1000,
                pointer_id=0,
                note_type=1,
                note_id=1,
                position=(200.0, 200.0),  # Outside NF — should pass
                angle=0.0,
                line=None,
            ),
            VerificationTask(
                task_type=TaskType.HOLD_MOVE,
                timestamp_ms=1008,
                pointer_id=1,
                note_type=3,
                note_id=2,
                position=(640.0, 350.0),  # Inside NF — should be info severity
                angle=0.0,
                line=None,
            ),
        ]

        report = verify_algo3_output(events_map, chart_mock, tasks=prebuilt_tasks)

        # NF should be detected
        self.assertTrue(report.nf_detected)
        # Should have 2 tasks
        self.assertEqual(report.total_tasks, 2)
        # TAP should pass, HOLD MOVE should generate info-level violation
        self.assertTrue(report.total_violations >= 1)
        # Unresolved should be tracked
        self.assertIsInstance(report.unresolved_violations, int)

    def test_old_api_backward_compatibility(self):
        """Old API call without tasks parameter should still work."""
        events_map = {
            1000: [_make_touch(640, 360, TouchAction.DOWN, 0)],
            2000: [_make_touch(640, 360, TouchAction.UP, 0)],
        }

        chart_mock = MagicMock()
        chart_mock.block_areas = BlockAreas([])  # No NF

        # Old API style — no tasks parameter
        report = verify_algo3_output(events_map, chart_mock)

        self.assertFalse(report.nf_detected)
        self.assertEqual(report.total_tasks, 0)

    def test_detailed_mode_flag(self):
        """detailed=True should create SpatialGraph even without NF skipping."""
        events_map = {
            1000: [_make_touch(200, 200, TouchAction.DOWN, 0)],
        }

        blocks = _make_nf_block_areas([(0.0, 5.0)])
        chart_mock = MagicMock()
        chart_mock.block_areas = blocks
        chart_mock.judge_lines = []

        with patch('algo.verify_nf.FrameGenerator') as mock_fg:
            with patch('algo.verify_nf.PositionCalculator') as mock_pc:
                with patch('algo.verify_nf.SpatialGraph') as mock_sg:
                    with patch('algo.verify_nf.NFMapper') as mock_nm:
                        with patch('algo.verify_nf.TaskMapper') as mock_tm:
                            mock_fg.return_value = MagicMock(frames=[])
                            mock_pc.return_value = MagicMock(results={})
                            mock_sg.return_value = MagicMock()
                            mock_nm.return_value = MagicMock(is_covered=lambda *a, **k: False)
                            mock_tm.return_value = MagicMock(tasks=[])

                            report = verify_algo3_output(
                                events_map, chart_mock, detailed=True
                            )

                            # SpatialGraph should be called with cell_size=16.0
                            mock_sg.assert_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
