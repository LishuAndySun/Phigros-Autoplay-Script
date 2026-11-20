# PhiAPS 噪域避让开发计划

## 一、当前稳定版本与现状

### 1.1 已推送稳定版本

- GitHub 上已有稳定版本（commit HEAD）。
- 基础点按逻辑已修复：即使没有噪域干扰，Tap/Drags/Flicks/Holds 都能正常触发。
- **本次任何修改都不能破坏这一已验证功能。**

### 1.2 已完成工作

| 模块 | 状态 |
|------|------|
| `block_area.py` — 时变噪域矩形判定 + `search_point` 几何避让 | ✅ 完成 |
| `algo/algo2.py` — TAP/FLICK 噪域外约束 + HOLD 严格跟随 | ✅ 完成 |
| 判定线垂直距离约束 (`MIN_DIST = 80`) | ✅ 完成 |
| 最大迁移距离限制 (`MAX_RELOCATION_DISTANCE = 200`) | ✅ 完成 |
| 无解原因枚举 (`PlacementFailure`) + `skipped` 记录 | ✅ 完成 |
| 审计脚本 `tools/audit_noise.py`（7 项指标） | ✅ 完成 |
| 跳变追踪脚本 `tools/trace_jumps.py` | ✅ 完成 |

### 1.3 当前参数

```python
MARGIN = 30           # 噪域安全边距 (px)
MIN_DIST = 80.0       # 触点到判定线垂直距离下限 (px)
MAX_RELOCATION_DISTANCE = 200.0  # 触点迁移上限 (px)
```

**暂不修改这些参数。**

### 1.4 审计基线数据（Chart_AT.json, 56830 帧）

| 指标 | 值 |
|------|-----|
| 总事件 | 17308 |
| 按下 | 1592 |
| MOVE | 14124 |
| [1] Tap/Flick 按下噪域违规 | 14 |
| [2] Hold MOVE 噪域违规 | 1229 |
| [3] Flick MOVE 噪域违规 | 0 |
| [4] 判定线垂直距离违规 (<80px) | 0 |
| [5] 相邻 MOVE 跳变 >50px | 48 / 13448（最大 998px） |
| [6] 最大实际迁移距离 | 200.0px |
| [7] 无解总数 | 54（35 REL + 19 NO_VAL） |

---

## 二、998px 跳变根因及证据

### 2.1 诊断结论

通过 `tools/trace_jumps.py` 完整追踪，确认：

- **所有 48 个 >50px 跳变均发生在同一 note_id 的连续 MOVE 之间。**
- **时间间隔全部为 8ms，对应 `drag_step = 8`。**
- **不是指针复用、跨音符匹配错误或 PointerAllocator bug。**

### 2.2 最大跳变示例

```
Pointer: 1000
MOVE[0]: t=92072ms (268.8,648.0) type=2 note_id=1195
MOVE[1]: t=92080ms (1267.2,648.0) type=2 note_id=1195
距离: 998.4px, 时间差: 8ms
前后事件均为同音符连续 MOVE，无指针切换。
```

### 2.3 根因定位

问题出在 `solve()` 中 HOLD 的 DRAG 位置生成：

```python
# algo/algo2.py solve()
for offset in range(1, hold_ms + 1):
    frames[ms + offset].add(Note.DRAG,
        line.pos_of(note, line.time((ms + offset) / 1000)), ...)
```

每帧 DRAG 目标直接取自 `line.pos_of()`。如果谱面中判定线在两帧之间快速移动（旋转/平移），相邻帧目标位置差距可达数百甚至近千像素。`PointerAllocator.allocate()` 步骤 3 直接将 `note.pos` 下发为 MOVE，**不做限速或插值**。

### 2.4 关键事实

- **基线和修改后最大跳变都是 998px** → 这不是噪域搜索引入的新问题，而是原有代码就存在的行为。
- HOLD 必须严格跟随判定线 → 不能为了减少跳变而擅自改变 HOLD 轨迹。
- PointerAllocator 只是忠实地将 `note.pos` 下发 → 问题在上游坐标生成。

---

## 三、HOLD 轨迹连续性检测方案

### 3.1 核心约束

**HOLD 必须严格跟随判定线，不能为了减少 MOVE 跳变而擅自改变 HOLD 轨迹。**

因此，不允许直接加入固定的每帧最大位移限制让触点落后于判定线。

### 3.2 调查步骤

#### Step 1: 判定线轨迹连续性检测

读取 `chart.py` 中 `JudgeLine.pos()`、`pos_of()`、`angle()`、`seconds()` 的实现，确认：

- `pos(t)` 是否对任意时刻 t 返回有限值。
- 在谱面快速旋转/平移时段，`pos(t)` 的变化率是否合理。
- `line.time(t)` 和 `line.seconds(t)` 的转换公式是否与谱面 JSON 一致。

#### Step 2: 极端位移识别与分类

使用 `tools/trace_jumps.py` 的输出，对每个 >50px 跳变：

1. 提取 note_id、时间戳、前后坐标。
2. 计算两帧间判定线中心位移 `d = hypot(dx, dy)`。
3. 检查该时间段内是否有 `rotateEvents` 或 `moveEvents` 导致判定线剧烈变化。
4. 分类为：
   - **A类：谱面真实快速运动**（判定线本身在两帧间移动了 >50px）。
   - **B类：计算异常**（判定线变化平缓但 `pos_of()` 返回了错误坐标）。

#### Step 3: 检查 `line.pos_of()` 正确性

阅读 `chart.py` 中 `JudgeLine.pos_of()` 实现，重点检查：

- `note.x` 偏移量是否正确应用。
- `line.angle()` 在 HOLD 持续期间是否被正确更新。
- 是否存在浮点精度累积误差。

#### Step 4: 研究坐标转换与采样

- 确认 `line.seconds(note.time)` 和 `line.time(ms/1000)` 的转换系数（1.875/bpm）是否正确。
- 确认 `alpha = -line.angle(...) * pi/180` 的角度方向是否正确。
- 确认 `off_x = note.x * 72` 的缩放因子是否正确。

#### Step 5: 输出报告

对每个 >50px 跳变输出：

```
note_id=N, t0=T0ms, t1=T1ms, p0=(X0,Y0), p1=(X1,Y1), d=D px
判定线中心位移: dx=X, dy=Y, d_line=L px
该时段 rotateEvents: [...]
该时段 moveEvents: [...]
分类: A/B
```

### 3.3 预期结果

- 如果全部归类为 A 类（谱面真实快速运动）→ 保留原始轨迹，记录为合法高速运动，无需修复。
- 如果发现 B 类（计算异常）→ 针对性修复 `pos_of()` 或相关转换函数。

---

## 四、14 个按下噪域违规的调查方案

### 4.1 违规列表（来自审计脚本）

```
74851ms type=2 (149,323)
75223ms type=2 (159,268)
75297ms type=2 (84,337)
75371ms type=2 (153,264)
75446ms type=2 (80,333)
81238ms type=2 (259,156)
81980ms type=2 (1024,216)
82351ms type=2 (1044,201)
82426ms type=2 (976,127)
82500ms type=2 (1050,196)
82574ms type=2 (982,123)
82723ms type=2 (1093,227)
```

共 14 个，全部是 `type=2`（DRAG 音符走 `_tap` 路径）。

### 4.2 调查步骤

对每个违规点：

1. **原始坐标 vs 最终坐标**：对比 `note.pos`（原始）和下发坐标。
2. **噪域边界距离**：计算下发点到最近噪域边缘的距离。
3. **判定线垂直距离**：调用 `point_line_distance(下发坐标, line)`。
4. **实际迁移距离**：`hypot(下发x-原始x, 下发y-原始y)`。
5. **search_point 过程**：模拟 `search_point` 的执行流程，确认：
   - 法向搜索是否遍历了所有候选。
   - nearby_points 兜底是否被触发。
   - fallback 是否找到了合法点但未正确下发。
6. **下发一致性**：确认 `_insert` 收到的坐标与 `note.pos` 一致。

### 4.3 重点关注

- 为什么 `type=2`（DRAG 音符）会走 `_tap` 路径？检查 `solve()` 中的分支逻辑。
- 这些违规点的噪域是否在 `[t, t+release_ms]` 区间内动态变化导致"按下时合法、执行时非法"。
- 是否存在 `sample_step=5` 采样遗漏的情况。

---

## 五、54 个无解事件的分类审查方案

### 5.1 当前分类

- RELOCATION_LIMIT_EXCEEDED (REL): 35
- NO_VALID_POSITION (NO_VAL): 19

### 5.2 审查步骤

对每个无解事件：

1. **原始坐标**：`(ox, oy)`。
2. **搜索方向**：`(nx_dir, ny_dir)`。
3. **判定线端点**：`line`。
4. **迁移距离**：`hypot(ox-candidate_x, oy-candidate_y)`（如果有接近的候选）。
5. **噪域覆盖分析**：在 `[t, t+duration]` 区间内，逐桶检查哪些 BlockArea 覆盖了屏幕。
6. **判定线距离约束影响**：移除 `min_dist` 约束后重新运行 `search_point`，看是否能找到解。

### 5.3 分类标准

| 类别 | 条件 |
|------|------|
| 整屏噪域覆盖 | 全屏不存在满足噪域约束的点 |
| 超出迁移距离 | 存在合法点但全在 200px 之外 |
| min_dist 约束 | 合法点在 80px 距离约束下被排除 |
| 搜索遗漏 | 理论上存在合法点但 `search_point` 未找到 |
| 几何异常 | 判定线退化、坐标非有限等 |

### 5.4 验证方法

对每个无解事件，手动调用 `search_point` 并打印中间状态：

```python
print(f"search_point: pos={pos}, t={t:.3f}, dir=({nx},{ny})")
print(f"  ok(pos)? {ok(*pos)}")
print(f"  法向搜索范围: 1..{min(MAX_STEPS, int(max_relocation//STEP)+1)}")
print(f"  nearby_points 命中数: N")
```

---

## 六、噪域避让算法的进一步验证

### 6.1 `search_point` 正确性验证

1. **法向搜索完整性**：确认 `(nx_dir, ny_dir)` 始终指向远离判定线的方向。
2. **nearby_points 均匀性**：确认半径 r 上的采样点数 `n = max(8, ceil(2πr/STEP))` 足够密集。
3. **duration 检查**：确认 `[t, t+duration]` 区间的采样步长 `sample_step=5` 不会遗漏瞬态噪域。

### 6.2 边界情况测试

| 场景 | 预期行为 |
|------|----------|
| 噪域完全覆盖屏幕 | NO_VALID_POSITION |
| 噪域刚好接触触点 | blocked 返回 True（margin 生效） |
| 判定线角度 0°/90° | point_line_distance 正确 |
| 判定线两端点重合 | ValueError → INVALID_GEOMETRY |
| pos 包含 NaN/Inf | INVALID_GEOMETRY |

---

## 七、回归测试方案

### 7.1 测试矩阵

| 测试组 | 内容 | 通过标准 |
|--------|------|----------|
| T1 | 无噪域时 Tap/Drags/Flicks/Holds | 全部正常点击，无跳过 |
| T2 | 静态噪域 | 所有音符落在噪域外 |
| T3 | 动态噪域（move/rotate/scale） | 同上 |
| T4 | 极限迁移距离 | 不超过 200px，无解时正确记录 |
| T5 | 判定线快速旋转 | HOLD 严格跟随，无偏离 |
| T6 | 完整谱面 Chart_AT.json | 审计脚本 7 项指标可复现 |

### 7.2 自动化检查

每次修改后运行：

```bash
venv/bin/python tools/audit_noise.py
venv/bin/python tools/trace_jumps.py
```

对比输出确保：

- 无解数量不增加。
- 按下噪域违规不增加。
- 跳变数量不增加。
- 已修复的 TAP/FLICK 点按能力保持。

---

## 八、分阶段开发路线

### Phase 0：保存稳定版本和审计基线（已完成）

- ✅ GitHub 推送稳定版本。
- ✅ 审计脚本产出基线数据。
- ✅ 跳变追踪脚本产出诊断数据。

### Phase 1：HOLD 轨迹连续性调查（只诊断，不修改）

**目标**：确认 998px 跳变是谱面真实运动还是计算异常。

**交付物**：

- 每个 >50px 跳变的详细报告（note_id、时间、坐标、判定线位移、分类）。
- 结论：是否需要修复，以及修复方向。

**不修改的代码**：`algo/algo2.py`、`chart.py`、`block_area.py`。

### Phase 2：调查 14 个按下噪域违规

**目标**：逐个确认违规原因。

**交付物**：

- 14 个违规点的详细分析报告。
- 结论：是 search_point 漏找、fallback 错误、还是噪域定义本身的问题。

### Phase 3：审查 54 个无解事件

**目标**：确认分类准确性，找出可修复的误判。

**交付物**：

- 54 个事件的分类表（整屏覆盖/超出距离/min_dist/搜索遗漏/几何异常）。
- 可修复事件清单及修复建议。

### Phase 4：小范围修复

**前提**：Phase 1-3 有明确证据支持。

**可能的修复方向**：

1. 如果 Phase 1 发现 `pos_of()` 计算异常 → 修复 `chart.py`。
2. 如果 Phase 2 发现 search_point 漏找 → 改进 `block_area.py` 搜索策略。
3. 如果 Phase 3 发现误判 → 调整 `PlacementFailure` 分类逻辑。

**严格限制**：

- 每次修复只改一个函数。
- 修复后运行完整回归测试。
- 不修改 MARGIN/MIN_DIST/MAX_RELOCATION_DISTANCE。

### Phase 5：完整谱面回归测试

**目标**：确认所有修复未破坏已有功能。

**通过标准**：

- T1-T6 全部通过。
- 审计指标无恶化。
- 点按功能正常。

---

## 九、风险与未解决问题

### 9.1 已知风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| HOLD 轨迹修复可能影响跟随精度 | 高 | 先诊断再修复，不盲目加限速 |
| search_point 改进可能引入性能问题 | 中 | 监控规划耗时 |
| 参数调整可能掩盖真正问题 | 高 | 暂不修改参数 |

### 9.2 未解决问题

1. **14 个按下噪域违规**：尚未确认是 search_point 漏找还是其他原因。
2. **54 个无解事件**：尚未确认分类准确性。
3. **998px 跳变**：确认为谱面真实快速运动还是计算异常待 Phase 1 确认。
4. **type=2 走 _tap 路径**：DRAG 音符为何走 TAP 路径需确认设计意图。

---

## 十、验收标准

### 10.1 Phase 1 验收

- [ ] 所有 >50px 跳变均有详细报告。
- [ ] 每个跳变已分类为 A（谱面真实运动）或 B（计算异常）。
- [ ] 结论明确：需要修复或不需要修复。

### 10.2 Phase 2 验收

- [ ] 14 个按下噪域违规全部有分析报告。
- [ ] 每个违规的原因已确认。
- [ ] 修复建议明确（如有）。

### 10.3 Phase 3 验收

- [ ] 54 个无解事件全部有分类。
- [ ] 分类准确性已验证（至少抽样 10 个）。
- [ ] 可修复事件清单已列出。

### 10.4 Phase 4 验收

- [ ] 每次修复只改一个函数。
- [ ] 修复后 T1-T6 全部通过。
- [ ] 审计指标无恶化。

### 10.5 Phase 5 验收

- [ ] 完整谱面无回归问题。
- [ ] 点按功能正常。
- [ ] HOLD 严格跟随判定线。
- [ ] 噪域避让正常工作。

---

## 建议的第一项实施任务

**Phase 1：HOLD 轨迹连续性调查**

理由：

1. 998px 跳变是当前最显著的异常指标，且已有完整诊断数据支撑。
2. 这是只读调查，不修改任何代码，风险为零。
3. 调查结果将决定后续是否需要修复 `chart.py` 或 `algo/algo2.py`。
4. 如果确认为谱面真实快速运动，则无需修复，可将精力集中在 14 个按下违规和 54 个无解事件上。

具体行动：

1. 读取 `chart.py` 中 `JudgeLine.pos()`、`pos_of()`、`angle()` 的实现。
2. 扩展 `tools/trace_jumps.py`，对每个 >50px 跳变输出判定线位移和噪域事件信息。
3. 运行扩展后的脚本，生成完整报告。
4. 根据报告得出结论。
