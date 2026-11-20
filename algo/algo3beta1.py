"""激进的指针规划算法（algo3beta1：独立实验分支，algo3 不做修改）
这种算法把hold拆分成一个tap和若干个drag，各自规划

实验分支新增：
  - FLICK 轨迹以 1 ms 步长做 NF 判定（algo3 为 5 ms 采样）
  - DRAG/HOLD 延续的 DOWN 与每个 MOVE 在其自身时刻做 NF 校验，并记录违规

噪域规则：
  - TAP/FLICK 的触点必须落在噪域外，且到判定线的垂直距离 >= MIN_DIST，
    迁移距离不超过 MAX_RELOCATION_DISTANCE；找不到合法点时跳过该音符并记录原因。
  - HOLD 的 DRAG/MOVE 严格跟随判定线目标点，不做任何噪域避让与位置偏移，
    其噪域冲突作为已知约束单独统计。
"""
import math
from enum import Enum
from sys import stdout
from typing import Optional, Iterator, Union

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
        self.used = False  # 是否曾被分配过音符，用于统计复用次数


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
flick_check_step = 1  # 轨迹校验步长(ms)，比发送步长细，避免采样漏检
drag_step = 8  # hold延续时每隔多少ms发送一次MOVE，过密会导致游戏卡顿
release_ms = 300  # 指针空闲超过该时长即抬起
MIN_PRESS_MS = 40  # 单次按压的最短持续时间，过短的按压游戏可能无法识别
MAX_POINTERS: Optional[int] = None  # 平台同时触点上限未知，None 表示不限制


class AllocFailure(Enum):
    """指针分配失败的原因（与 PlacementFailure 区分：这里是资源耗尽而非落点无解）"""
    POINTER_LIMIT_EXCEEDED = 'POINTER_LIMIT_EXCEEDED'  # 已达 max_pointers 且无可复用指针


def flick_path_clear(blocks: BlockAreas, t_ms: int, x0: float, y0: float, dx: float, dy: float,
                     line: Optional[tuple[tuple[float, float], tuple[float, float]]] = None,
                     min_dist: float = 0.0) -> bool:
    """滑动轨迹的每个采样点都不在噪域(含动态边距)内，且满足判定线垂直距离约束"""
    duration = flick_end - flick_start
    for t in range(t_ms, t_ms + duration + 1, flick_check_step):
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


# ---- 实验分支：指针路径 NF 校验（只记录，不改变事件） ----
NF_CHECK_STEP_MS = 1  # 路径校验步长(ms)


def path_nf_violations(blocks: BlockAreas, t_start_ms: int, t_end_ms: int,
                       path_at, step_ms: int = NF_CHECK_STEP_MS) -> list[tuple[int, float, float]]:
    """对 [t_start_ms, t_end_ms] 区间内的指针路径逐 step_ms 采样，返回所有落在噪域内的采样点。

    path_at(t_ms) -> (x, y) 给出 t 时刻的指针真实位置（像素，y 向下）。
    返回 [(t_ms, x, y), ...]；为空表示该区间无 NF 冲突。
    """
    hits: list[tuple[int, float, float]] = []
    for t in range(t_start_ms, t_end_ms + 1, step_ms):
        x, y = path_at(t)
        if blocks.blocked(x, y, t / 1000, margin_at(t / 1000)):
            hits.append((t, x, y))
    return hits


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
    skipped: list[tuple[int, int, float, float, Union[PlacementFailure, AllocFailure]]]  # (时间ms, 音符类型, 原始x, 原始y, 原因)

    def __init__(self, max_pointers_count: int = 10, begin_at: int = 1000,
                 max_pointers: Optional[int] = MAX_POINTERS):
        if max_pointers is not None and max_pointers_count > max_pointers:
            raise ValueError(f'初始指针数 {max_pointers_count} 超过上限 {max_pointers}')
        self.pointers = [Pointer(i + begin_at) for i in range(max_pointers_count)]
        self.max_pointers = max_pointers
        self._next_id = begin_at + max_pointers_count  # 新建指针ID单调递增，不与已有ID冲突
        self.events = {}
        self.last_timestamp = None
        self.reserved = set()
        self.skipped = []
        self.tags: dict[tuple[int, int], tuple[int, float]] = {}  # (pointer, DOWN ms) -> (note type, normal angle)
        self.last_pos: dict[int, tuple[int, float, float]] = {}  # pointer id -> (ms, x, y) of last sent event
        self.drag_failures: list[tuple[int, int, float, float, int]] = []  # (ms, note type, x, y, pointer id)
        self.created_count = 0
        self.reuse_count = 0
        self.allocation_failures = 0
        self.peak_active = 0

    def stats(self) -> dict[str, int]:
        return {'created': self.created_count, 'pool_size': len(self.pointers),
                'peak_active': self.peak_active, 'reuse': self.reuse_count,
                'alloc_failures': self.allocation_failures}

    def _mark_used(self, pointer: Pointer):
        if pointer.used:
            self.reuse_count += 1
        pointer.used = True

    def _release_at(self, pointer: Pointer) -> int:
        return min(max(self.now - pointer.age + 1, pointer.pressed_at + MIN_PRESS_MS), self.now)

    def alloc(self, note: SimpleNote) -> Optional[Pointer]:
        """取得一个用于按下 note 的指针。

        策略（MIN_PRESS_MS）：只复用已满足最短按压时长的闲置指针；若没有，则新建。
        不复用仍处于按压锁定期内的指针，因为那样会迫使其在 MIN_PRESS_MS 内抬起，
        违反按压时长约束。已达 max_pointers 且无可用指针时返回 None，由调用方记录跳过。
        """
        free = [p for p in self.pointers
                if p.id not in self.reserved and (p.note is None or p.age > 0)]
        ready = [p for p in free if p.note is None or p.pressed_at + MIN_PRESS_MS <= self.now]
        if ready:
            return min(ready, key=lambda p: distance_of(p.note, note))  # 优先使用废弃的Pointer
        if self.max_pointers is not None and len(self.pointers) >= self.max_pointers:
            return None
        pointer = Pointer(self._next_id)
        self._next_id += 1
        self.pointers.append(pointer)
        self.created_count += 1
        return pointer

    def _skip(self, note: SimpleNote, reason: Union[PlacementFailure, AllocFailure]):
        """记录被跳过的音符；资源耗尽类原因同时计入 allocation_failures"""
        if isinstance(reason, AllocFailure):
            self.allocation_failures += 1
        self.skipped.append((self.now, note.note_type, note.pos[0], note.pos[1], reason))

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

    def _last_xy(self, pointer: Pointer) -> tuple[float, float]:
        last = self.last_pos.get(pointer.id)
        return (last[1], last[2]) if last is not None else pointer.note.pos

    def _down(self, pointer: Pointer, note: SimpleNote, pos: tuple[float, float]):
        # 复用指针前，先在其上一次事件之后释放它（alloc保证 age > 0，因此释放时间 <= now）
        if pointer.note is not None:
            self._insert(self._release_at(pointer), TouchEvent(self._last_xy(pointer), TouchAction.UP, pointer.id))
        self._mark_used(pointer)
        pointer.note = note
        pointer.age = 0
        pointer.sent_at = self.now
        pointer.pressed_at = self.now
        self._insert(self.now, TouchEvent(pos, TouchAction.DOWN, pointer.id))
        self.last_pos[pointer.id] = (self.now, pos[0], pos[1])
        self.tags[(pointer.id, self.now)] = (note.note_type, note.angle)

    def _tap(self, note: SimpleNote, blocks: BlockAreas) -> bool:
        """按下 TAP。先验证落点，合法后才取得指针，避免无效音符产生多余指针；
        无合法点或指针上限耗尽时记录到 skipped，返回 False 且不发送任何事件"""
        original = note.pos
        found, reason = find_clear_press(blocks, self.now, original, release_ms, note.line, MIN_DIST,
                                         -math.sin(note.angle), math.cos(note.angle))
        if found is None:
            self._skip(note, reason or PlacementFailure.NO_VALID_POSITION)
            return False
        pointer = self.alloc(note)  # 指针选择仍基于原始位置，与落点修正前保持一致
        if pointer is None:
            self._skip(note, AllocFailure.POINTER_LIMIT_EXCEEDED)
            return False
        note.pos = found
        self._down(pointer, note, found)
        return True

    def _flick(self, note: SimpleNote, blocks: BlockAreas) -> bool:
        """执行 FLICK。先验证轨迹，合法后才取得指针；失败时记录到 skipped 且不发送任何事件"""
        duration = flick_end - flick_start
        alpha = note.angle
        dx, dy = math.sin(alpha) * flick_scale_factor, math.cos(alpha) * flick_scale_factor
        x0, y0 = note.pos
        if not flick_path_clear(blocks, self.now, x0, y0, dx, dy, note.line, MIN_DIST):
            found, reason = find_clear_flick(blocks, self.now, note, MIN_DIST)
            if found is None:
                self._skip(note, reason or PlacementFailure.NO_VALID_POSITION)
                return False
            x0, y0, dx, dy = found
        pointer = self.alloc(note)
        if pointer is None:
            self._skip(note, AllocFailure.POINTER_LIMIT_EXCEEDED)
            return False
        if pointer.note is not None:
            self._insert(self._release_at(pointer), TouchEvent(self._last_xy(pointer), TouchAction.UP, pointer.id))
        self._mark_used(pointer)
        pointer.pressed_at = self.now
        self._insert(self.now, TouchEvent((x0, y0), TouchAction.DOWN, pointer.id))
        self.tags[(pointer.id, self.now)] = (note.note_type, note.angle)
        for t in range(self.now + flick_step, self.now + duration + 1, flick_step):
            k = (t - self.now) / duration
            self._insert(t, TouchEvent((x0 + dx * k, y0 + dy * k), TouchAction.MOVE, pointer.id))
        self.last_pos[pointer.id] = (self.now + duration, x0 + dx, y0 + dy)
        # 滑动结束点，供后续 check() 与 UP 使用
        note.pos = (x0 + dx, y0 + dy)
        pointer.note = note
        pointer.age = flick_start - flick_end  # 负值：滑动期间该指针不可被分配
        return True

    def _drag(self, pointer: Pointer, note: SimpleNote, blocks: BlockAreas):
        """拖动按压的新起点：经局部绕行后按下"""
        self._down(pointer, note, self._drag_pos(note, blocks, None))

    def _drag_pos(self, note: SimpleNote, blocks: BlockAreas,
                  prev: Optional[tuple[int, float, float]]) -> tuple[float, float]:
        """拖动点：优先判定线目标；不合法则在小范围内取与上一发送点连线不穿过 NF 的最近点，否则记录失败"""
        tx, ty = note.pos
        candidates = [(tx, ty)] + sorted(_SCREEN_GRID, key=lambda q: (q[0] - tx) ** 2 + (q[1] - ty) ** 2)
        for x, y in candidates:
            if not _point_clear(blocks, self.now, x, y):
                continue
            if prev is None or _segment_clear(blocks, prev[0], (prev[1], prev[2]), self.now, (x, y)):
                return x, y
        self.drag_failures.append((self.now, note.note_type, tx, ty, -1))
        return tx, ty

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
            self._tap(note, frame.blocks)

        # 步骤2: 分配flick（无解时不发送DOWN）
        for note in frame.flicks():
            self._flick(note, frame.blocks)

        # 步骤3：分配drag（沿用步骤0的一对一匹配结果；预留指针未被tap/flick占用）
        for note, pointer in zip(drag_notes, matched):
            if pointer is not None:
                pointer.note = note
                pointer.age = 0
                if self.now - pointer.sent_at >= drag_step:
                    pos = self._drag_pos(note, frame.blocks, self.last_pos.get(pointer.id))
                    self._insert(self.now, TouchEvent(pos, TouchAction.MOVE, pointer.id))
                    pointer.sent_at = self.now
                    self.last_pos[pointer.id] = (self.now, pos[0], pos[1])
                continue
            pointer = self.alloc(note)
            if pointer is None:
                self._skip(note, AllocFailure.POINTER_LIMIT_EXCEEDED)
                continue
            self._drag(pointer, note, frame.blocks)
        frame.unallocated[Note.DRAG - 1] = []
        self.reserved = set()

        # 步骤4：抬起长时间空闲的指针
        for pointer in self.pointers:
            if pointer.note is not None and pointer.age >= release_ms:
                self._insert(self.now - pointer.age + 1, TouchEvent(self._last_xy(pointer), TouchAction.UP, pointer.id))
                pointer.note = None

        self.peak_active = max(self.peak_active, sum(1 for p in self.pointers if p.note is not None))
        self.last_timestamp = frame.timestamp

    def done(self):
        # 释放仍按住的指针，避免结束后残留按下状态
        for pointer in self.pointers:
            if pointer.note is not None:
                self._insert(self.now - pointer.age + 1, TouchEvent(self._last_xy(pointer), TouchAction.UP, pointer.id))
                pointer.note = None
        return self.events


DRAG_SEARCH_STEP = 4  # 拖动避让候选网格步长(px)，仅在目标点不可用时搜索
_SCREEN_GRID = [(float(x), float(y)) for x in range(0, 1281, DRAG_SEARCH_STEP)
                for y in range(0, 721, DRAG_SEARCH_STEP)]


def _point_clear(blocks: BlockAreas, t_ms: int, x: float, y: float) -> bool:
    if not (0 <= x <= 1280 and 0 <= y <= 720):
        return False
    return not blocks.blocked(x, y, t_ms / 1000, margin_at(t_ms / 1000))


def _segment_clear(blocks: BlockAreas, t0: int, p0: tuple[float, float],
                   t1: int, p1: tuple[float, float]) -> bool:
    """逐 1 ms 检查两发送点之间的线性插值路径是否穿过 NF"""
    if t1 <= t0:
        return _point_clear(blocks, t1, p1[0], p1[1])
    for tt in range(t0 + 1, t1 + 1):
        k = (tt - t0) / (t1 - t0)
        if not _point_clear(blocks, tt, p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k):
            return False
    return True


def validate_pointer_paths(blocks: BlockAreas, events: dict[int, list[TouchEvent]]) -> list[dict]:
    """对每个指针的事件序列，在相邻事件之间按 NF_CHECK_STEP_MS 采样真实路径，
    记录所有落入噪域的采样点（包括 DOWN 位置、MOVE 位置、UP 位置及中间插值轨迹）。
    违规记录仅用于报告；不修改、不删除任何事件。"""
    per_pointer: dict[int, list[tuple[int, TouchAction, tuple[float, float]]]] = {}
    for t in sorted(events):
        for ev in events[t]:
            per_pointer.setdefault(ev.pointer, []).append((t, ev.action, ev.pos))

    records: list[dict] = []
    for pid, seq in per_pointer.items():
        seq.sort(key=lambda e: e[0])
        down_t = None
        for i, (t, action, pos) in enumerate(seq):
            if action == TouchAction.DOWN:
                down_t = t
            if action == TouchAction.UP:
                down_t = None
            # 事件点本身在其时刻校验
            if blocks.blocked(pos[0], pos[1], t / 1000, margin_at(t / 1000)):
                records.append({'pointer': pid, 'kind': action.name, 'time_ms': t,
                                'x': pos[0], 'y': pos[1], 'segment': 'event'})
            # 与下一事件之间的插值路径（仅对仍按住的同一指针）
            if i + 1 < len(seq) and seq[i + 1][1] != TouchAction.DOWN and down_t is not None:
                t2, _, pos2 = seq[i + 1]
                if t2 <= t:
                    continue

                def path_at(tt, t0=t, p0=pos, t1=t2, p1=pos2):
                    k = (tt - t0) / (t1 - t0)
                    return p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k

                for tt, x, y in path_nf_violations(blocks, t + NF_CHECK_STEP_MS, t2 - NF_CHECK_STEP_MS,
                                                   path_at, NF_CHECK_STEP_MS):
                    records.append({'pointer': pid, 'kind': 'SEGMENT', 'time_ms': tt,
                                    'x': x, 'y': y, 'segment': f'{t}->{t2}'})
    return records


def solve(chart: Chart, stats: Optional[list] = None,
          violations_out: Optional[list] = None, drag_out: Optional[list] = None) -> dict[int, list[TouchEvent]]:
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

    allocator = PointerAllocator(max_pointers=MAX_POINTERS)

    print('正在规划触控事件...', end='')
    stdout.flush()

    for frame in frames:
        allocator.allocate(frame)

    print('规划完毕.')
    if stats is not None:
        stats.extend(allocator.skipped)
    events = allocator.done()
    if drag_out is not None:
        drag_out.extend(allocator.drag_failures)
    violations = validate_pointer_paths(chart.block_areas, events)
    if violations_out is not None:
        violations_out.extend(violations)
    return events
