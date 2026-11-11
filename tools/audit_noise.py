"""噪域与几何避让审计脚本

对 Chart_AT.json 运行 algo2.solve，并统计：
  1. Tap/Flick 按下时的噪域违规数量
  2. Hold MOVE 噪域违规数量
  3. Flick MOVE 噪域违规数量
  4. 判定线垂直距离违规数量
  5. 相邻 MOVE (<=20ms) 跳变 > 50px 的数量
  6. 最大实际迁移距离
  7. 各类无解数量及对应 Note ID

原始基线数据由 git stash 后的旧实现产生，审计口径保持一致，不删减任何项目。
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from block_area import MARGIN, MIN_DIST, margin_at, judge_line_ends, point_line_distance
import algo.algo2 as a2
from algo.algo2 import PointerAllocator
from chart import Chart

CHART = 'Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json'


def main():
    chart = Chart.from_dict(json.load(open(CHART)))
    blocks = chart.block_areas

    # 拦截 _insert 拿到全部事件；拦截 _down 拿到按下时刻的真实音符位置
    events: dict[int, list[tuple[int, str, tuple[float, float]]]] = defaultdict(list)
    presses: list[tuple[int, int, tuple[float, float], tuple[float, float], tuple]] = []  # ms,type,下发位置,原始位置,判定线端点
    moves: dict[int, list[tuple[int, tuple[float, float]]]] = defaultdict(list)
    flick_moves: set[tuple[int, int, tuple[float, float]]] = set()

    orig_insert = PointerAllocator._insert

    def _insert(self, ts, ev):
        events[ev.pointer].append((ts, ev.action.name, tuple(ev.pos)))
        if ev.action.name == 'MOVE':
            moves[ev.pointer].append((ts, tuple(ev.pos)))
        return orig_insert(self, ts, ev)

    orig_tap = PointerAllocator._tap
    orig_flick = PointerAllocator._flick
    orig_drag = PointerAllocator._drag

    def _tap(self, pointer, note, blocks_):
        original = tuple(note.pos)
        ok = orig_tap(self, pointer, note, blocks_)
        if ok:
            presses.append((self.now, note.note_type, tuple(note.pos), original, note.line))
        return ok

    def _flick(self, pointer, note, blocks_):
        original = tuple(note.pos)
        before = len(events.get(pointer.id, []))
        ok = orig_flick(self, pointer, note, blocks_)
        if ok:
            presses.append((self.now, note.note_type, tuple(note.pos), original, note.line))
            # 结构性标记：本次 _flick 内部插入的 MOVE 即为 flick 轨迹
            for ts, act, pos in events.get(pointer.id, [])[before:]:
                if act == 'MOVE':
                    flick_moves.add((pointer.id, ts, pos))
        return ok

    def _drag(self, pointer, note):
        presses.append((self.now, note.note_type, tuple(note.pos), tuple(note.pos), note.line))
        return orig_drag(self, pointer, note)

    PointerAllocator._insert = _insert
    PointerAllocator._tap = _tap
    PointerAllocator._flick = _flick
    PointerAllocator._drag = _drag

    stats: list = []
    try:
        a2.solve(chart, stats)
    except TypeError:
        a2.solve(chart)
    finally:
        PointerAllocator._insert = orig_insert
        PointerAllocator._tap = orig_tap
        PointerAllocator._flick = orig_flick
        PointerAllocator._drag = orig_drag

    # ---- 1/2/3 噪域违规，按结构性轨迹归属分类 ----
    press_bad = []
    move_bad_hold = []
    move_bad_flick = []
    for pid, seq in events.items():
        for ts, act, pos in seq:
            if act != 'MOVE':
                continue
            if not blocks.blocked(*pos, ts / 1000, margin_at(ts / 1000)):
                continue
            if (pid, ts, pos) in flick_moves:
                move_bad_flick.append((ts, pos))
            else:
                move_bad_hold.append((ts, pos))

    for ms, typ, placed, original, _line in presses:
        if blocks.blocked(*placed, ms / 1000, margin_at(ms / 1000)):
            press_bad.append((ms, typ, placed))

    # ---- 4 判定线垂直距离 ----
    dist_bad = []
    for ms, typ, placed, original, line in presses:
        if typ not in (1, 4) or line is None:
            continue
        try:
            d = point_line_distance(placed, line)
        except ValueError:
            continue
        if d < MIN_DIST:
            dist_bad.append((ms, typ, placed, round(d, 1)))

    # ---- 5 跳变：按指针遍历，排除指针复用造成的假跳变 ----
    # 真实跳变 = 同一指针、相邻两条 MOVE、间隔 <=20ms。DOWN 之后的第一个 MOVE 与
    # 复用指针跨音符的位移不计入（那不是同一段轨迹）。
    jumps = []
    for pid, seq in moves.items():
        for (t0, p0), (t1, p1) in zip(seq, seq[1:]):
            if 0 < t1 - t0 <= 20:
                jumps.append(math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
    big_jumps = [j for j in jumps if j > 50]

    # ---- 6 最大实际迁移距离（仅 Tap/Flick，Hold 严格跟随判定线不迁移） ----
    relocations = [math.hypot(p[0] - o[0], p[1] - o[1])
                   for _, typ, p, o, _ in presses if typ in (1, 4)]
    max_reloc = max(relocations) if relocations else 0.0

    # ---- 7 无解 ----
    reasons = Counter(s[4].name if hasattr(s[4], 'name') else str(s[4]) for s in stats)

    print('=' * 68)
    print('噪域与几何避让审计（Chart_AT.json）')
    print('=' * 68)
    print(f'总事件 {sum(len(v) for v in events.values())}，按下 {len(presses)}，'
          f'MOVE {sum(len(v) for v in moves.values())}')
    print()
    print(f'[1] Tap/Flick 按下噪域违规        : {len(press_bad)}')
    print(f'[2] Hold MOVE 噪域违规            : {len(move_bad_hold)}')
    print(f'[3] Flick MOVE 噪域违规           : {len(move_bad_flick)}')
    print(f'[4] 判定线垂直距离违规 (<{MIN_DIST:g}px) : {len(dist_bad)}')
    print(f'[5] 相邻 MOVE 跳变 >50px          : {len(big_jumps)} / {len(jumps)}'
          f'（最大 {max(jumps) if jumps else 0:.0f}px）')
    print(f'[6] 最大实际迁移距离              : {max_reloc:.1f}px')
    print(f'[7] 无解总数                      : {len(stats)}')
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f'      {k:28s}: {v}')
    if stats:
        print('      明细 (时间ms, 类型, 原始x, 原始y, 原因):')
        for ms, typ, x, y, reason in stats:
            print(f'        {ms:6d}ms type={typ} ({x:6.1f},{y:6.1f}) {reason.name if hasattr(reason, "name") else reason}')

    if press_bad:
        print()
        print(f'按下噪域违规明细 (共 {len(press_bad)})：')
        for ms, typ, pos in press_bad:
            print(f'  {ms}ms type={typ} ({pos[0]:.0f},{pos[1]:.0f})')

    if dist_bad:
        print()
        print(f'判定线垂直距离违规明细 (共 {len(dist_bad)})：')
        for ms, typ, pos, d in dist_bad:
            print(f'  {ms}ms type={typ} ({pos[0]:.0f},{pos[1]:.0f}) d={d}px')

    return 0


if __name__ == '__main__':
    sys.exit(main())
