# 当前状态总结

日期：2026-11-14

## 1. 已完成

- 四种新 Marker 已加入 UI 下拉列表：`PREVIEW_PLAYING`、`START_TRIGGER`、`PREVIEW_STOPPED`、`GAMEPLAY_AUDIO_STARTED`。原有 10 种保持不变。
  - 位置：[timeline.py](phigros_diagnostic/timeline.py#L241)（`ExperimentMarkWidget.EXPERIMENT_TYPES`）
- Marker id 由 `manual_{计数器}` 改为 `manual_{uuid4}`，避免应用重启后计数器归零导致 id 重复。
  - 位置：[timeline.py](phigros_diagnostic/timeline.py#L303)
- `sessions.json` schema 未改变。

## 2. 已验证的链路（临时脚本，已删除，未生成实验数据）

| 环节 | 结果 |
|---|---|
| UI 下拉选择 | 通过：14 项，原 10 项保留 |
| 数据模型（type/notes/timestamp/id/session_id） | 通过 |
| 保存到当前 session 的 `manual_marks` | 通过 |
| 写入 `sessions.json` | 通过（顶层字段与原 schema 一致） |
| 管理器层面重载 `load_sessions_from_json` | 通过 |
| `get_timeline()` 生成 `[TYPE]` 标签 | 通过（仅数据层） |
| 按精确 type 筛选并计算时间差 | 通过 |

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
- events JSON 是否需要包含 marks。
