# PhiAPS 双轮实验联合审计：手动标记与操作日志关联

范围：`diags/1211202605`（第一轮）与 `diags/1211202606`（第二轮）。只读分析，未修改原始日志、`events.json`、`statistics.csv`、`report.txt` 或程序代码，未运行游戏。

## 1. 时间基准

| 轮次 | 标记时间 | 日志时间基准 | 换算 |
|---|---|---|---|
| 第一轮 | UTC（`receive_time`） | 仅有 `receive_time`，无设备时间戳 | 直接用 `receive_time` 对齐 |
| 第二轮 | UTC | 设备时间（`timestamp`）为本地时间 | 设备时间 = UTC + 9 小时 |

第二轮时钟偏移已验证：1489 条实时事件的 `receive_time - timestamp` 中位数为 -9.0000 h，最小与最大值一致，即设备时间恰为 UTC+9。

第二轮 `logcat -v threadtime` 回放的积压事件（约 13:08:24 UTC 一次性接收）其 `receive_time` 不可用于对齐，必须以设备时间戳为准。

## 2. 标记清单

- 第一轮：7 个标记（按 `receive_time` UTC）。
- 第二轮：8 个标记（来自 `experiment_data/sessions.json` 的 `manual_marks`）。前 3 个标记（13:07:55、13:08:00、13:08:03 UTC）对应设备时间 22:07:55、22:08:00、22:08:03，其 ±3 秒内无事件，因为回放在 22:08:24 才开始；这 3 个标记在 `receive_time` 维度上是空的。

## 3. 第二轮设备时间窗口（已核对）

| 标记（设备时间） | 游戏进程（PID 4063）事件 | 说明 |
|---|---|---|
| Map Load Start 22:07:55.897 | 无直接游戏事件；窗口内有 `Surface` 创建（643，22:07:55.049） | 系统层 Surface 事件，非游戏加载证据 |
| Map Load End 22:08:00.434 | `System.out` SecurityException（22:08:00.383）、`TapSdkCore` 网络错误（22:08:02.388） | 与加载完成无直接关联 |
| Play Start 22:08:03.521 | `TapSdkCore` 网络错误（22:08:02.388 之后的重试窗口） | 无输入或 Play 状态事件 |
| Map Load Start 2 22:08:50.906 | 窗口内无游戏进程事件 | 仅 `ActivityManager` 冻结其他进程 |
| Play Start 2 22:08:58.817 | `System.out` SecurityException（22:09:00.390，窗口外） | 无 Play 状态事件 |
| Play End 22:11:03.873 | `TapSdkCore` 网络错误（22:11:02.447） | 无结束事件 |
| Score Screen 22:11:06.267 | 窗口内无游戏进程事件 | 第二轮 8 个标记的第 8 个（`sessions.json`） |

第二轮 8 个标记（`sessions.json` 的 `manual_marks`）依次为：Map Load Start、Map Load End、Play Start、Map Load Start、Map Load End、Play Start、Play End、Score Screen。第一轮标记类型本次未逐一核对，第一轮的 Pause/Resume 未在本次验证。

## 4. 游戏生命周期（设备时间，第二轮）

- `PlayerBase::PlayerBase()` / `TrackPlayerBase::TrackPlayerBase()` 构造：
  - PID 3307：21:01:16
  - PID 3730：21:01:34，21:08:07
  - PID 4063：21:16:46，22:07:29
- `~PlayerBase()` 析构：PID 3307 于 20:42:03；PID 3730 与 4063 未见析构日志。

构造事件表示游戏场景对象创建，但不证明已进入可演奏状态，也不证明收到开始信号。

第一轮对应的构造事件（UTC `receive_time`）：
- PID 3307：12:16:42
- PID 3730：12:16:42
- PID 4063：12:16:45

## 5. 自动开始链路

| 环节 | 证据 | 状态 |
|---|---|---|
| 内部信号：`main.py` 屏幕中心 `ctl.tap(...)`（约 L504）随后 `self.start_time = time.time() + offset` | 代码可见 | 已确认（代码路径） |
| 计划中的 `KEYCODE_DPAD_CENTER`（`AutoStartCalibrationPlan.md` 约 L320–420） | 仓库内无实现（未搜到 `auto_start`、`KEYCODE_DPAD`、`keyevent`） | 仅计划，未实现 |
| 设备输入派发（`InputDispatcher` / 触摸事件） | 第二轮 22:07:40–22:12:00 窗口内未找到 | NOT OBSERVED |
| 游戏对输入的响应（Play 状态切换） | 无对应事件 | NOT OBSERVED |
| 第一个真实 Note 的时间关系 | 未检查谱面数据 | NOT OBSERVED |

结论：PhiAPS 开始信号的精确时间无法从日志确定。日志中没有可与标记对齐的输入证据，因此无法判定信号发出时刻与首个真实 Note 的先后关系。

## 6. 第一轮的限制

- 第一轮 `events.json` 缺少 `pid`、`tid`、`tag` 与设备日期，无法做 PID 级跨轮比对。
- 第一轮标记窗口（按 `receive_time`）主要被 Wi-Fi 与 Telephony 噪声占满，未发现与 Play Start 直接对应的输入事件。

## 7. 跨轮验证的操作

| 操作 | 第一轮 | 第二轮 | 跨轮状态 |
|---|---|---|---|
| 游戏场景加载（PlayerBase 构造） | 有（12:16:42–45 UTC） | 有（21:01、21:08、21:16、22:07 设备时间） | 已验证，但不代表可演奏 |
| 游戏进程重启 / 死亡 | 有（12:16:41 析构） | 有（20:42、21:01、21:16） | 已验证 |
| 手动 Play Start | 标记存在，无对应输入日志 | 标记存在，无对应输入日志 | 未验证 |
| 自动 Play Start（tap） | 代码路径，无日志 | 代码路径，无日志 | 未验证 |

## 8. 缺失证据清单

1. 设备端输入派发日志（`InputDispatcher`、触摸坐标）在标记窗口内缺失。
2. 游戏侧 Play 状态切换（如谱面开始、Track 播放）缺失。
3. 第一轮缺少 PID、TID、设备日期，无法做进程级对齐。
4. 第二轮前 3 个标记因回放时间问题无法在 `receive_time` 维度对齐。
5. 谱面数据未检查，无法计算首个真实 Note 的时间。

## 9. 下一轮日志建议

- 同时采集 `InputDispatcher` 与 `InputReader`，过滤 `Touch` 与 `KEYCODE` 事件。
- 在 PhiAPS 发出 tap 或 keyevent 前后各记录一条带设备时间的日志（使用 `adb shell date +%s%3N`）。
- 使用 `logcat -v threadtime` 并保证实时采集，避免回放积压。
- 为每个标记同时记录 UTC 与设备时间，并在 `sessions.json` 中写明时区。
- 记录游戏侧 Play 状态（如谱面开始回调），以便与输入时间对齐。

## 10. 结论

- 已确认：第二轮设备时间为 UTC+9；游戏场景加载与进程生命周期可由日志追踪。
- 未确认：PhiAPS 开始信号的精确时间；信号是否被设备接收；游戏是否进入可演奏状态。
- NOT OBSERVED：首个真实 Note 与开始信号的先后关系。
