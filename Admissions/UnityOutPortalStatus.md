# 当前状态总结

日期：2026-11-14

## 1. 已完成

- 四种新 Marker 已加入 UI 下拉列表：`PREVIEW_PLAYING`、`START_TRIGGER`、`PREVIEW_STOPPED`、`GAMEPLAY_AUDIO_STARTED`。原有 10 种保持不变。
  - 位置：[timeline.py](phigros_diagnostic/timeline.py#L241)（`ExperimentMarkWidget.EXPERIMENT_TYPES`）
- Marker id 由 `manual*{计数器}` 改为 `manual*{uuid4}`，避免应用重启后计数器归零导致 id 重复。
  - 位置：[timeline.py](phigros_diagnostic/timeline.py#L303)
- `sessions.json` schema 未改变。

## 2. 已验证的链路（临时脚本，已删除，未生成实验数据）

:::table
--- row
--- cell
环节
--- cell
结果
--- row
--- cell
UI 下拉选择
--- cell
通过：14 项，原 10 项保留
--- row
--- cell
数据模型（type/notes/timestamp/id/session_id）
--- cell
通过
--- row
--- cell
保存到当前 session 的 `manual_marks`
--- cell
通过
--- row
--- cell
写入 `sessions.json`
--- cell
通过（顶层字段与原 schema 一致）
--- row
--- cell
管理器层面重载 `load_sessions_from_json`
--- cell
通过
--- row
--- cell
`get_timeline()` 生成 `[TYPE]` 标签
--- cell
通过（仅数据层）
--- row
--- cell
按精确 type 筛选并计算时间差
--- cell
通过
:::

调用链：

1. `ExperimentMarkWidget.add_mark()` → 发出 `mark_added`
2. `MainWindow.on_manual_mark_added()` → `ExperimentSession.add_manual_mark()`
3. `MainWindow.closeEvent()`（选择 Yes）→ `ExperimentManager.save_sessions_to_json()`
4. 重载：`ExperimentManager.load_sessions_from_json()`（UI 中无调用入口）
5. 导出：`ReportExporter.export_formatted_report()` 的 TXT 报告包含 marks

## 3. 未完成

- **时间线展示（未接通）**：UI 从未调用 `get_timeline()`，`TimelineView` 只显示 logcat 解析事件，Marker 不会出现在时间线中。
- **UI 重载（未接通）**：应用启动时不会读取 `sessions.json`，重新打开应用后 session 不会恢复。
- **events JSON 导出**：`export_events_json()` 不包含 marks，仅 TXT 报告包含。
- **保存时机**：`sessions.json` 仅在关闭窗口并选择 Yes 时写入，异常退出会丢失 marks。
- **时间对齐**：mark 时间戳为主机 UTC；logcat `log_time` 为设备本地时间（Asia/Tokyo）。对齐应以 `receive_time` 为准。
- **正式实验**：尚未运行，未生成任何实验数据。

## 4. 修改范围

- 仅修改 [timeline.py](phigros_diagnostic/timeline.py)（新增 `import uuid`，扩展类型列表，修改 id 生成）。
- 未修改自动开始逻辑、未修改 `experiment.py`、`main_window.py`、`report_exporter.py`。

## 5. 待决定

- 是否接通时间线展示（步骤 6）和 UI 启动时的 session 重载（步骤 5）。这两项是正式实验前的必要条件。
- events JSON 是否需要包含 marks。# PhiAPS Unity / Audio Track 调查计划（更新）

> 本更新补充在原《当前状态总结 141126（早）》之后，保留原文及其历史状态。本文根据 Admissions 现有报告与 2026-11-14 的 Android 17 只读身份审计整理；不把当前设备状态倒推为实验时状态。

<!-- notedeep:blank -->

日期：2026-11-14
项目：`/Users/lishuandysun/Documents/Phigros-Autoplay-Script`
实验：`phigros_diagnostic/diags/1411202601/`，session `session_20261114_211923`

## 1. 目标与问题拆分

分别回答两条证据链，避免混为一谈：

1. **Android 系统侧**：OpenSL ES 创建播放对象后，如何经客户端 AudioTrack API 到达 AudioFlinger `createTrack_l()`；实际参与的库、函数、参数及 flags `0x104` 含义是什么？
2. **Phigros 内部**：哪一个游戏侧函数或工厂调用了 `TrackPlayerBase` 构造函数？构造行为与后续音频 track 是否一一对应？

系统源码能解释系统 API 路径，但本身不能识别 Phigros 二进制中的构造调用者。

## 2. 已有证据

### 2.1 Android build identity

以下数据来自 `Admissions/android17_build_identity.md`，是 2026-11-14 12:44:47–12:45:18 UTC 在 `emulator-5554` 上直接读取的**当前设备状态**：

:::table
--- row
--- cell
项目
--- cell
已读值
--- cell
状态
--- row
--- cell
Android
--- cell
17，SDK 37，`userdebug/test-keys`
--- cell
VERIFIED（审计时）
--- row
--- cell
`ro.build.fingerprint`
--- cell
`Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys`
--- cell
VERIFIED（审计时）
--- row
--- cell
Build ID / incremental
--- cell
`CE2A.260420.051.A3` / `16571990`
--- cell
VERIFIED（审计时）
--- row
--- cell
`libOpenSLES.so` GNU Build ID
--- cell
`4f9b436de4a0a3b0a1f1886a2c6e44d0`
--- cell
VERIFIED
--- row
--- cell
`libaudioclient.so` GNU Build ID
--- cell
`d5e03623b0ca530f899f320ba7c9811d`
--- cell
VERIFIED
--- row
--- cell
OpenSL ES 与 AudioTrack 客户端库路径
--- cell
`/system/lib64/libOpenSLES.so`、`/system/lib64/libaudioclient.so`
--- cell
VERIFIED
--- row
--- cell
独立 `libaudioflinger.so`
--- cell
未找到；见到 `libaudioflinger_datapath/fastpath/timing/utils.so`
--- cell
VERIFIED（文件搜索结果）
--- row
--- cell
定义 `createTrack_l()` 的确切模块及其 Build ID
--- cell
尚未定位/读取
--- cell
UNKNOWN
:::

库的 SHA-256、尺寸、MiniDebugInfo 情况及完整审计结果见 `Admissions/android17_build_identity.md`。`audioserver` 当时 PID 为 509，`/proc/509/maps` 因权限拒绝无法读取。

**时间关联限制：** 指纹读取于 12:45Z，实验日志约在 12:19Z。审计记录里实验 `sessions.json` 只保存 Android 17 和设备型号，没有 fingerprint；审计 PID 509 与实验 AudioFlinger PID 506 不同，说明服务进程曾重启或设备重启，但不能证明系统镜像是否改变。当前 build identity 不得直接标注为实验时 identity，需先查 AVD/image 历史或其他已有记录。

### 2.2 实验日志中观察到的序列

`Admissions/TrackPlayerbaseCallsiteInvestigation.md` 记录 `raw_logs.txt` 第 24600–24615 行：Phigros PID 2219/TID 2235 三次打印 `PlayerBase::PlayerBase()` 与 `TrackPlayerBase::TrackPlayerBase()`；每次紧邻 `libOpenSLES` channel-mask 兼容日志，随后约 1 ms 出现 AudioFlinger `createTrack_l()` 请求 flags `0x104`、输出 flags `0x2`。另有更早的 `createTrack_l()`（flags `0x4`、`0x8`），其 owner 未知。

- **VERIFIED：** 这些是同进程/线程中的日志共现；构造日志无对象地址、track 名或 session ID，AudioFlinger 行也未给出 client PID。
- **SUPPORTED：** 三组序列与 OpenSL ES 创建播放 track 相符，构造时刻更像初始化而非可听播放开始。日志时间邻近并不能证明每个构造调用确实创建了对应 track。
- **UNKNOWN：** 上述 flags 在该确切系统 build 中的逐位解释、创建请求与游戏对象的因果对应、音频何时实际送达扬声器。

### 2.3 `TrackPlayerBase` 身份与调用者

- **VERIFIED：** 日志 tag 是 `onGames.Phigros`，显示未带 namespace 的 `TrackPlayerBase::TrackPlayerBase()`。PhiAPS 的 `event_parser.py` 仅把这些字符串作为日志 marker。
- **UNKNOWN：** `TrackPlayerBase` 的定义、namespace、继承关系、构造函数实现及立即调用者。仓库搜索没有发现生产代码定义或构造点；相关符号很可能位于游戏二进制或注入/诊断组件中，但目前仅是推测。
- `android::TrackPlayerBase` 尚无证据支持，不应当作已确认类名或 Android framework 类。
- 目前没有开始 APK/native library 逆向，也没有匹配的调试符号。

## 3. 未确认事项清单

1. 当前 emulator 镜像是否与 12:19Z 实验运行镜像相同。
2. 与 fingerprint/build 完全匹配的 Android 源码 revision、构建 manifest 或符号产物是否可取得；不可仅凭 Android 17 猜分支。
3. `createTrack_l()` 实际所在的 Android 17 模块及其 GNU Build ID、符号可见性。
4. OpenSL ES 的 player/object 创建 API 至 AudioTrack 创建的实际函数链，以及此 build 中 flags `0x104` 的准确含义。
5. `PlayerBase` / `TrackPlayerBase` 的真实定义及游戏进程内直接构造调用者。
6. 三个构造 burst 与三个 AudioFlinger 请求是否一一对应，以及更早两个请求属于哪个 client。

## 4. 调查计划与阶段顺序

### 阶段 0：固定证据与版本关联（先做）

- 只审阅已有 `sessions.json`、实验记录和 emulator/AVD 元数据，判断能否把当前 fingerprint 与实验时镜像关联起来；不重跑实验、不重启设备。
- 把“审计时设备身份”和“实验时身份”分开记录。若无法关联，后续系统结论只适用于审计所读 build，并明确这一限制。
- 从已有设备文件清单定位 AudioFlinger 相关模块；若获准进行新的只读设备审计，再读取候选模块的 Build ID 和符号信息。不得因缺项而更改镜像。

**阶段出口：** 有可追溯的目标 build/module 清单；每项标明实验时匹配程度。

### 阶段 1：Android 系统侧源码与符号路径

- 以完整 fingerprint `.../CE2A.260420.051.A3/16571990:...`、库 Build ID 和可获得的构建元数据寻找匹配源码/符号；记录来源及直接匹配证据，不臆造 tag、branch 或 revision。
- 在匹配源码中，从 OpenSL ES 播放对象/player 创建入口向下跟踪到 `AudioTrack` 客户端构造/初始化，再到 AudioFlinger `createTrack_l()`；标出源码路径、行号、调用条件和边界。
- 结合该 build 的定义解释请求 flags `0x104` 与输出 flags `0x2`，核实日志中 flags mismatch 的实际语义；不要用其他 Android 版本的常量或行为替代。
- 检查可用符号/二进制中的日志字符串与相关符号，区分静态源码链与本次日志能直接证明的事实。
- 明确系统链只能说明客户端如何到达 AudioFlinger，不能单独给出 Phigros 内部调用者。

**阶段出口：** 一条带源码/符号证据的 OpenSL ES → AudioTrack → AudioFlinger 路径；flags 有版本依据，未匹配处列为 UNKNOWN。

### 阶段 2：Phigros 内部构造调用者定位

- 先盘点**已有** APK/native library、符号文件、崩溃符号化文件、构建产物与日志 hook 来源；不改应用、不安装、不导出或覆盖实验数据。
- 只有存在可读的既有二进制材料时，才做离线只读字符串/符号/反汇编定位：确认 marker 字符串由哪个模块发出，查找构造函数入口及其直接引用者，逐层记录地址、符号状态、调用约定与推断置信度。
- 将直接 caller 与更高层业务调用链（例如 Unity/游戏音频管理器）分开；没有符号或可验证交叉引用时，不猜函数名。
- 使用现有日志中的 PID/TID、时间、flags 和可用 session/client 标识交叉核对。单靠毫秒级相邻日志不能宣称一一映射。
- 若所需 APK/native binary 当前不存在，停止于材料缺口说明；是否取得或分析它应作为新的明确范围决定，不通过实验或修改配置来补材料。

**阶段出口：** 要么给出可复核的直接调用者证据，要么清楚列出缺少的二进制/符号/关联标识及其影响。

### 阶段 3：综合与结论

- 合并两条链，区分已观察事件、源码确认行为、推断和未知项。
- 核对时间域（设备本地时间、host UTC、接收时间）和 PID 差异；将构造/track 创建与可听播放开始分开。
- 形成简短结论、证据表、调用链图及可复查的源文件路径/行号、Build ID 或二进制偏移。

## 5. 只读约束

整个调查仅检查现有 Admissions 报告、源码、实验材料、设备/镜像元数据和已有二进制材料。不得：

- 修改 PhiAPS 或 Phigros 应用代码、安装包、构建产物；
- 修改/生成/清理实验数据、`sessions`、`markers`、日志、事件文件或报告以外的项目数据；
- 启动或重跑实验，触发游戏播放，重启/更新/重配置模拟器；
- 通过改 hook、改系统属性、改音频配置或改变实验环境来取得证据；
- 将未验证的 Android 源码分支、符号归属、类关系或业务调用者写成事实。

本计划不授权上述任何操作。任何需要新增采集或超出只读检查的步骤，先停止并单独说明所需范围。

## 6. 完成标准

调查完成时应能交付：

1. 当前 build 与实验 build 的身份关联结论（匹配或明确 UNKNOWN），以及关键系统库/module 的 Build ID 清单。
2. 有准确版本依据的 OpenSL ES → AudioTrack → AudioFlinger 创建路径；`createTrack_l()` 所属组件和 flags 含义均有来源，或明确标 UNKNOWN。
3. `PlayerBase` / `TrackPlayerBase` 的身份结论及 Phigros 内直接构造 caller 的证据；若无法定位，说明具体缺失材料，不作猜测。
4. 对三次构造日志与 AudioFlinger 请求的关联强度、时间误差及实际播放状态给出分级结论。
5. 每条结论用 VERIFIED / SUPPORTED / HYPOTHESIS / UNKNOWN 标注，并附可复查的文件行号、源码 revision、Build ID 或地址。
6. 只读边界得到遵守：应用代码、实验数据、sessions、markers 和模拟器配置未改动，实验未重跑。

## 7. 现有资料索引

- `Admissions/android17_build_identity.md`：设备身份与库审计、时间和权限限制。
- `Admissions/TrackPlayerbaseCallsiteInvestigation.md`：构造日志、call-site 搜索与推断边界。
- `Admissions/AUDIO_PLAYBACK_PIPELINE_AUDIT.md`：创建、buffer submission、mixing proxy 与可听声音的区分。
- `phigros_diagnostic/diags/1411202601/raw_logs.txt`：原始实验日志；关键范围 23846、24491、24600–24615。
- `phigros_diagnostic/experiment_data/sessions.json`：实验 session 元数据（不含本次审计的 fingerprint）。