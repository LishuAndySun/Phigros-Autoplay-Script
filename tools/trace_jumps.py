"""追踪相邻 MOVE 跳变 (>50px) 的完整调用链

对 Chart_AT.json 运行 algo2.solve，找出所有同一指针、相邻 MOVE、间隔<=20ms
且位移>50px 的事件，输出 pointer ID、时间、坐标、音符类型及上下文。
"""
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chart import Chart
from algo.algo2 import PointerAllocator, SimpleNote

CHART = 'Assets/Tracks/DesultorySignals.technoplanet.0/Chart_AT.json'


def main():
    chart = Chart.from_dict(json.load(open(CHART)))

    # ---- 拦截 _insert 拿到全部事件，并记录每个 MOVE 所属的音符信息 ----
    # events_by_pointer: pid -> [(ts, action_name, pos, note_type_or_None, note_id_or_None)]
    events_by_pointer: dict[int, list[tuple[int, str, tuple[float, float], int | None, int | None]]] = defaultdict(list)
    # 当前正在执行的音符：在 _tap/_flick/_drag 中设置
    current_note_for_pointer: dict[int, tuple[int, int]] = {}  # pid -> (note_type, note_id)

    orig_insert = PointerAllocator._insert
    orig_tap = PointerAllocator._tap
    orig_flick = PointerAllocator._flick
    orig_drag = PointerAllocator._drag

    def _insert(self, ts, ev):
        nt = current_note_for_pointer.get(ev.pointer)
        events_by_pointer[ev.pointer].append((ts, ev.action.name, tuple(ev.pos), nt[0] if nt else None, nt[1] if nt else None))
        return orig_insert(self, ts, ev)

    def _tap(self, pointer, note, blocks_):
        current_note_for_pointer[pointer.id] = (note.note_type, note.note_id)
        ok = orig_tap(self, pointer, note, blocks_)
        if not ok:
            current_note_for_pointer.pop(pointer.id, None)
        return ok

    def _flick(self, pointer, note, blocks_):
        current_note_for_pointer[pointer.id] = (note.note_type, note.note_id)
        ok = orig_flick(self, pointer, note, blocks_)
        if not ok:
            current_note_for_pointer.pop(pointer.id, None)
        return ok

    def _drag(self, pointer, note):
        current_note_for_pointer[pointer.id] = (note.note_type, note.note_id)
        return orig_drag(self, pointer, note)

    PointerAllocator._insert = _insert
    PointerAllocator._tap = _tap
    PointerAllocator._flick = _flick
    PointerAllocator._drag = _drag

    stats = []
    try:
        import algo.algo2 as a2
        a2.solve(chart, stats)
    except TypeError:
        import algo.algo2 as a2
        a2.solve(chart)
    finally:
        PointerAllocator._insert = orig_insert
        PointerAllocator._tap = orig_tap
        PointerAllocator._flick = orig_flick
        PointerAllocator._drag = orig_drag

    # ---- 分析跳变 ----
    print(f"总指针数: {len(events_by_pointer)}")
    print()

    big_jumps = []
    for pid, seq in sorted(events_by_pointer.items()):
        for i in range(len(seq) - 1):
            t0, a0, p0, nt0, nid0 = seq[i]
            t1, a1, p1, nt1, nid1 = seq[i + 1]
            dt = t1 - t0
            if dt <= 0:
                continue
            if dt > 20:
                continue
            if a0 != 'MOVE' or a1 != 'MOVE':
                continue
            dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            if dist <= 50:
                continue
            big_jumps.append((pid, t0, t1, p0, p1, dt, dist, nt0, nid0, nt1, nid1, seq[i-1] if i > 0 else None, seq[i+2] if i+2 < len(seq) else None))

    print(f">50px 跳变总数: {len(big_jumps)}")
    print(f"最大跳变: {max(j[6] for j in big_jumps) if big_jumps else 0:.1f}px")
    print()

    # 按距离排序，先打印最大的
    big_jumps.sort(key=lambda j: -j[6])

    for idx, (pid, t0, t1, p0, p1, dt, dist, nt0, nid0, nt1, nid1, prev_ev, next_ev) in enumerate(big_jumps[:30]):
        print(f"--- 跳变 #{idx+1} ---")
        print(f"  Pointer: {pid}")
        print(f"  MOVE[0]: t={t0}ms ({p0[0]:.1f},{p0[1]:.1f}) type={nt0} note_id={nid0}")
        print(f"  MOVE[1]: t={t1}ms ({p1[0]:.1f},{p1[1]:.1f}) type={nt1} note_id={nid1}")
        print(f"  时间差: {dt}ms, 距离: {dist:.1f}px")
        if prev_ev:
            pt, pa, pp, pnt, pnid = prev_ev
            pdist = math.hypot(p0[0] - pp[0], p0[1] - pp[1])
            print(f"  前一个事件: t={pt}ms {pa} ({pp[0]:.1f},{pp[1]:.1f}) type={pnt} note_id={pnid} d_to_MOVE0={pdist:.1f}")
        if next_ev:
            nt, na, np, nnt, nnid = next_ev
            ndist = math.hypot(np[0] - p1[0], np[1] - p1[1])
            print(f"  后一个事件: t={nt}ms {na} ({np[0]:.1f},{np[1]:.1f}) type={nnt} note_id={nnid} d_from_MOVE1={ndist:.1f}")
        
        # 判断场景
        reasons = []
        if nt0 is None or nt1 is None:
            reasons.append("未知音符类型（可能是系统事件）")
        elif nt0 != nt1:
            reasons.append(f"跨音符类型切换: {nt0}→{nt1}")
        elif nid0 == nid1:
            reasons.append("同一音符的连续 MOVE（正常轨迹）")
        else:
            reasons.append(f"不同音符但同类型: {nid0}→{nid1}")
        print(f"  可能原因: {'; '.join(reasons)}")
        print()

    # 统计分类
    cross_type = sum(1 for j in big_jumps if j[7] is not None and j[9] is not None and j[7] != j[9])
    same_type_diff_note = sum(1 for j in big_jumps if j[7] is not None and j[9] is not None and j[7] == j[9] and j[8] != j[10])
    unknown_type = sum(1 for j in big_jumps if j[7] is None or j[9] is None)
    same_note = sum(1 for j in big_jumps if j[8] == j[10] and j[8] is not None)
    
    print("=== 跳变分类统计 ===")
    print(f"  跨音符类型: {cross_type}")
    print(f"  同类型不同音符: {same_type_diff_note}")
    print(f"  未知音符类型: {unknown_type}")
    print(f"  同一音符: {same_note}")
    print(f"  其他: {len(big_jumps) - cross_type - same_type_diff_note - unknown_type - same_note}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
