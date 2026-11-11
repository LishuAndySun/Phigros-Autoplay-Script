"""噪域(blockAreaList)的时变矩形判定与触点避让"""
import math
from enum import Enum
from typing import Optional, Sequence

SCREEN_W = 1280
SCREEN_H = 720
BUCKET = 0.5  # 时间索引的分桶宽度(秒)
MAX_TIME = 3600.0  # 索引时间上限(秒)，避免 disableTime=1e9 之类的值撑爆索引
STEP = 4  # 避让时沿判定线法向搜索的步长(像素)
MAX_STEPS = math.ceil(math.hypot(SCREEN_W, SCREEN_H) / STEP)
MAX_RADIUS = math.hypot(SCREEN_W, SCREEN_H)
MARGIN = 30  # 避让用的安全边距(像素)，向噪域外侧额外扩张
USE_SUBTRACT = False  # 游戏中挖空块不生效，设为 True 才启用挖空

# 判定线半宽：判定线以 line.pos() 为中心、沿角度方向向两侧各延伸 SCREEN_W/2
JUDGE_LINE_HALF_WIDTH = SCREEN_W / 2
MIN_DIST = 80.0  # 触点到判定线的垂直距离下限(像素)
MAX_RELOCATION_DISTANCE = 200.0  # 触点相对原始目标的迁移距离上限(像素)，不允许无限远兜底


class PlacementFailure(Enum):
    """触点无解的原因，各类原因严格区分、不合并"""
    NO_VALID_POSITION = 'NO_VALID_POSITION'  # 全屏不存在满足噪域与判定线约束的点
    RELOCATION_LIMIT_EXCEEDED = 'RELOCATION_LIMIT_EXCEEDED'  # 存在合法点，但全都超出最大迁移距离
    INVALID_GEOMETRY = 'INVALID_GEOMETRY'  # 几何数据非法（判定线退化、坐标非有限等）


def margin_at(t: float) -> float:
    """t 时刻的噪域安全边距。

    本次保留 MARGIN 的既有实际行为，仅封装为时间接口，暂不引入速度预测。
    后续若需要随噪域运动放大余量，只改本函数即可。
    """
    return MARGIN


def judge_line_ends(center: tuple[float, float], angle_deg: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """由判定线中心与角度(度)求两个端点，坐标系与 line.pos() 一致(y 向下)"""
    a = -angle_deg * math.pi / 180
    cx, cy = center
    dx, dy = math.cos(a) * JUDGE_LINE_HALF_WIDTH, math.sin(a) * JUDGE_LINE_HALF_WIDTH
    return (cx + dx, cy + dy), (cx - dx, cy - dy)


def point_line_distance(p: tuple[float, float], line: tuple[tuple[float, float], tuple[float, float]]) -> float:
    """点到无限延长直线的垂直距离 d(P,L) = |Ax + By + C| / sqrt(A²+B²)

    (x1,y1)、(x2,y2) 为判定线两端点：
        A = y2 - y1, B = x1 - x2, C = x2*y1 - x1*y2
    判定线退化(两端点重合)时抛出 ValueError，由调用方转换为 INVALID_GEOMETRY。
    """
    (x1, y1), (x2, y2) = line
    a = y2 - y1
    b = x1 - x2
    c = x2 * y1 - x1 * y2
    norm = math.hypot(a, b)
    if norm < 1e-9:
        raise ValueError('判定线退化：两端点重合，无法定义垂直距离')
    x, y = p
    return abs(a * x + b * y + c) / norm


def nearby_points(x: float, y: float, max_radius: float = MAX_RADIUS, step: float = STEP):
    """以 (x, y) 为中心由近及远输出屏幕内的候选点，首个为自身，半径不超过 max_radius"""
    yield x, y
    r = step
    limit = min(max_radius, MAX_RADIUS)
    while r <= limit:
        n = max(8, math.ceil(2 * math.pi * r / step))
        for i in range(n):
            a = 2 * math.pi * i / n
            px, py = x + r * math.cos(a), y + r * math.sin(a)
            if 0 <= px <= SCREEN_W and 0 <= py <= SCREEN_H:
                yield px, py
        r += step


def _interp(events: list[tuple[float, tuple[float, ...]]], t: float,
            default: tuple[float, ...]) -> tuple[float, ...]:
    """分段线性插值，事件需按时间排序"""
    if not events or t < events[0][0]:
        return default
    prev_t, prev_v = events[0]
    for ev_t, ev_v in events[1:]:
        if t < ev_t:
            k = (t - prev_t) / (ev_t - prev_t)
            return tuple(a + (b - a) * k for a, b in zip(prev_v, ev_v))
        prev_t, prev_v = ev_t, ev_v
    return prev_v


class BlockArea:
    def __init__(self, d: dict):
        self.enable = d['enableTime']
        self.disable = d['disableTime']
        tr, bl = d['topRightPercentage'], d['bottomLeftPercentage']
        # 以下坐标均为物理坐标系(y向上)，单位为像素
        self.half_w = (tr['x'] - bl['x']) * SCREEN_W / 2
        self.half_h = (tr['y'] - bl['y']) * SCREEN_H / 2
        self.base_center = ((tr['x'] + bl['x']) * SCREEN_W / 2, (tr['y'] + bl['y']) * SCREEN_H / 2)
        self.moves = sorted((e['time'], (e['endPosition']['x'] * SCREEN_W - self.base_center[0],
                         e['endPosition']['y'] * SCREEN_H - self.base_center[1]))
                    for e in d.get('moveEvents', []))
        self.rotations = sorted((e['time'], (e['anchor']['x'] * SCREEN_W, e['anchor']['y'] * SCREEN_H,
                                            e['rotation'])) for e in d.get('rotateEvents', []))
        self.scales = sorted((e['time'], (e['anchor']['x'] * SCREEN_W, e['anchor']['y'] * SCREEN_H,
                                          e['scale']['x'], e['scale']['y']))
                             for e in d.get('scaleEvents', []))

    def contains(self, x: float, y: float, t: float, margin: float = 0.0) -> bool:
        px, py = x, SCREEN_H - y
        mx, my = _interp(self.moves, t, (0.0, 0.0))
        px, py = px - mx, py - my
        rx, ry, rotation = _interp(self.rotations, t, (*self.base_center, 0.0))
        theta = math.radians(rotation)
        dx, dy = px - rx, py - ry
        c, s = math.cos(theta), math.sin(theta)
        px, py = rx + dx * c + dy * s, ry - dx * s + dy * c
        sx_anchor, sy_anchor, sx, sy = _interp(self.scales, t, (*self.base_center, 1.0, 1.0))
        if abs(sx) < 1e-9 or abs(sy) < 1e-9:
            return False
        px = sx_anchor + (px - sx_anchor) / sx
        py = sy_anchor + (py - sy_anchor) / sy
        lx, ly = px - self.base_center[0], py - self.base_center[1]
        return abs(lx) <= self.half_w + margin and abs(ly) <= self.half_h + margin


class BlockAreas:
    def __init__(self, items: Sequence[dict]):
        self.add: dict[int, list[BlockArea]] = {}
        self.sub: dict[int, list[BlockArea]] = {}
        for d in items:
            block = BlockArea(d)
            if block.enable > block.disable:
                continue
            index = self.sub if d.get('isSubtract') else self.add
            start = max(0, int(block.enable // BUCKET))
            end = min(block.disable, MAX_TIME)
            for k in range(start, int(end // BUCKET) + 1):
                index.setdefault(k, []).append(block)

    @staticmethod
    def _hit(index: dict[int, list[BlockArea]], x: float, y: float, t: float, margin: float) -> bool:
        return any(b.enable <= t <= b.disable and b.contains(x, y, t, margin)
                   for b in index.get(int(t // BUCKET), ()))

    def blocked(self, x: float, y: float, t: float, margin: float = 0.0) -> bool:
        """噪域 = 普通块的并集 减去 挖空块(isSubtract)的并集"""
        if not self._hit(self.add, x, y, t, margin):
            return False
        return not (USE_SUBTRACT and self._hit(self.sub, x, y, t, margin))

    def search_point(self,
                     pos: tuple[float, float],
                     t: float,
                     nx_dir: float,
                     ny_dir: float,
                     line: Optional[tuple[tuple[float, float], tuple[float, float]]] = None,
                     min_dist: float = 0.0,
                     max_relocation: float = MAX_RELOCATION_DISTANCE,
                     duration: int = 0,
                     sample_step: int = 5,
                     ) -> tuple[Optional[tuple[float, float]], Optional[PlacementFailure]]:
        """为 t 时刻(及后续 duration ms)的静止按压/滑动起点寻找合法位置。

        合法位置需同时满足：
          1. 在 [t, t+duration] 内(含动态 margin_at)都不处于噪域；
          2. 到判定线的垂直距离 >= min_dist；
          3. 相对原始目标点 pos 的迁移距离 <= max_relocation。

        搜索顺序：先沿判定线法向 (±(nx_dir, ny_dir)) 逐 STEP 像素搜索，再退回 nearby_points
        由近及远兜底。返回 (位置, None) 或 (None, 失败原因)，绝不静默返回原始位置。
        """
        x, y = pos
        if not (math.isfinite(x) and math.isfinite(y)):
            return None, PlacementFailure.INVALID_GEOMETRY

        def ok(px: float, py: float) -> bool:
            if not (0 <= px <= SCREEN_W and 0 <= py <= SCREEN_H):
                return False
            t0 = int(round(t * 1000))
            for tt in range(t0, t0 + duration + 1, sample_step):
                if self.blocked(px, py, tt / 1000, margin_at(tt / 1000)):
                    return False
            if line is None or min_dist <= 0:
                return True
            try:
                return point_line_distance((px, py), line) >= min_dist
            except ValueError:
                return False

        # 1) 法向优先（同样受最大迁移距离约束）
        if ok(x, y):
            return (x, y), None
        max_steps = min(MAX_STEPS, int(max_relocation // STEP) + 1)
        for i in range(1, max_steps + 1):
            if i * STEP > max_relocation:
                break
            for sign in (1, -1):
                nx, ny = x + sign * i * STEP * nx_dir, y + sign * i * STEP * ny_dir
                if ok(nx, ny):
                    return (nx, ny), None

        # 2) nearby_points 有限范围兜底，由近及远
        exceeded = False
        for px, py in nearby_points(x, y, max_radius=max_relocation):
            if math.hypot(px - x, py - y) > max_relocation:
                continue
            if ok(px, py):
                return (px, py), None
        # 区分「全屏无解」与「有解但太远」：只在 max_relocation 之外继续找一次
        for px, py in nearby_points(x, y, max_radius=MAX_RADIUS):
            if math.hypot(px - x, py - y) <= max_relocation:
                continue
            if ok(px, py):
                exceeded = True
                break
        return None, PlacementFailure.RELOCATION_LIMIT_EXCEEDED if exceeded else PlacementFailure.NO_VALID_POSITION

