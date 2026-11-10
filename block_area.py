"""噪域(blockAreaList)的时变矩形判定与触点避让"""
import math
from typing import Sequence

SCREEN_W = 1280
SCREEN_H = 720
BUCKET = 0.5  # 时间索引的分桶宽度(秒)
MAX_TIME = 3600.0  # 索引时间上限(秒)，避免 disableTime=1e9 之类的值撑爆索引
STEP = 4  # 避让时沿判定线法向搜索的步长(像素)
MAX_STEPS = math.ceil(math.hypot(SCREEN_W, SCREEN_H) / STEP)
MARGIN = 30  # 避让用的安全边距(像素)，向噪域外侧额外扩张


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
        return self._hit(self.add, x, y, t, margin) and not self._hit(self.sub, x, y, t, margin)

    def free_point(self, pos: tuple[float, float], t: float, nx_dir: float, ny_dir: float) -> tuple[float, float]:
        """若 pos 位于 t 时刻的噪域内，沿法向单位向量 (nx_dir, ny_dir) 搜索；找不到时保持原位"""
        x, y = pos
        if not self.blocked(x, y, t, MARGIN):
            return pos
        for i in range(1, MAX_STEPS + 1):
            for sign in (1, -1):
                nx, ny = x + sign * i * STEP * nx_dir, y + sign * i * STEP * ny_dir
                if 0 <= nx <= SCREEN_W and 0 <= ny <= SCREEN_H and not self.blocked(nx, ny, t, MARGIN):
                    return nx, ny
        return pos
