import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from algo import algo3beta1 as beta  # noqa: E402
from algo.algo_base import TouchAction, TouchEvent  # noqa: E402
from note import Note  # noqa: E402


class HorizontalBand:
    def blocked(self, x, y, time, margin):
        return abs(y - 360) < 4


class WideHorizontalBand:
    def blocked(self, x, y, time, margin):
        return abs(y - 360) < 20


class PreferredSideBlocked:
    def blocked(self, x, y, time, margin):
        return y >= 360


class MovingBlock:
    def blocked(self, x, y, time, margin):
        return time >= 1.01 and 356 < y < 377


class DragRelocationTests(unittest.TestCase):
    def test_drag_relocates_only_along_judge_line_normal(self):
        allocator = beta.PointerAllocator(max_pointers_count=1, max_pointers=1)
        allocator.now = 1000
        note = beta.SimpleNote(Note.DRAG, 1000, (640, 360), 0)

        self.assertEqual(allocator._drag_pos(note, HorizontalBand(), None), (640, 368))

    def test_safe_current_target_recovers_after_blocked_previous_target(self):
        allocator = beta.PointerAllocator(max_pointers_count=1, max_pointers=1)
        allocator.now = 1000
        note = beta.SimpleNote(Note.DRAG, 1000, (640, 360), 0)

        self.assertEqual(allocator._drag_pos(note, HorizontalBand(), (900, 640, 360)), (640, 368))

    def test_relocation_does_not_flip_normal_side_between_samples(self):
        allocator = beta.PointerAllocator(max_pointers_count=1, max_pointers=1)
        allocator.now = 1000
        note = beta.SimpleNote(Note.DRAG, 1000, (640, 360), 0)

        self.assertEqual(allocator._drag_pos(note, WideHorizontalBand(), (999, 640, 368)), (640, 384))

    def test_drag_falls_back_to_opposite_normal_side(self):
        allocator = beta.PointerAllocator(max_pointers_count=1, max_pointers=1)
        allocator.now = 1000
        note = beta.SimpleNote(Note.DRAG, 1000, (640, 360), 0)

        self.assertEqual(allocator._drag_pos(note, PreferredSideBlocked(), None), (640, 352))

    def test_final_guard_does_not_insert_move_after_backdated_up(self):
        allocator = beta.PointerAllocator(max_pointers_count=1, max_pointers=1)
        allocator.now = 1100
        allocator.blocks = HorizontalBand()
        pointer_id = allocator.pointers[0].id
        allocator.events = {
            1000: [TouchEvent((640, 360), TouchAction.DOWN, pointer_id)],
            1050: [TouchEvent((640, 360), TouchAction.UP, pointer_id)],
        }
        allocator.tags[(pointer_id, 1000)] = (Note.TAP, 0)

        allocator._guard_static(allocator.blocks)

        sequence = [(time, event.action) for time, events in sorted(allocator.events.items())
                for event in events]
        up_time = next(time for time, action in sequence if action == TouchAction.UP)
        self.assertTrue(all(time < up_time for time, action in sequence if action == TouchAction.MOVE))
        self.assertEqual(sequence[0], (1000, TouchAction.DOWN))
        self.assertEqual(sequence[-1], (1050, TouchAction.UP))

    def test_guard_escapes_moving_nf_on_opposite_normal_side(self):
        allocator = beta.PointerAllocator(max_pointers_count=1, max_pointers=1)
        allocator.now = 1100
        allocator.blocks = MovingBlock()
        pointer_id = allocator.pointers[0].id
        allocator.events = {
            1000: [TouchEvent((640, 360), TouchAction.DOWN, pointer_id)],
            1100: [TouchEvent((640, 360), TouchAction.UP, pointer_id)],
        }
        allocator.tags[(pointer_id, 1000)] = (Note.TAP, 0)

        allocator._guard_static(allocator.blocks)

        moves = [(time, event.pos) for time, events in allocator.events.items()
                 for event in events if event.action == TouchAction.MOVE]
        self.assertTrue(moves)
        self.assertLess(moves[0][1][1], 360)
        self.assertEqual(allocator.guard_failures, 0)


if __name__ == '__main__':
    unittest.main()