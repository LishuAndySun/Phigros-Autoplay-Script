"""激进的指针规划算法
这种算法把hold拆分成一个tap和若干个drag，各自规划
"""
import math
from sys import stdout
from typing import Optional, Iterator

from chart import Chart
from note import Note
from utils import recalc_pos
from .algo_base import TouchAction, TouchEvent


class SimpleNote:
    note_type: int
    timestamp: int
    pos: tuple[float, float]
    angle: float

    def __init__(self, note_type: int, timestamp: int, pos: tuple[float, float], angle: float):
        self.note_type = note_type
        self.timestamp = timestamp
        self.pos = pos
        self.angle = angle


class Frame:
    timestamp: int

    unallocated: list[list[SimpleNote]]
    allocated: list[list[SimpleNote]]

    def __init__(self, timestamp: int):
        self.timestamp = timestamp

        self.unallocated = [[] for _ in range(4)]
        self.allocated = [[] for _ in range(4)]

    def add(self, note_type: int, pos: tuple[float, float], angle: float):
        pos = recalc_pos(pos, math.sin(angle), math.cos(angle))
        self.unallocated[note_type - 1].append(SimpleNote(note_type, self.timestamp, pos, angle))

    def taps(self) -> Iterator[SimpleNote]:
        taps = self.unallocated[Note.TAP - 1]
        while taps:
            yield taps.pop(0)

    def drags(self) -> Iterator[SimpleNote]:
        drags = self.unallocated[Note.DRAG - 1]
        while drags:
            yield drags.pop(0)

    def flicks(self) -> Iterator[SimpleNote]:
        flicks = self.unallocated[Note.FLICK - 1]
        while flicks:
            yield flicks.pop(0)


class Frames:
    frames: dict[int, Frame]

    def __init__(self):
        self.frames = {}

    def __getitem__(self, timestamp: int) -> Frame:
        if timestamp not in self.frames:
            self.frames[timestamp] = Frame(timestamp)
        return self.frames[timestamp]

    def __iter__(self) -> Iterator[Frame]:
        return iter(sorted(self.frames.values(), key=lambda f: f.timestamp))

    def __len__(self) -> int:
        return len(self.frames)


class Pointer:
    id: int
    note: Optional[SimpleNote]
    age: int  # 距离最后一次事件的时间(ms)，为负表示仍在执行flick
    sent_at: int  # 最后一次发送MOVE的时间(ms)

    def __init__(self, pid: int, note: Optional[SimpleNote] = None, age: int = 0):
        self.id = pid
        self.note = note
        self.age = age
        self.sent_at = -10 ** 9


def distance_of(note1: Optional[SimpleNote], note2: SimpleNote) -> float:
    if note1 is None:
        return math.inf
    x1, y1 = note1.pos
    x2, y2 = note2.pos
    return (x2 - x1) ** 2 + (y2 - y1) ** 2


flick_start = -50
flick_end = 50
flick_scale_factor = 100
flick_step = 5  # flick滑动时每隔多少ms发送一次MOVE
drag_step = 8  # hold延续时每隔多少ms发送一次MOVE，过密会导致游戏卡顿


class PointerAllocator:
    pointers: list[Pointer]
    events: dict[int, list[TouchEvent]]
    last_timestamp: Optional[int]
    now: int

    def __init__(self, max_pointers_count: int = 10, begin_at: int = 1000):
        self.pointers = [Pointer(i + begin_at) for i in range(max_pointers_count)]
        self.events = {}
        self.last_timestamp = None
    def alloc(self, note: SimpleNote) -> Pointer:
        usable_pointers = [p for p in self.pointers if p.note is None or p.age > 0]
        assert usable_pointers
        return min(usable_pointers, key=lambda p: distance_of(p.note, note))  # 优先使用废弃的Pointer

    def check(self, note: SimpleNote) -> Optional[Pointer]:
        ox, oy = note.pos
        ca, sa = math.cos(note.angle), math.sin(note.angle)
        for pointer in self.pointers:
            if pointer.note is None or pointer.age < 0:  # 闲置指针或正在执行flick的指针
                continue
            # TODO: 考虑flick在移动时的影响
            px, py = pointer.note.pos
            if abs((px - ox) * ca + (py - oy) * sa) < 100:
                return pointer
        return None

    def _insert(self, timestamp: int, event: TouchEvent):
        if timestamp not in self.events:
            self.events[timestamp] = []
        self.events[timestamp].append(event)

    def _down(self, pointer: Pointer, note: SimpleNote):
        # 复用指针前，先在其上一次事件之后释放它（alloc保证 age > 0，因此释放时间 <= now）
        if pointer.note is not None:
            self._insert(self.now - pointer.age + 1, TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
        pointer.note = note
        pointer.age = 0
        pointer.sent_at = self.now
        self._insert(self.now, TouchEvent(note.pos, TouchAction.DOWN, pointer.id))

    def _tap(self, pointer: Pointer, note: SimpleNote):
        self._down(pointer, note)

    def _flick(self, pointer: Pointer, note: SimpleNote):
        # 在 [now, now + (flick_end - flick_start)] 内单调滑动，每 flick_step ms 发送一次MOVE
        duration = flick_end - flick_start
        if pointer.note is not None:
            self._insert(self.now - pointer.age + 1, TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
        x0, y0 = note.pos
        alpha = note.angle
        dx, dy = math.sin(alpha) * flick_scale_factor, math.cos(alpha) * flick_scale_factor
        self._insert(self.now, TouchEvent((x0, y0), TouchAction.DOWN, pointer.id))
        for t in range(self.now + flick_step, self.now + duration + 1, flick_step):
            k = (t - self.now) / duration
            self._insert(t, TouchEvent((x0 + dx * k, y0 + dy * k), TouchAction.MOVE, pointer.id))
        # 滑动结束点，供后续 check() 与 UP 使用
        note.pos = (x0 + dx, y0 + dy)
        pointer.note = note
        pointer.age = flick_start - flick_end  # 负值：滑动期间该指针不可被分配

    def _drag(self, pointer: Pointer, note: SimpleNote):
        self._down(pointer, note)

    def allocate(self, frame: Frame):

        # 更新pointer age
        self.now = frame.timestamp
        if self.last_timestamp is not None:
            for pointer in self.pointers:
                pointer.age += self.now - self.last_timestamp

        # 步骤1：分配tap
        for note in frame.taps():
            pointer = self.alloc(note)
            self._tap(pointer, note)

        # 步骤2: 分配flick
        for note in frame.flicks():
            pointer = self.alloc(note)
            self._flick(pointer, note)

        # 步骤3：分配drag
        for note in frame.drags():
            pointer = self.check(note)
            if pointer:
                pointer.note = note
                pointer.age = 0
                if self.now - pointer.sent_at >= drag_step:
                    self._insert(self.now, TouchEvent(note.pos, TouchAction.MOVE, pointer.id))
                    pointer.sent_at = self.now
                continue
            pointer = self.alloc(note)
            self._drag(pointer, note)

        self.last_timestamp = frame.timestamp

    def done(self):
        # 释放仍按住的指针，避免结束后残留按下状态
        for pointer in self.pointers:
            if pointer.note is not None:
                self._insert(self.now - pointer.age + 1, TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
                pointer.note = None
        return self.events


def solve(chart: Chart) -> dict[int, list[TouchEvent]]:
    frames = Frames()

    print('正在统计帧...', end='')
    stdout.flush()
    # 统计frames
    for line in chart.judge_lines:
        for note in line.notes_above + line.notes_below:
            ms = round(line.seconds(note.time) * 1000)
            off_x = note.x * 72
            x, y = line.pos(note.time)
            alpha = - line.angle(note.time) * math.pi / 180
            pos = x + off_x * math.cos(alpha), y + off_x * math.sin(alpha)
            if note.typ == Note.HOLD:
                hold_ms = math.ceil(line.seconds(note.hold) * 1000)
                frames[ms].add(Note.TAP, pos, alpha)
                for offset in range(1, hold_ms + 1):
                    alpha = - line.angle(line.time((ms + offset) / 1000)) * math.pi / 180
                    frames[ms + offset].add(Note.DRAG,
                                            line.pos_of(note, line.time((ms + offset) / 1000)),
                                            alpha)
            elif note.typ == Note.FLICK:
                frames[ms + flick_start].add(Note.FLICK, pos, alpha)
            else:
                frames[ms].add(note.typ, pos, alpha)

    print(f'统计完毕，当前谱面共计{len(frames)}帧')

    allocator = PointerAllocator()

    print('正在规划触控事件...', end='')
    stdout.flush()

    for frame in frames:
        allocator.allocate(frame)

    print('规划完毕.')
    return allocator.done()
