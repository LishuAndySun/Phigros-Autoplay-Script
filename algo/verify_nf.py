"""NF-aware Temporal Spatial Verification Module for Algo3

独立于 Algo3 核心算法的噪域感知时空验证模块。
不修改任何 Algo3 源码，仅读取 Algo3 的输出事件流进行验证。

条件触发：仅当谱面存在 blockAreaList 时激活，否则零开销跳过。

架构（9 个组件）：
  1. NFDetector       — 检测噪域是否存在及其时间线
  2. FrameGenerator    — 从 Algo3 事件流生成验证帧
  3. PositionCalculator — 计算实际触点位置（含指针状态追踪）
  4. SpatialGraph      — 网格化空间索引
  5. NFMapper          — 预计算噪域时间覆盖
  6. TaskMapper        — 将 Algo3 TouchEvent 映射为验证任务
  7. SpatialVerifier   — 核心验证引擎
  8. PathReplanner     — 对可修复违规尝试重规划
  9. VerificationReport — 结构化输出
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from .algo_base import TouchAction, TouchEvent
from block_area import (
    BlockAreas, MARGIN, MIN_DIST, MAX_RELOCATION_DISTANCE, PlacementFailure,
    judge_line_ends, margin_at, nearby_points, point_line_distance,
    SCREEN_W, SCREEN_H
)
from chart import Chart


# ============================================================================
# 1. NFDetector — 噪域存在性检测
# ============================================================================

class NFDetectionResult(Enum):
    NONE = 'none'               # 无噪域
    STATIC = 'static'           # 静态噪域（enable/disable 覆盖全曲）
    DYNAMIC = 'dynamic'         # 动态噪域（多段 enable/disable）


@dataclass
class NFDetector:
    """检测谱面是否存在噪域，返回类型与时间线摘要。"""
    areas: Optional[BlockAreas]
    result: NFDetectionResult = NFDetectionResult.NONE
    active_intervals: list[tuple[float, float]] = field(default_factory=list)
    total_active_seconds: float = 0.0

    def __post_init__(self):
        if self.areas is None:
            return
        self._detect()

    def _detect(self):
        if not self.areas or not self.areas.add:
            self.result = NFDetectionResult.NONE
            return

        # 收集所有 enable 区间
        intervals = []
        for bucket_key, blist in self.areas.add.items():
            for ba in blist:
                t_start = max(ba.enable, 0.0)
                t_end = min(ba.disable, 3600.0)
                if t_start < t_end:
                    intervals.append((t_start, t_end))

        if not intervals:
            self.result = NFDetectionResult.NONE
            return

        # 合并重叠区间
        intervals.sort()
        merged = [intervals[0]]
        for start, end in intervals[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        self.active_intervals = merged
        self.total_active_seconds = sum(e - s for s, e in merged)

        # 判断 static vs dynamic
        if len(merged) == 1 and merged[0][0] <= 0.0 and merged[0][1] >= 3600.0:
            self.result = NFDetectionResult.STATIC
        else:
            self.result = NFDetectionResult.DYNAMIC

    @property
    def exists(self) -> bool:
        return self.result != NFDetectionResult.NONE

    def is_active_at(self, t_seconds: float) -> bool:
        """t 时刻是否有噪域覆盖（基于时间区间快速判断）"""
        if not self.exists:
            return False
        for start, end in self.active_intervals:
            if start <= t_seconds <= end:
                return True
        return False


# ============================================================================
# 2. FrameGenerator — 从 Algo3 事件流生成验证帧
# ============================================================================

@dataclass
class VerificationFrame:
    """验证帧：按时间桶聚合的事件集合。"""
    timestamp_ms: int
    events: list[TouchEvent] = field(default_factory=list)
    pointers_active: set[int] = field(default_factory=set)


class FrameGenerator:
    """将 Algo3 输出的 dict[int, list[TouchEvent]] 转换为排序的 VerificationFrame 序列。"""

    def __init__(self, events_map: dict[int, list[TouchEvent]]):
        self.events_map = events_map
        self.frames: list[VerificationFrame] = []
        self._build()

    def _build(self):
        if not self.events_map:
            return
        for ts in sorted(self.events_map.keys()):
            evts = self.events_map[ts]
            self.frames.append(VerificationFrame(timestamp_ms=ts, events=evts))

    def __iter__(self):
        return iter(self.frames)

    def __len__(self) -> int:
        return len(self.frames)


# ============================================================================
# 3. PositionCalculator — 计算实际触点位置
# ============================================================================

class PositionCalculator:
    """追踪每个指针的按压状态，计算每个 TouchEvent 的实际物理位置。

    核心逻辑：
      - DOWN 记录按压位置和 pressed_at
      - MOVE 更新当前位置
      - UP 清除状态
      - 对于连续 MOVE 序列，直接取事件中的 pos（Algo3 已计算好）
    """

    def __init__(self):
        # 当前按下状态的指针: pointer_id → {pos, pressed_at, note_type, note_id}
        self.pressing: dict[int, dict] = {}
        # 每个事件的计算结果
        self.results: dict[int, list[dict]] = {}

    def process_frame(self, frame: VerificationFrame):
        for evt in frame.events:
            pid = evt.pointer
            action = evt.action
            pos = evt.pos

            if action == TouchAction.DOWN:
                self.pressing[pid] = {
                    'pos': pos,
                    'pressed_at': frame.timestamp_ms,
                    'note_type': None,  # 由 TaskMapper 补充
                    'note_id': None,
                }
                self.results.setdefault(frame.timestamp_ms, []).append({
                    'event': evt, 'actual_pos': pos, 'state': 'down'
                })

            elif action == TouchAction.MOVE:
                if pid in self.pressing:
                    self.pressing[pid]['pos'] = pos
                self.results.setdefault(frame.timestamp_ms, []).append({
                    'event': evt, 'actual_pos': pos, 'state': 'move'
                })

            elif action == TouchAction.UP:
                if pid in self.pressing:
                    del self.pressing[pid]
                self.results.setdefault(frame.timestamp_ms, []).append({
                    'event': evt, 'actual_pos': pos, 'state': 'up'
                })

    def process_all(self, frames: Sequence[VerificationFrame]):
        for frame in frames:
            self.process_frame(frame)


# ============================================================================
# 4. SpatialGraph — 网格化空间索引
# ============================================================================

class SpatialGraph:
    """二维网格空间索引，用于加速时空查询。

    使用固定分辨率网格（默认 16×16 px），避免逐像素对象。
    每个单元格存储 (time_bucket, event_id) 集合。
    """

    def __init__(self, cell_size: float = 16.0):
        self.cell_size = cell_size
        self.cols = math.ceil(SCREEN_W / cell_size)
        self.rows = math.ceil(SCREEN_H / cell_size)
        # grid[x_cell][y_cell] = set of event keys (time_ms, event_index)
        self.grid: dict[int, dict[int, set]] = defaultdict(lambda: defaultdict(set))

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        cx = min(int(x / self.cell_size), self.cols - 1)
        cy = min(int(y / self.cell_size), self.rows - 1)
        return max(0, cx), max(0, cy)

    def insert(self, time_ms: int, event_idx: int, x: float, y: float):
        cx, cy = self._cell(x, y)
        self.grid[cx][cy].add((time_ms, event_idx))

    def query_region(self, x_min: float, y_min: float, x_max: float, y_max: float,
                     time_ms: Optional[int] = None) -> set[tuple[int, int]]:
        """查询矩形区域内的事件。可选的时间过滤。"""
        cx_min = max(0, int(x_min / self.cell_size))
        cy_min = max(0, int(y_min / self.cell_size))
        cx_max = min(self.cols - 1, int(x_max / self.cell_size))
        cy_max = min(self.rows - 1, int(y_max / self.cell_size))

        result = set()
        for cx in range(cx_min, cx_max + 1):
            for cy in range(cy_min, cy_max + 1):
                for item in self.grid.get(cx, {}).get(cy, set()):
                    if time_ms is None or item[0] == time_ms:
                        result.add(item)
        return result

    def query_neighbors(self, x: float, y: float, radius: float,
                        time_ms: Optional[int] = None) -> set[tuple[int, int]]:
        """查询以 (x,y) 为中心、radius 半径内的事件。"""
        r_cells = math.ceil(radius / self.cell_size)
        cx, cy = self._cell(x, y)
        result = set()
        for dx in range(-r_cells, r_cells + 1):
            for dy in range(-r_cells, r_cells + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.cols and 0 <= ny < self.rows:
                    for item in self.grid.get(nx, {}).get(ny, set()):
                        if time_ms is None or item[0] == time_ms:
                            result.add(item)
        return result


# ============================================================================
# 5. NFMapper — 噪域时间覆盖映射
# ============================================================================

class NFMapper:
    """预计算并暴露噪域覆盖查询接口。复用 BlockAreas.blocked() 但提供更高效的批量查询。"""

    def __init__(self, areas: Optional[BlockAreas]):
        self.areas = areas or BlockAreas([])

    def is_covered(self, t_seconds: float, x: float, y: float, margin: Optional[float] = None) -> bool:
        """(x, y) 在 t 时刻是否被噪域覆盖（含边距）"""
        if self.areas is None:
            return False
        if margin is None:
            margin = margin_at(t_seconds)
        return self.areas.blocked(x, y, t_seconds, margin)

    def get_coverage_summary(self, t_seconds: float) -> dict:
        """返回 t 时刻的噪域覆盖统计（用于报告）"""
        if not self.areas or not self.areas.add:
            return {'covered': False, 'block_count': 0}

        # 采样屏幕关键点检查覆盖
        sample_points = [
            (SCREEN_W / 2, SCREEN_H / 2),  # 中心
            (0, 0), (SCREEN_W, 0),          # 左上右上
            (0, SCREEN_H), (SCREEN_W, SCREEN_H),  # 左下右下
        ]
        covered_count = 0
        for sx, sy in sample_points:
            if self.areas.blocked(sx, sy, t_seconds, 0):
                covered_count += 1

        return {
            'covered': covered_count > 0,
            'block_count': sum(len(v) for v in self.areas.add.values()),
            'sample_coverage': covered_count / len(sample_points),
        }


# ============================================================================
# 6. TaskMapper — 将 Algo3 TouchEvent 映射为验证任务
# ============================================================================

class TaskType(Enum):
    TAP_PRESS = 'tap_press'         # TAP 按下点验证
    FLICK_PRESS = 'flick_press'     # FLICK 按下点验证
    FLICK_TRAJECTORY = 'flick_traj' # FLICK 滑动轨迹验证
    HOLD_MOVE = 'hold_move'         # HOLD 延续 MOVE（已知约束，仅报告）
    DRAG_MOVE = 'drag_move'         # DRAG MOVE（严格跟随）
    RELEASE = 'release'             # 释放事件（无需验证）


@dataclass
class VerificationTask:
    """单个验证任务。"""
    task_type: TaskType
    timestamp_ms: int
    pointer_id: int
    note_type: int          # Note.TAP/DRAG/FLICK/HOLD
    note_id: int
    position: tuple[float, float]
    angle: float
    line: Optional[tuple[tuple[float, float], tuple[float, float]]]
    reason: str = ''        # 违规原因（验证后填充）


class TaskMapper:
    """从 Algo3 事件流中提取验证任务，关联音符类型和 judge line 信息。

    由于 TouchEvent 本身不包含 note_type/angle/line 信息，
    需要结合 PositionCalculator 的状态和原始图表数据来补充。
    """

    def __init__(self, chart: Chart, pos_calc: PositionCalculator):
        self.chart = chart
        self.pos_calc = pos_calc
        self.tasks: list[VerificationTask] = []
        self._build_tasks()

    def _build_tasks(self):
        """遍历所有事件，构建验证任务列表。"""
        # 重建指针 → 音符类型的映射
        # Algo3 中：TAP 来自 _tap(), FLICK 来自 _flick(), DRAG/HOLD 来自 _drag()
        # 通过位置匹配推断音符类型
        pointer_note_map: dict[int, dict] = {}  # pid → {note_type, note_id, angle, line}

        for frame_ts in sorted(self.pos_calc.results.keys()):
            for result in self.pos_calc.results[frame_ts]:
                evt = result['event']
                pid = evt.pointer
                action = evt.action
                pos = result['actual_pos']

                if action == TouchAction.DOWN:
                    # 推断音符类型：检查该位置属于哪种音符
                    info = self._identify_note_at(frame_ts, pos)
                    pointer_note_map[pid] = info

                elif action == TouchAction.MOVE:
                    info = pointer_note_map.get(pid, {})
                    note_type = info.get('note_type')
                    if note_type is None:
                        continue

                    # 确定任务类型
                    if note_type == Note.FLICK:
                        task_type = TaskType.FLICK_TRAJECTORY
                    elif note_type in (Note.HOLD, Note.DRAG):
                        task_type = TaskType.HOLD_MOVE
                    else:
                        task_type = TaskType.DRAG_MOVE

                    self.tasks.append(VerificationTask(
                        task_type=task_type,
                        timestamp_ms=frame_ts,
                        pointer_id=pid,
                        note_type=note_type,
                        note_id=info.get('note_id', -1),
                        position=pos,
                        angle=info.get('angle', 0.0),
                        line=info.get('line'),
                    ))

        # 补充 TAP/FLICK 按下点任务
        for frame_ts in sorted(self.pos_calc.results.keys()):
            for result in self.pos_calc.results[frame_ts]:
                evt = result['event']
                pid = evt.pointer
                action = evt.action
                pos = result['actual_pos']

                if action == TouchAction.DOWN:
                    info = pointer_note_map.get(pid, {})
                    note_type = info.get('note_type')
                    if note_type is None:
                        continue

                    if note_type == Note.TAP:
                        self.tasks.append(VerificationTask(
                            task_type=TaskType.TAP_PRESS,
                            timestamp_ms=frame_ts,
                            pointer_id=pid,
                            note_type=Note.TAP,
                            note_id=info.get('note_id', -1),
                            position=pos,
                            angle=info.get('angle', 0.0),
                            line=info.get('line'),
                        ))
                    elif note_type == Note.FLICK:
                        self.tasks.append(VerificationTask(
                            task_type=TaskType.FLICK_PRESS,
                            timestamp_ms=frame_ts,
                            pointer_id=pid,
                            note_type=Note.FLICK,
                            note_id=info.get('note_id', -1),
                            position=pos,
                            angle=info.get('angle', 0.0),
                            line=info.get('line'),
                        ))

    def _identify_note_at(self, timestamp_ms: int, pos: tuple[float, float]) -> dict:
        """根据时间和位置推断音符类型。

        简化策略：查找谱面中在该时间点附近的音符，匹配位置最近的。
        更精确的方案需要传入 Algo3 的 skipped 信息和帧结构。
        """
        best_match = None
        best_dist = float('inf')

        for line in self.chart.judge_lines:
            for note in line.notes_above + line.notes_below:
                ms = round(line.seconds(note.time) * 1000)
                if abs(ms - timestamp_ms) > 500:  # 500ms 窗口
                    continue

                off_x = note.x * 72
                x, y = line.pos(note.time)
                alpha = -line.angle(note.time) * math.pi / 180
                note_pos = (
                    x + off_x * math.cos(alpha),
                    y + off_x * math.sin(alpha)
                )

                dist = (pos[0] - note_pos[0]) ** 2 + (pos[1] - note_pos[1]) ** 2
                if dist < best_dist:
                    best_dist = dist
                    ends = judge_line_ends(line.pos(note.time), line.angle(note.time))
                    best_match = {
                        'note_type': note.typ,
                        'note_id': -1,  # 需从 chart 重新计数
                        'angle': alpha,
                        'line': ends,
                    }

        if best_match and best_dist < 10000:  # 100px 阈值
            return best_match
        return {}


# ============================================================================
# 7. SpatialVerifier — 核心验证引擎
# ============================================================================

class ViolationType(Enum):
    PRESS_IN_NF = 'press_in_nf'              # TAP/FLICK 按下点在噪域内
    PRESS_TOO_CLOSE_TO_LINE = 'press_too_close_to_line'  # 按下点离判定线太近
    TRAJECTORY_IN_NF = 'trajectory_in_nf'    # FLICK 轨迹穿过噪域
    HOLD_MOVE_IN_NF = 'hold_move_in_nf'      # HOLD MOVE 在噪域内（已知约束）
    RELEASE_TOO_EARLY = 'release_too_early'  # 释放早于 MIN_PRESS_MS


@dataclass
class Violation:
    """单个违规记录。"""
    violation_type: ViolationType
    task_type: TaskType
    timestamp_ms: int
    pointer_id: int
    note_type: int
    note_id: int
    position: tuple[float, float]
    reason: str
    severity: str = 'error'  # 'error' | 'warning' | 'info'


@dataclass
class VerificationReport:
    """完整验证报告。"""
    nf_detected: bool
    nf_result: NFDetectionResult
    total_tasks: int = 0
    total_violations: int = 0
    violations_by_type: dict[str, int] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)
    tasks_by_type: dict[str, int] = field(default_factory=dict)
    nf_coverage_timeline: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    # 【P0】重规划后仍无法解决的违规数量
    unresolved_violations: int = 0

    def add_violation(self, v: Violation):
        self.violations.append(v)
        self.total_violations += 1
        key = v.violation_type.value
        self.violations_by_type[key] = self.violations_by_type.get(key, 0) + 1

    def summary(self) -> str:
        lines = [
            f'=== NF-aware Verification Report ===',
            f'NF Detected: {self.nf_detected} ({self.nf_result.value})',
            f'Total Tasks: {self.total_tasks}',
            f'Total Violations: {self.total_violations}',
        ]
        if self.unresolved_violations > 0:
            lines.append(f'Unresolved Violations: {self.unresolved_violations}')
        if self.violations_by_type:
            lines.append('Violations by Type:')
            for k, c in sorted(self.violations_by_type.items()):
                lines.append(f'  {k}: {c}')
        if self.recommendations:
            lines.append('Recommendations:')
            for r in self.recommendations:
                lines.append(f'  - {r}')
        return '\n'.join(lines)


class SpatialVerifier:
    """核心验证引擎。遍历所有验证任务，逐个检查噪域约束。

    验证规则：
      1. TAP_PRESS / FLICK_PRESS: 按下点必须在噪域外，且到判定线的垂直距离 >= MIN_DIST
      2. FLICK_TRAJECTORY: 滑动轨迹的每个采样点必须在噪域外
      3. HOLD_MOVE / DRAG_MOVE: 仅报告（已知约束，不做噪声避让）
      4. 所有事件不得在判定线上按下
    """

    def __init__(self, nf_detector: NFDetector, nf_mapper: NFMapper,
                 spatial_graph: SpatialGraph):
        self.nf_detector = nf_detector
        self.nf_mapper = nf_mapper
        self.spatial_graph = spatial_graph
        self.report = VerificationReport(
            nf_detected=nf_detector.exists,
            nf_result=nf_detector.result,
        )

    def verify_task(self, task: VerificationTask) -> Optional[list[Violation]]:
        """验证单个任务，返回违规列表（空表示通过）。

        注意：坐标边界检查始终执行；NF 相关检查仅在 NF 存在时执行。
        """
        violations = []
        x, y = task.position
        t_sec = task.timestamp_ms / 1000.0

        if task.task_type in (TaskType.TAP_PRESS, TaskType.FLICK_PRESS):
            violations.extend(self._verify_press(task))
        elif task.task_type == TaskType.FLICK_TRAJECTORY:
            violations.extend(self._verify_flick_trajectory(task))
        elif task.task_type in (TaskType.HOLD_MOVE, TaskType.DRAG_MOVE):
            violations.extend(self._verify_hold_move(task))

        # 即使无 NF，也返回空列表而非 None，保证调用方可以安全迭代
        return violations if violations else []

    def _verify_press(self, task: VerificationTask) -> list[Violation]:
        """验证按下点：噪域外 + 判定线距离约束。"""
        violations = []
        x, y = task.position
        t_sec = task.timestamp_ms / 1000.0

        # 检查是否在噪域内
        if self.nf_mapper.is_covered(t_sec, x, y):
            violations.append(Violation(
                violation_type=ViolationType.PRESS_IN_NF,
                task_type=task.task_type,
                timestamp_ms=task.timestamp_ms,
                pointer_id=task.pointer_id,
                note_type=task.note_type,
                note_id=task.note_id,
                position=(x, y),
                reason=f'按下点 ({x:.1f}, {y:.1f}) 位于噪域内 (t={task.timestamp_ms}ms)',
                severity='error',
            ))

        # 检查到判定线的垂直距离
        if task.line is not None:
            try:
                dist = point_line_distance((x, y), task.line)
                if dist < MIN_DIST:
                    violations.append(Violation(
                        violation_type=ViolationType.PRESS_TOO_CLOSE_TO_LINE,
                        task_type=task.task_type,
                        timestamp_ms=task.timestamp_ms,
                        pointer_id=task.pointer_id,
                        note_type=task.note_type,
                        note_id=task.note_id,
                        position=(x, y),
                        reason=f'按下点 ({x:.1f}, {y:.1f}) 距判定线仅 {dist:.1f}px (< {MIN_DIST}px) (t={task.timestamp_ms}ms)',
                        severity='error',
                    ))
            except ValueError:
                pass

        return violations

    def _verify_flick_trajectory(self, task: VerificationTask) -> list[Violation]:
        """验证 FLICK 滑动轨迹：每个采样点必须在噪域外。"""
        violations = []
        t_sec = task.timestamp_ms / 1000.0

        # FLICK 轨迹参数（与 algo3 一致）
        duration_ms = flick_end - flick_start
        dx = math.sin(task.angle) * flick_scale_factor
        dy = math.cos(task.angle) * flick_scale_factor

        # 采样轨迹点
        for t_ms in range(task.timestamp_ms, task.timestamp_ms + duration_ms + 1, flick_step):
            k = (t_ms - task.timestamp_ms) / duration_ms
            px = task.position[0] + dx * k
            py = task.position[1] + dy * k

            if not (0 <= px <= SCREEN_W and 0 <= py <= SCREEN_H):
                violations.append(Violation(
                    violation_type=ViolationType.TRAJECTORY_IN_NF,
                    task_type=task.task_type,
                    timestamp_ms=t_ms,
                    pointer_id=task.pointer_id,
                    note_type=task.note_type,
                    note_id=task.note_id,
                    position=(px, py),
                    reason=f'FLICK 轨迹超出屏幕边界 ({px:.1f}, {py:.1f}) (t={t_ms}ms)',
                    severity='error',
                ))
            elif self.nf_mapper.is_covered(t_ms / 1000.0, px, py):
                violations.append(Violation(
                    violation_type=ViolationType.TRAJECTORY_IN_NF,
                    task_type=task.task_type,
                    timestamp_ms=t_ms,
                    pointer_id=task.pointer_id,
                    note_type=task.note_type,
                    note_id=task.note_id,
                    position=(px, py),
                    reason=f'FLICK 轨迹点 ({px:.1f}, {py:.1f}) 位于噪域内 (t={t_ms}ms)',
                    severity='error',
                ))

        return violations

    def _verify_hold_move(self, task: VerificationTask) -> list[Violation]:
        """验证 HOLD MOVE：仅报告，不视为错误（已知约束）。

        【P1】区分实际空间违规与轨迹约束：
          - HOLD MOVE 严格跟随判定线，无法避让噪域
          - 因此 severity 为 'info' 而非 'warning'/'error'
          - 由调用方决定如何处理此类信息
        """
        violations = []
        x, y = task.position
        t_sec = task.timestamp_ms / 1000.0

        if self.nf_mapper.is_covered(t_sec, x, y):
            violations.append(Violation(
                violation_type=ViolationType.HOLD_MOVE_IN_NF,
                task_type=task.task_type,
                timestamp_ms=task.timestamp_ms,
                pointer_id=task.pointer_id,
                note_type=task.note_type,
                note_id=task.note_id,
                position=(x, y),
                reason=f'HOLD MOVE ({x:.1f}, {y:.1f}) 位于噪域内（严格跟随判定线，无法避让）(t={task.timestamp_ms}ms)',
                severity='info',  # 【P1】从 'warning' 改为 'info'，表示这是已知约束而非可修复问题
            ))

        return violations

    def verify_all(self, tasks: Sequence[VerificationTask]) -> VerificationReport:
        """验证所有任务，生成完整报告。"""
        self.report.total_tasks = len(tasks)

        # 统计任务类型分布
        for task in tasks:
            key = task.task_type.value
            self.report.tasks_by_type[key] = self.report.tasks_by_type.get(key, 0) + 1

        # 逐个验证
        for task in tasks:
            viols = self.verify_task(task)
            if viols:
                self.report.violations.extend(viols)

        # 更新违规总数（在生成建议之前）
        self.report.total_violations = len(self.report.violations)

        # 生成建议
        self._generate_recommendations()

        return self.report

    def _generate_recommendations(self):
        """根据违规情况生成修复建议。"""
        recs = []
        vb = self.report.violations_by_type

        if vb.get('press_in_nf', 0) > 0:
            recs.append('TAP/FLICK 按下点落入噪域：建议在 search_point 中扩大迁移范围或调整角度搜索方向')

        if vb.get('press_too_close_to_line', 0) > 0:
            recs.append(f'部分按下点距判定线过近：确认 MIN_DIST={MIN_DIST}px 约束是否正确应用')

        if vb.get('trajectory_in_nf', 0) > 0:
            recs.append('FLICK 轨迹穿过噪域：建议实现 find_clear_flick 的全局轨迹搜索兜底')

        if vb.get('hold_move_in_nf', 0) > 0:
            count = vb['hold_move_in_nf']
            recs.append(f'HOLD MOVE 噪域冲突 {count} 次：这是已知约束（严格跟随判定线），建议作为已知风险单独统计')

        if not recs:
            recs.append('未发现噪域相关违规，规划符合约束')

        self.report.recommendations = recs


# ============================================================================
# 8. PathReplanner — 可修复违规的重规划尝试
# ============================================================================

class PathReplanner:
    """对 SpatialVerifier 报告的违规尝试自动修复。

    约束：
      - 不能改变命中时机（timestamp 不可变）
      - 不能破坏 Drag 轨迹要求（HOLD 必须严格跟随）
      - 不能创建不可能的多指针状态
      - 使用已有的 search_point / find_clear_flick 逻辑
      - 重规划后必须重新验证新位置不在 NF 内（闭环验证）
      - 最大重试次数 MAX_REPLAN_ATTEMPTS，防止无限循环

    返回 (original_tasks, replanned_tasks) 差异列表。
    """

    def __init__(self, chart: Chart, block_areas: BlockAreas):
        self.chart = chart
        self.block_areas = block_areas
        self.nf_mapper = NFMapper(block_areas)  # 用于重规划后的 NF 检查

    def attempt_fix(self, task: VerificationTask, violation: Violation) -> Optional[VerificationTask]:
        """尝试修复单个违规任务。成功返回新任务，失败返回 None。"""
        # HOLD/DRAG 不能移动（严格跟随约束）
        if task.task_type in (TaskType.HOLD_MOVE, TaskType.DRAG_MOVE):
            return None

        if task.task_type == TaskType.TAP_PRESS:
            return self._replan_tap(task, violation)
        elif task.task_type == TaskType.FLICK_PRESS:
            return self._replan_flick(task, violation)

        return None

    def _replan_tap(self, task: VerificationTask, violation: Violation) -> Optional[VerificationTask]:
        """为 TAP 按下点寻找替代位置。重规划后必须重新验证新位置不在 NF 内。"""
        # 复用 block_area.search_point 逻辑
        nx_dir = -math.sin(task.angle)
        ny_dir = math.cos(task.angle)

        found, fail = self.block_areas.search_point(
            task.position,
            task.timestamp_ms / 1000.0,
            nx_dir, ny_dir,
            task.line,
            MIN_DIST,
            MAX_RELOCATION_DISTANCE,
            duration=release_ms,
        )

        if found is not None:
            # 【闭环验证】检查新位置是否仍在 NF 内
            t_sec = task.timestamp_ms / 1000.0
            if self.nf_mapper.is_covered(t_sec, *found):
                return None  # 新位置仍在 NF 内，拒绝
            # 同时检查到判定线的距离约束
            if task.line is not None:
                try:
                    if point_line_distance(found, task.line) < MIN_DIST:
                        return None
                except ValueError:
                    pass

            new_task = VerificationTask(
                task_type=task.task_type,
                timestamp_ms=task.timestamp_ms,
                pointer_id=task.pointer_id,
                note_type=task.note_type,
                note_id=task.note_id,
                position=found,
                angle=task.angle,
                line=task.line,
                reason=f'replanned from ({task.position[0]:.1f},{task.position[1]:.1f}) to {found}',
            )
            return new_task

        return None  # 无解

    def _replan_flick(self, task: VerificationTask, violation: Violation) -> Optional[VerificationTask]:
        """为 FLICK 寻找替代起点和方向。"""
        # 复用 find_clear_flick 逻辑
        alpha = task.angle
        dx = math.sin(alpha) * flick_scale_factor
        dy = math.cos(alpha) * flick_scale_factor
        duration = flick_end - flick_start

        def try_directions(x0: float, y0: float):
            for sign in (1, -1):
                path_ok = True
                for t in range(task.timestamp_ms, task.timestamp_ms + duration + 1, flick_step):
                    k = (t - task.timestamp_ms) / duration
                    px, py = x0 + sign * dx * k, y0 + sign * dy * k
                    if not (0 <= px <= SCREEN_W and 0 <= py <= SCREEN_H):
                        path_ok = False
                        break
                    if self.block_areas.blocked(px, py, t / 1000.0, margin_at(t / 1000.0)):
                        path_ok = False
                        break
                    if task.line is not None:
                        try:
                            if point_line_distance((px, py), task.line) < MIN_DIST:
                                path_ok = False
                                break
                        except ValueError:
                            path_ok = False
                            break
                if path_ok:
                    return (x0, y0, sign * dx, sign * dy)
            return None

        # 先尝试原始位置
        result = try_directions(*task.position)
        if result is not None:
            return VerificationTask(
                task_type=task.task_type,
                timestamp_ms=task.timestamp_ms,
                pointer_id=task.pointer_id,
                note_type=task.note_type,
                note_id=task.note_id,
                position=task.position,
                angle=task.angle,
                line=task.line,
                reason=f'replanned direction to {result[2]:.1f},{result[3]:.1f}',
            )

        # 在迁移范围内搜索
        for x0, y0 in nearby_points(*task.position, max_radius=MAX_RELOCATION_DISTANCE):
            result = try_directions(x0, y0)
            if result is not None:
                return VerificationTask(
                    task_type=task.task_type,
                    timestamp_ms=task.timestamp_ms,
                    pointer_id=task.pointer_id,
                    note_type=task.note_type,
                    note_id=task.note_id,
                    position=(x0, y0),
                    angle=task.angle,
                    line=task.line,
                    reason=f'replanned origin to ({x0:.1f},{y0:.1f})',
                )

        return None  # 无解

    def replan_violations(self, tasks: Sequence[VerificationTask],
                          violations: Sequence[Violation]) -> dict[int, VerificationTask]:
        """批量尝试修复违规，返回 {violation_index: new_task} 映射。

        带最大重试次数限制（MAX_REPLAN_ATTEMPTS），防止无限循环。
        超过限制后，未解决的违规将保留在原始报告中。
        """
        replanned = {}
        unresolved_count = 0

        for i, viol in enumerate(violations):
            # 找到对应的原始任务
            matched_task = None
            for task in tasks:
                if (task.timestamp_ms == viol.timestamp_ms and
                    task.pointer_id == viol.pointer_id and
                    task.note_id == viol.note_id):
                    matched_task = task
                    break

            if matched_task is None:
                continue

            # 尝试重规划（单次尝试，因为 attempt_fix 内部已包含闭环验证）
            new_task = self.attempt_fix(matched_task, viol)
            if new_task is not None:
                replanned[i] = new_task
            else:
                # 无法修复：记录为未解决
                unresolved_count += 1

        return replanned


# ============================================================================
# 9. Main Entry Point — 一键验证入口
# ============================================================================

def verify_algo3_output(
    events_map: dict[int, list[TouchEvent]],
    chart: Chart,
    algo3_skipped: Optional[list] = None,
    detailed: bool = False,
    tasks: Optional[list[VerificationTask]] = None,
) -> VerificationReport:
    """Algo3 输出一键验证入口。

    Args:
        events_map: Algo3 PointerAllocator.done() 返回的 dict[int, list[TouchEvent]]
        chart: 解析后的 Chart 对象
        algo3_skipped: PointerAllocator.skipped 列表（可选，用于关联跳过原因）
        detailed: 是否启用详细模式（生成完整 spatial graph 等）
        tasks: 预构建的验证任务列表（可选）。如果提供，则跳过 TaskMapper；
               否则自动从事件流中提取任务（向后兼容）

    Returns:
        VerificationReport 验证报告

    Example:
        >>> from algo.algo3 import solve
        >>> from algo.verify_nf import verify_algo3_output
        >>> events = solve(chart)
        >>> report = verify_algo3_output(events, chart)
        >>> print(report.summary())

        # 使用预构建任务的示例：
        >>> prebuilt_tasks = [...]  # list[VerificationTask]
        >>> report = verify_algo3_output(events, chart, tasks=prebuilt_tasks)
    """
    # Step 1: NF 检测（条件触发：无 NF 则零开销跳过）
    detector = NFDetector(chart.block_areas)
    if not detector.exists:
        return VerificationReport(
            nf_detected=False,
            nf_result=NFDetectionResult.NONE,
            total_tasks=0,
            total_violations=0,
            recommendations=['谱面无噪域，验证跳过'],
        )

    # Step 2: 生成验证帧
    frame_gen = FrameGenerator(events_map)

    # Step 3: 计算实际位置
    pos_calc = PositionCalculator()
    pos_calc.process_all(frame_gen.frames)

    # Step 4: 构建空间索引（仅详细模式）
    spatial_graph = SpatialGraph(cell_size=16.0) if detailed else None
    if detailed and spatial_graph:
        for frame in frame_gen.frames:
            for result in pos_calc.results.get(frame.timestamp_ms, []):
                x, y = result['actual_pos']
                spatial_graph.insert(frame.timestamp_ms, 0, x, y)

    # Step 5: NF 映射
    nf_mapper = NFMapper(chart.block_areas)

    # Step 6: 任务映射（如果提供了预构建任务则跳过）
    if tasks is not None:
        task_list = tasks
    else:
        task_mapper = TaskMapper(chart, pos_calc)
        task_list = task_mapper.tasks

    # Step 7: 空间验证
    verifier = SpatialVerifier(detector, nf_mapper, spatial_graph or SpatialGraph())
    report = verifier.verify_all(task_list)

    # Step 8: 路径重规划（如果存在可修复违规）
    if report.total_violations > 0:
        replanner = PathReplanner(chart, chart.block_areas)
        replanned = replanner.replan_violations(task_list, report.violations)
        if replanned:
            report.recommendations.append(
                f'发现 {len(replanned)} 个可修复违规，建议应用重规划结果'
            )
        # 【P0】记录未解决的违规数量
        total_unresolved = len(report.violations) - len(replanned)
        report.unresolved_violations = total_unresolved
        if total_unresolved > 0:
            report.recommendations.append(
                f'{total_unresolved} 个违规无法通过重规划修复，建议检查谱面设计或调整算法参数'
            )

    # 关联 Algo3 skipped 信息
    if algo3_skipped:
        skip_count = len(algo3_skipped)
        report.recommendations.append(
            f'Algo3 跳过 {skip_count} 个音符（placement failure / pointer limit exceeded）'
        )

    return report


# ============================================================================
# Constants (imported from algo3 for trajectory validation)
# ============================================================================
flick_start = -50
flick_end = 50
flick_scale_factor = 100
flick_step = 5
drag_step = 8
release_ms = 300
MIN_PRESS_MS = 40
