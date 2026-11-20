"""algo/algo3.py 指针分配的自动化测试（合成帧，不使用真实谱面）。

运行: venv/bin/python -m unittest tests/test_algo3_pointers.py
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from algo import algo3  # noqa: E402
from algo.algo3 import (AllocFailure, Frame, PointerAllocator, MIN_PRESS_MS, release_ms)  # noqa: E402
from algo.algo_base import TouchAction  # noqa: E402
from block_area import BlockAreas, PlacementFailure  # noqa: E402
from note import Note  # noqa: E402


class AlwaysBlocked:
    """所有位置都被噪域覆盖的替身，用于构造无解音符"""

    def blocked(self, *args, **kwargs):
        return True

    def search_point(self, *args, **kwargs):
        return None, PlacementFailure.NO_VALID_POSITION


def empty_blocks() -> BlockAreas:
    return BlockAreas([])


def make_frame(t: int, blocks, notes=()) -> Frame:
    """notes: (note_type, pos, angle) 三元组序列"""
    frame = Frame(t, blocks)
    for note_type, pos, angle in notes:
        frame.add(note_type, pos, angle, None, note_id=t)
    return frame


def tap(t: int, blocks, x=640.0, y=360.0):
    return make_frame(t, blocks, [(Note.TAP, (x, y), 0.0)])


def events_of(allocator: PointerAllocator, action: TouchAction):
    return [(t, e) for t, evs in sorted(allocator.events.items())
            for e in evs if e.action == action]


class InvalidNoteTests(unittest.TestCase):
    def test_invalid_tap_creates_no_pointer(self):
        alloc = PointerAllocator(max_pointers=None)
        blocks = AlwaysBlocked()
        for i in range(5):
            alloc.allocate(tap(1000 + i * 10, blocks))
        self.assertEqual(len(alloc.pointers), 10)
        self.assertEqual(alloc.created_count, 0)
        self.assertEqual(len(alloc.skipped), 5)
        self.assertTrue(all(s[4] is PlacementFailure.NO_VALID_POSITION for s in alloc.skipped))
        self.assertEqual(events_of(alloc, TouchAction.DOWN), [])

    def test_invalid_flick_creates_no_pointer(self):
        alloc = PointerAllocator(max_pointers=None)
        blocks = AlwaysBlocked()
        frame = make_frame(1000, blocks, [(Note.FLICK, (640.0, 360.0), 0.0)])
        alloc.allocate(frame)
        self.assertEqual(alloc.created_count, 0)
        self.assertEqual(len(alloc.pointers), 10)
        self.assertEqual(len(alloc.skipped), 1)


class CapOverflowTests(unittest.TestCase):
    def test_overflow_is_recorded_not_raised(self):
        alloc = PointerAllocator(max_pointers_count=1, max_pointers=1)
        blocks = empty_blocks()
        alloc.allocate(tap(1000, blocks))  # 占用唯一的指针
        alloc.allocate(tap(1010, blocks, x=100.0, y=100.0))  # 按压锁定期内且已达上限
        self.assertEqual(len(alloc.pointers), 1)
        self.assertEqual(len(alloc.skipped), 1)
        self.assertIs(alloc.skipped[0][4], AllocFailure.POINTER_LIMIT_EXCEEDED)
        self.assertEqual(alloc.allocation_failures, 1)

    def test_overflow_drag_is_recorded_not_raised(self):
        alloc = PointerAllocator(max_pointers_count=0, max_pointers=0)
        frame = make_frame(1000, empty_blocks(), [(Note.DRAG, (640.0, 360.0), 0.0)])
        alloc.allocate(frame)
        self.assertEqual(len(alloc.skipped), 1)
        self.assertIs(alloc.skipped[0][4], AllocFailure.POINTER_LIMIT_EXCEEDED)

    def test_overflow_at_cap_boundary_allows_exactly_max(self):
        alloc = PointerAllocator(max_pointers_count=0, max_pointers=3)
        blocks = empty_blocks()
        frame = make_frame(1000, blocks, [(Note.TAP, (100.0, 100.0), 0.0),
                                          (Note.TAP, (400.0, 400.0), 0.0),
                                          (Note.TAP, (800.0, 300.0), 0.0),
                                          (Note.TAP, (1000.0, 600.0), 0.0)])
        alloc.allocate(frame)
        self.assertEqual(len(alloc.pointers), 3)
        self.assertEqual(len(alloc.skipped), 1)

    def test_init_over_cap_rejected(self):
        with self.assertRaises(ValueError):
            PointerAllocator(max_pointers_count=5, max_pointers=2)


class MinPressTests(unittest.TestCase):
    def test_press_locked_pointer_not_reused_before_min_press(self):
        """按压于 t=1000，t=1000+MIN_PRESS_MS-1 时不得复用该指针（cap=1 时应跳过）"""
        alloc = PointerAllocator(max_pointers_count=1, max_pointers=1)
        blocks = empty_blocks()
        alloc.allocate(tap(1000, blocks))
        alloc.allocate(tap(1000 + MIN_PRESS_MS - 1, blocks, x=100.0, y=100.0))
        self.assertEqual(len(alloc.skipped), 1)
        self.assertEqual(len(events_of(alloc, TouchAction.UP)), 0)

    def test_pointer_reused_exactly_at_min_press(self):
        """恰好 MIN_PRESS_MS 时指针已满足最短按压，应允许复用"""
        alloc = PointerAllocator(max_pointers_count=1, max_pointers=1)
        blocks = empty_blocks()
        alloc.allocate(tap(1000, blocks))
        alloc.allocate(tap(1000 + MIN_PRESS_MS, blocks, x=100.0, y=100.0))
        self.assertEqual(alloc.skipped, [])
        self.assertEqual(len(alloc.pointers), 1)
        self.assertEqual(len(events_of(alloc, TouchAction.DOWN)), 2)

    def test_press_lock_never_expands_pool_when_under_cap(self):
        """未达上限时，按压锁定的指针不被复用，改为新建（不违反按压时长）"""
        alloc = PointerAllocator(max_pointers_count=1, max_pointers=None)
        blocks = empty_blocks()
        alloc.allocate(tap(1000, blocks))
        alloc.allocate(tap(1000 + MIN_PRESS_MS - 1, blocks, x=100.0, y=100.0))
        self.assertEqual(alloc.skipped, [])
        self.assertEqual(alloc.created_count, 1)
        self.assertEqual(len(alloc.pointers), 2)


class ProtectionTests(unittest.TestCase):
    def test_flick_in_progress_not_stolen(self):
        alloc = PointerAllocator(max_pointers_count=1, max_pointers=1)
        blocks = empty_blocks()
        alloc.allocate(make_frame(1000, blocks, [(Note.FLICK, (640.0, 360.0), 0.0)]))
        # FLICK 持续期间（age 为负）该指针不可被 tap 占用
        alloc.allocate(tap(1020, blocks, x=100.0, y=100.0))
        self.assertEqual(len(alloc.skipped), 1)
        self.assertIs(alloc.skipped[0][4], AllocFailure.POINTER_LIMIT_EXCEEDED)

    def test_active_pointer_not_stolen(self):
        alloc = PointerAllocator(max_pointers_count=1, max_pointers=1)
        blocks = empty_blocks()
        alloc.allocate(tap(1000, blocks))
        alloc.allocate(tap(1000 + MIN_PRESS_MS + 5, blocks, x=100.0, y=100.0))
        # 第二个 tap 能复用，因为已满足按压时长；这里验证占用指针仍在使用中
        alloc.allocate(tap(1000 + MIN_PRESS_MS + 6, blocks, x=100.0, y=100.0))
        self.assertEqual(alloc.skipped[0][4], AllocFailure.POINTER_LIMIT_EXCEEDED)


class IdentityAndReuseTests(unittest.TestCase):
    def test_ids_unique_across_creation_and_recycle(self):
        alloc = PointerAllocator(max_pointers_count=2, max_pointers=None)
        blocks = empty_blocks()
        for i in range(200):
            alloc.allocate(make_frame(1000 + i * 200, blocks,
                                      [(Note.TAP, (100.0 + (i % 5) * 200, 300.0), 0.0),
                                       (Note.TAP, (200.0 + (i % 3) * 300, 500.0), 0.0),
                                       (Note.TAP, (900.0, 200.0), 0.0)]))
        ids = [p.id for p in alloc.pointers]
        self.assertEqual(len(ids), len(set(ids)))

    def test_reuse_counted_without_creation(self):
        alloc = PointerAllocator(max_pointers_count=1, max_pointers=None)
        blocks = empty_blocks()
        alloc.allocate(tap(1000, blocks))
        # 指针超过 release_ms 后会被抬起，之后再次点击应复用同一指针
        alloc.allocate(make_frame(1000 + release_ms + 50, blocks, []))
        alloc.allocate(tap(1000 + release_ms + 60, blocks, x=100.0, y=100.0))
        self.assertEqual(alloc.created_count, 0)
        self.assertEqual(alloc.reuse_count, 1)
        self.assertEqual(len(alloc.pointers), 1)


if __name__ == '__main__':
    unittest.main()
