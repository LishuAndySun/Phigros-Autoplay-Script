from block_area import BlockAreas
from judge_line import JudgeLine


class Chart:
    version: int
    offset: float
    notes_count: int
    judge_lines: list[JudgeLine]
    block_areas: BlockAreas

    def __init__(self, version: int, offset: float, notes_count: int, judge_lines: list[JudgeLine],
                 block_areas: BlockAreas = None):
        self.version = version
        self.offset = offset
        self.notes_count = notes_count
        self.judge_lines = judge_lines
        self.block_areas = block_areas or BlockAreas([])

    @classmethod
    def from_dict(cls, d: dict):
        version = d['formatVersion']
        # Newer charts omit numOfNotes; count it from the judge lines instead.
        notes_count = d.get('numOfNotes', sum(len(line['notesAbove']) + len(line['notesBelow'])
                                              for line in d['judgeLineList']))
        block_areas = BlockAreas(d.get('blockAreaList', []))
        if version == 1:
            return cls(version, d['offset'], notes_count,
                       [*map(JudgeLine.from_dict_v1, d['judgeLineList'])], block_areas)
        else:
            return cls(version, d['offset'], notes_count,
                       [*map(JudgeLine.from_dict, d['judgeLineList'])], block_areas)


__all__ = ['Chart']
