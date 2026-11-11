"""激进的指针规划算法
这种算法把hold拆分成一个tap和若干个drag，各自规划
"""
import math
from sys import stdout
from typing import Optional, Iterator

from chart import Chart
from block_area import BlockAreas, MARGIN, nearby_points
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

    def __init__(self, timestamp: int, blocks: BlockAreas):
        self.timestamp = timestamp
        self.blocks = blocks

        self.unallocated = [[] for _ in range(4)]
        self.allocated = [[] for _ in range(4)]

    def add(self, note_type: int, pos: tuple[float, float], angle: float):
        pos = recalc_pos(pos, math.sin(angle), math.cos(angle))
        pos = self.blocks.free_point(pos, self.timestamp / 1000, -math.sin(angle), math.cos(angle))
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

    def __init__(self, blocks: BlockAreas):
        self.frames = {}
        self.blocks = blocks

    def __getitem__(self, timestamp: int) -> Frame:
        if timestamp not in self.frames:
            self.frames[timestamp] = Frame(timestamp, self.blocks)
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
    pressed_at: int  # 最近一次按下的时间(ms)

    def __init__(self, pid: int, note: Optional[SimpleNote] = None, age: int = 0):
        self.id = pid
        self.note = note
        self.age = age
        self.sent_at = -10 ** 9
        self.pressed_at = -10 ** 9


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
release_ms = 300  # 指针空闲超过该时长即抬起
MIN_PRESS_MS = 40  # 单次按压的最短持续时间，过短的按压游戏可能无法识别


def flick_path_clear(blocks: BlockAreas, t_ms: int, x0: float, y0: float, dx: float, dy: float) -> bool:
    """滑动轨迹的每个采样点都不在噪域(含边距)内"""
    duration = flick_end - flick_start
    for t in range(t_ms, t_ms + duration + 1, flick_step):
        k = (t - t_ms) / duration
        if blocks.blocked(x0 + dx * k, y0 + dy * k, t / 1000, MARGIN):
            return False
    return True


def press_clear(blocks: BlockAreas, t_ms: int, x: float, y: float, duration: int) -> bool:
    """静止按压的整个持续时段内，触点都不在噪域(含边距)内"""
    for t in range(t_ms, t_ms + duration + 1, flick_step):
        if blocks.blocked(x, y, t / 1000, MARGIN):
            return False
    return True


def find_clear_press(blocks: BlockAreas, t_ms: int, pos: tuple[float, float],
                     duration: int) -> Optional[tuple[float, float]]:
    """由近及远搜索静止按压点，返回整个按压期间都不进入噪域的点"""
    for x0, y0 in nearby_points(*pos):
        if press_clear(blocks, t_ms, x0, y0, duration):
            return x0, y0
    return None


def find_clear_flick(blocks: BlockAreas, t_ms: int, note: 'SimpleNote') -> Optional[tuple[float, float, float, float]]:
    """由近及远搜索起点，并允许反向滑动，返回轨迹不进入噪域的 (x0, y0, dx, dy)"""
    alpha = note.angle
    dx, dy = math.sin(alpha) * flick_scale_factor, math.cos(alpha) * flick_scale_factor
    for x0, y0 in nearby_points(*note.pos):
        for sign in (1, -1):
            if flick_path_clear(blocks, t_ms, x0, y0, sign * dx, sign * dy):
                return x0, y0, sign * dx, sign * dy
    return None


class PointerAllocator:
    pointers: list[Pointer]
    events: dict[int, list[TouchEvent]]
    last_timestamp: Optional[int]
    now: int
    reserved: set[int]

    def __init__(self, max_pointers_count: int = 10, begin_at: int = 1000):
        self.pointers = [Pointer(i + begin_at) for i in range(max_pointers_count)]
        self.events = {}
        self.last_timestamp = None
        self.reserved = set()
    def _release_at(self, pointer: Pointer) -> int:
        return min(max(self.now - pointer.age + 1, pointer.pressed_at + MIN_PRESS_MS), self.now)

    def alloc(self, note: SimpleNote) -> Pointer:
        free = [p for p in self.pointers
                if p.id not in self.reserved and (p.note is None or p.age > 0)]
        ready = [p for p in free if p.note is None or p.pressed_at + MIN_PRESS_MS <= self.now]
        usable_pointers = ready or free  # 优先满足最短按压时长，指针不足时放宽
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

    def match(self, notes: list[SimpleNote]) -> list[Optional[Pointer]]:
        """为每个 drag 音符分配一个不重复的指针：按距离从近到远贪心匹配，同一指针只能对应一个音符"""
        candidates = []  # (距离平方, 音符序号, 指针)
        for i, note in enumerate(notes):
            ox, oy = note.pos
            ca, sa = math.cos(note.angle), math.sin(note.angle)
            for pointer in self.pointers:
                if pointer.note is None or pointer.age < 0:
                    continue
                px, py = pointer.note.pos
                if abs((px - ox) * ca + (py - oy) * sa) < 100:
                    candidates.append(((px - ox) ** 2 + (py - oy) ** 2, i, pointer))
        result: list[Optional[Pointer]] = [None] * len(notes)
        used: set[int] = set()
        for _, i, pointer in sorted(candidates, key=lambda c: c[0]):
            if result[i] is None and pointer.id not in used:
                result[i] = pointer
                used.add(pointer.id)
        return result

    def _insert(self, timestamp: int, event: TouchEvent):
        if timestamp not in self.events:
            self.events[timestamp] = []
        self.events[timestamp].append(event)

    def _down(self, pointer: Pointer, note: SimpleNote):
        # 复用指针前，先在其上一次事件之后释放它（alloc保证 age > 0，因此释放时间 <= now）
        if pointer.note is not None:
            self._insert(self._release_at(pointer), TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
        pointer.note = note
        pointer.age = 0
        pointer.sent_at = self.now
        pointer.pressed_at = self.now
        self._insert(self.now, TouchEvent(note.pos, TouchAction.DOWN, pointer.id))

    def _tap(self, pointer: Pointer, note: SimpleNote, blocks: BlockAreas):
        if not press_clear(blocks, self.now, *note.pos, release_ms):
            found = find_clear_press(blocks, self.now, note.pos, release_ms)
            if found is not None:
                note.pos = found
        self._down(pointer, note)

    def _flick(self, pointer: Pointer, note: SimpleNote, blocks: BlockAreas):
        # 在 [now, now + (flick_end - flick_start)] 内单调滑动，每 flick_step ms 发送一次MOVE
        duration = flick_end - flick_start
        if pointer.note is not None:
            self._insert(self._release_at(pointer), TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
        pointer.pressed_at = self.now
        x0, y0 = note.pos
        alpha = note.angle
        dx, dy = math.sin(alpha) * flick_scale_factor, math.cos(alpha) * flick_scale_factor
        if not flick_path_clear(blocks, self.now, x0, y0, dx, dy):
            found = find_clear_flick(blocks, self.now, note)
            if found is not None:
                x0, y0, dx, dy = found
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

        # 本帧仍在按住(hold)的指针不可被 tap/flick 复用
        drag_notes = frame.unallocated[Note.DRAG - 1]
        matched = self.match(drag_notes)
        self.reserved = {p.id for p in matched if p is not None}

        # 步骤1：分配tap
        for note in frame.taps():
            pointer = self.alloc(note)
            self._tap(pointer, note, frame.blocks)

        # 步骤2: 分配flick
        for note in frame.flicks():
            pointer = self.alloc(note)
            self._flick(pointer, note, frame.blocks)

        # 步骤3：分配drag（沿用步骤0的一对一匹配结果；预留指针未被tap/flick占用）
        for note, pointer in zip(drag_notes, matched):
            if pointer is not None:
                pointer.note = note
                pointer.age = 0
                if self.now - pointer.sent_at >= drag_step:
                    self._insert(self.now, TouchEvent(note.pos, TouchAction.MOVE, pointer.id))
                    pointer.sent_at = self.now
                continue
            pointer = self.alloc(note)
            self._drag(pointer, note)
        frame.unallocated[Note.DRAG - 1] = []
        self.reserved = set()

        # 步骤4：抬起长时间空闲的指针
        for pointer in self.pointers:
            if pointer.note is not None and pointer.age >= release_ms:
                self._insert(self.now - pointer.age + 1, TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
                pointer.note = None

        self.last_timestamp = frame.timestamp

    def done(self):
        # 释放仍按住的指针，避免结束后残留按下状态
        for pointer in self.pointers:
            if pointer.note is not None:
                self._insert(self.now - pointer.age + 1, TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
                pointer.note = None
        return self.events


def solve(chart: Chart) -> dict[int, list[TouchEvent]]:
    frames = Frames(chart.block_areas)

    print('正在统计帧...', end='')
    stdout.flush()
    # 统计frames
    seen: set[tuple[int, int, float, float]] = set()  # 谱面中同时刻同位置的重复音符只保留一个
    for line in chart.judge_lines:
        for note in line.notes_above + line.notes_below:
            ms = round(line.seconds(note.time) * 1000)
            off_x = note.x * 72
            x, y = line.pos(note.time)
            alpha = - line.angle(note.time) * math.pi / 180
            pos = x + off_x * math.cos(alpha), y + off_x * math.sin(alpha)
            key = (ms, note.typ, round(pos[0], 1), round(pos[1], 1))
            if key in seen:
                continue
            seen.add(key)
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
