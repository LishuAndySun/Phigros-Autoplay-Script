from judge_line import JudgeLine


class Chart:
    version: int
    offset: float
    notes_count: int
    judge_lines: list[JudgeLine]

    def __init__(self, version: int, offset: float, notes_count: int, judge_lines: list[JudgeLine]):
        self.version = version
        self.offset = offset
        self.notes_count = notes_count
        self.judge_lines = judge_lines

    @classmethod
    def from_dict(cls, d: dict):
        version = d['formatVersion']
        # Newer charts omit numOfNotes; count it from the judge lines instead.
        notes_count = d.get('numOfNotes', sum(len(line['notesAbove']) + len(line['notesBelow'])
                                              for line in d['judgeLineList']))
        if version == 1:
            return cls(version, d['offset'], notes_count,
                       [*map(JudgeLine.from_dict_v1, d['judgeLineList'])])
        else:
            return cls(version, d['offset'], notes_count,
                       [*map(JudgeLine.from_dict, d['judgeLineList'])])


__all__ = ['Chart']
