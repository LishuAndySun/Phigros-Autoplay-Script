"""激进的指针规划算法
这种算法把hold拆分成一个tap和若干个drag，各自规划

噪域规则：
  - TAP/FLICK 的触点必须落在噪域外，且到判定线的垂直距离 >= MIN_DIST，
    迁移距离不超过 MAX_RELOCATION_DISTANCE；找不到合法点时跳过该音符并记录原因。
  - HOLD 的 DRAG/MOVE 严格跟随判定线目标点，不做任何噪域避让与位置偏移，
    其噪域冲突作为已知约束单独统计。
"""
import math
from sys import stdout
from typing import Optional, Iterator

from block_area import (BlockAreas, MARGIN, MIN_DIST, MAX_RELOCATION_DISTANCE, PlacementFailure,
                        judge_line_ends, margin_at, nearby_points, point_line_distance)
from chart import Chart
from note import Note
from utils import recalc_pos
from .algo_base import TouchAction, TouchEvent


class SimpleNote:
    note_type: int
    timestamp: int
    pos: tuple[float, float]
    angle: float
    line: Optional[tuple[tuple[float, float], tuple[float, float]]]  # 判定线两端点
    note_id: int  # 谱面音符序号，用于报告无解原因

    def __init__(self, note_type: int, timestamp: int, pos: tuple[float, float], angle: float,
                 line: Optional[tuple[tuple[float, float], tuple[float, float]]] = None, note_id: int = -1):
        self.note_type = note_type
        self.timestamp = timestamp
        self.pos = pos
        self.angle = angle
        self.line = line
        self.note_id = note_id


class Frame:
    timestamp: int

    unallocated: list[list[SimpleNote]]
    allocated: list[list[SimpleNote]]

    def __init__(self, timestamp: int, blocks: BlockAreas):
        self.timestamp = timestamp
        self.blocks = blocks

        self.unallocated = [[] for _ in range(4)]
        self.allocated = [[] for _ in range(4)]

    def add(self, note_type: int, pos: tuple[float, float], angle: float,
            line: Optional[tuple[tuple[float, float], tuple[float, float]]] = None, note_id: int = -1):
        pos = recalc_pos(pos, math.sin(angle), math.cos(angle))
        # HOLD 的 DRAG 采样严格跟随判定线，不做噪域避让；
        # TAP/FLICK 的位置避也让 PointerAllocator 在知道按压时长后再做，
        # 这里只负责把角度换算后的目标位置交出去。
        self.unallocated[note_type - 1].append(
            SimpleNote(note_type, self.timestamp, pos, angle, line, note_id))

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


def flick_path_clear(blocks: BlockAreas, t_ms: int, x0: float, y0: float, dx: float, dy: float,
                     line: Optional[tuple[tuple[float, float], tuple[float, float]]] = None,
                     min_dist: float = 0.0) -> bool:
    """滑动轨迹的每个采样点都不在噪域(含动态边距)内，且满足判定线垂直距离约束"""
    duration = flick_end - flick_start
    for t in range(t_ms, t_ms + duration + 1, flick_step):
        k = (t - t_ms) / duration
        px, py = x0 + dx * k, y0 + dy * k
        if not (0 <= px <= 1280 and 0 <= py <= 720):
            return False
        if blocks.blocked(px, py, t / 1000, margin_at(t / 1000)):
            return False
        if line is not None and min_dist > 0:
            try:
                if point_line_distance((px, py), line) < min_dist:
                    return False
            except ValueError:
                return False
    return True


def find_clear_press(blocks: BlockAreas, t_ms: int, pos: tuple[float, float], duration: int,
                     line: Optional[tuple[tuple[float, float], tuple[float, float]]] = None,
                     min_dist: float = 0.0, nx_dir: float = 0.0, ny_dir: float = 1.0,
                     max_relocation: float = MAX_RELOCATION_DISTANCE
                     ) -> tuple[Optional[tuple[float, float]], Optional[PlacementFailure]]:
    """寻找整个按压期间都合法的静止点，失败时返回明确的失败原因"""
    return blocks.search_point(pos, t_ms / 1000, nx_dir, ny_dir, line, min_dist,
                               max_relocation, duration=duration)


def find_clear_flick(blocks: BlockAreas, t_ms: int, note: 'SimpleNote',
                     min_dist: float = 0.0, max_relocation: float = MAX_RELOCATION_DISTANCE
                     ) -> tuple[Optional[tuple[float, float, float, float]], Optional[PlacementFailure]]:
    """寻找滑动起点(允许反向)，使整条轨迹合法；失败时返回明确的失败原因"""
    alpha = note.angle
    dx, dy = math.sin(alpha) * flick_scale_factor, math.cos(alpha) * flick_scale_factor
    duration = flick_end - flick_start
    reason: Optional[PlacementFailure] = None

    def try_origin(x0: float, y0: float) -> Optional[tuple[float, float, float, float]]:
        for sign in (1, -1):
            if flick_path_clear(blocks, t_ms, x0, y0, sign * dx, sign * dy, note.line, min_dist):
                return x0, y0, sign * dx, sign * dy
        return None

    found = try_origin(*note.pos)
    if found is not None:
        return found, None

    # 先用 search_point 找轨迹起点附近的合法静止点，再在起点邻域内尝试两个方向
    start, fail = blocks.search_point(note.pos, t_ms / 1000, -math.sin(alpha), math.cos(alpha),
                                      note.line, min_dist, max_relocation, duration=duration)
    if start is not None:
        found = try_origin(*start)
        if found is not None:
            return found, None
        reason = PlacementFailure.NO_VALID_POSITION
    else:
        reason = fail

    # 由近及远兜底：逐点检查整条轨迹
    for x0, y0 in nearby_points(*note.pos, max_radius=max_relocation):
        if math.hypot(x0 - note.pos[0], y0 - note.pos[1]) > max_relocation:
            continue
        found = try_origin(x0, y0)
        if found is not None:
            return found, None
    if reason is None:
        # 邻域内轨迹均不合法，检查是否存在「有解但超出迁移上限」的情况
        for x0, y0 in nearby_points(*note.pos, max_radius=float('inf')):
            if math.hypot(x0 - note.pos[0], y0 - note.pos[1]) <= max_relocation:
                continue
            if try_origin(x0, y0) is not None:
                return None, PlacementFailure.RELOCATION_LIMIT_EXCEEDED
        reason = PlacementFailure.NO_VALID_POSITION
    return None, reason


class PointerAllocator:
    pointers: list[Pointer]
    events: dict[int, list[TouchEvent]]
    last_timestamp: Optional[int]
    now: int
    reserved: set[int]
    skipped: list[tuple[int, int, float, float, PlacementFailure]]  # (时间ms, 音符类型, 原始x, 原始y, 原因)

    def __init__(self, max_pointers_count: int = 10, begin_at: int = 1000):
        self.pointers = [Pointer(i + begin_at) for i in range(max_pointers_count)]
        self.events = {}
        self.last_timestamp = None
        self.reserved = set()
        self.skipped = []
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

    def _tap(self, pointer: Pointer, note: SimpleNote, blocks: BlockAreas) -> bool:
        """按下 TAP；找不到合法点时返回 False 且不发送任何事件"""
        original = note.pos
        found, reason = find_clear_press(blocks, self.now, original, release_ms, note.line, MIN_DIST,
                                         -math.sin(note.angle), math.cos(note.angle))
        if found is None:
            self.skipped.append((self.now, note.note_type, original[0], original[1],
                                 reason or PlacementFailure.NO_VALID_POSITION))
            return False
        note.pos = found
        self._down(pointer, note)
        return True

    def _flick(self, pointer: Pointer, note: SimpleNote, blocks: BlockAreas) -> bool:
        """执行 FLICK；找不到合法轨迹时返回 False 且不发送任何事件"""
        duration = flick_end - flick_start
        alpha = note.angle
        dx, dy = math.sin(alpha) * flick_scale_factor, math.cos(alpha) * flick_scale_factor
        x0, y0 = note.pos
        if not flick_path_clear(blocks, self.now, x0, y0, dx, dy, note.line, MIN_DIST):
            found, reason = find_clear_flick(blocks, self.now, note, MIN_DIST)
            if found is None:
                self.skipped.append((self.now, note.note_type, note.pos[0], note.pos[1],
                                     reason or PlacementFailure.NO_VALID_POSITION))
                return False
            x0, y0, dx, dy = found
        if pointer.note is not None:
            self._insert(self._release_at(pointer), TouchEvent(pointer.note.pos, TouchAction.UP, pointer.id))
        pointer.pressed_at = self.now
        self._insert(self.now, TouchEvent((x0, y0), TouchAction.DOWN, pointer.id))
        for t in range(self.now + flick_step, self.now + duration + 1, flick_step):
            k = (t - self.now) / duration
            self._insert(t, TouchEvent((x0 + dx * k, y0 + dy * k), TouchAction.MOVE, pointer.id))
        # 滑动结束点，供后续 check() 与 UP 使用
        note.pos = (x0 + dx, y0 + dy)
        pointer.note = note
        pointer.age = flick_start - flick_end  # 负值：滑动期间该指针不可被分配
        return True

    def _drag(self, pointer: Pointer, note: SimpleNote):
        """HOLD 的延续按压：严格跟随判定线目标点，不做噪域避让、不改位置"""
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

        # 步骤1：分配tap（无解时不发送DOWN）
        for note in frame.taps():
            pointer = self.alloc(note)
            self._tap(pointer, note, frame.blocks)

        # 步骤2: 分配flick（无解时不发送DOWN）
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


def solve(chart: Chart, stats: Optional[list] = None) -> dict[int, list[TouchEvent]]:
    frames = Frames(chart.block_areas)

    print('正在统计帧...', end='')
    stdout.flush()
    # 统计frames
    seen: set[tuple[int, int, float, float]] = set()  # 谱面中同时刻同位置的重复音符只保留一个
    note_id = 0
    for line in chart.judge_lines:
        for note in line.notes_above + line.notes_below:
            note_id += 1
            ms = round(line.seconds(note.time) * 1000)
            off_x = note.x * 72
            x, y = line.pos(note.time)
            alpha = - line.angle(note.time) * math.pi / 180
            pos = x + off_x * math.cos(alpha), y + off_x * math.sin(alpha)
            key = (ms, note.typ, round(pos[0], 1), round(pos[1], 1))
            if key in seen:
                continue
            seen.add(key)
            # 判定线两端点，用于触点垂直距离约束
            ends = judge_line_ends(line.pos(note.time), line.angle(note.time))
            if note.typ == Note.HOLD:
                hold_ms = math.ceil(line.seconds(note.hold) * 1000)
                frames[ms].add(Note.TAP, pos, alpha, ends, note_id)
                for offset in range(1, hold_ms + 1):
                    alpha = - line.angle(line.time((ms + offset) / 1000)) * math.pi / 180
                    ends_h = judge_line_ends(line.pos(line.time((ms + offset) / 1000)),
                                             line.angle(line.time((ms + offset) / 1000)))
                    # HOLD 的 DRAG 严格跟随判定线，不传判定线约束也不做噪域避让
                    frames[ms + offset].add(Note.DRAG,
                                            line.pos_of(note, line.time((ms + offset) / 1000)),
                                            alpha, ends_h, note_id)
            elif note.typ == Note.FLICK:
                frames[ms + flick_start].add(Note.FLICK, pos, alpha, ends, note_id)
            else:
                frames[ms].add(note.typ, pos, alpha, ends, note_id)

    print(f'统计完毕，当前谱面共计{len(frames)}帧')

    allocator = PointerAllocator()

    print('正在规划触控事件...', end='')
    stdout.flush()

    for frame in frames:
        allocator.allocate(frame)

    print('规划完毕.')
    if stats is not None:
        stats.extend(allocator.skipped)
    return allocator.done()
