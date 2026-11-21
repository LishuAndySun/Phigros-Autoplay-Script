import json
from pathlib import Path
import unittest

from block_area import BlockArea, BlockAreas


def make_block(left, right, subtract=False):
    return {
        'enableTime': 0, 'disableTime': 10,
        'bottomLeftPercentage': {'x': left, 'y': 0},
        'topRightPercentage': {'x': right, 'y': 1},
        'isSubtract': subtract,
    }


class BlockCompositionTests(unittest.TestCase):
    def test_large_inverter_leaves_center_clear_and_blocks_sides(self):
        areas = BlockAreas([make_block(.25, .75), make_block(-1, 2, True)])
        self.assertFalse(areas.blocked(640, 360, 1))
        self.assertTrue(areas.blocked(100, 360, 1))
        self.assertTrue(areas.blocked(1180, 360, 1))

    def test_two_inverters_cancel(self):
        areas = BlockAreas([make_block(-1, 2, True), make_block(-1, 2, True)])
        self.assertFalse(areas.blocked(640, 360, 1))

    def test_margin_shrinks_inverted_safe_center(self):
        areas = BlockAreas([make_block(.25, .75), make_block(-1, 2, True)])
        self.assertFalse(areas.blocked(330, 360, 1))
        self.assertTrue(areas.blocked(330, 360, 1, 30))
        self.assertFalse(areas.blocked(360, 360, 1, 30))

    def test_disable_endpoint_is_inactive(self):
        areas = BlockAreas([make_block(0, 1)])
        self.assertTrue(areas.blocked(640, 360, 9.999))
        self.assertFalse(areas.blocked(640, 360, 10))

    def test_outgoing_easing_and_lookup_samples(self):
        self.assertEqual(BlockArea._ease(0, .7), 0)
        self.assertEqual(BlockArea._ease(1, .3), 1)
        self.assertEqual(BlockArea._ease(2, .3), .3)
        self.assertAlmostEqual(BlockArea._ease(6, .5), .25)
        self.assertAlmostEqual(BlockArea._ease(7, .123), 1 - (1 - .12) ** 2 + .3 * ((1 - (1 - .13) ** 2) - (1 - (1 - .12) ** 2)))
        data = make_block(.25, .75)
        data['scaleEvents'] = [
            {'time': 0, 'anchor': {'x': .5, 'y': .5}, 'scale': {'x': 1, 'y': 1}, 'easeTypeX': 0},
            {'time': 2, 'anchor': {'x': .5, 'y': .5}, 'scale': {'x': .1, 'y': 1}},
        ]
        self.assertAlmostEqual(BlockArea(data).geometry(1)[2], 320)

    def test_completed_anchor_deltas_accumulate(self):
        data = make_block(.4, .6)
        data['scaleEvents'] = [
            {'time': 0, 'anchor': {'x': 1, 'y': .5}, 'scale': {'x': 1, 'y': 1}},
            {'time': 1, 'anchor': {'x': 0, 'y': .5}, 'scale': {'x': 2, 'y': 1}},
            {'time': 2, 'anchor': {'x': .5, 'y': .5}, 'scale': {'x': 4, 'y': 1}},
        ]
        self.assertAlmostEqual(BlockArea(data).geometry(2)[0], 0)

    def test_overlapping_normal_blocks_are_a_union(self):
        areas = BlockAreas([make_block(.1, .9), make_block(.2, .8)])
        self.assertTrue(areas.blocked(640, 360, 1))

    def test_desultory_65_center_clear_sides_blocked(self):
        path = Path(__file__).resolve().parents[1] / 'Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json'
        with path.open(encoding='utf-8') as stream:
            areas = BlockAreas(json.load(stream)['blockAreaList'])
        self.assertFalse(areas.blocked(640, 360, 65))
        self.assertTrue(areas.blocked(20, 360, 65))
        self.assertTrue(areas.blocked(1260, 360, 65))