# Phigros Diagnostic Tool

A standalone diagnostic tool for studying Phigros Unity game logs, audio player lifecycle, and observable events via ADB Logcat.

## Features

- Real-time ADB Logcat monitoring with PID filtering
- Automatic parsing of PlayerBase/TrackPlayerBase lifecycle events
- Manual experiment marking (game start, song select, map load, play start, etc.)
- Timeline visualization with interval calculation
- Export to TXT, JSON, CSV formats
- Multiple independent experiment sessions

## Requirements

```bash
pip install pyside6
```

## Usage

```bash
python main.py
```

## Important Notes

- This tool does NOT modify Phigros or PhiAPS
- Raw logs are preserved separately from parsed results
- PlayerBase construction time is NOT assumed to be music playback start time
- Log timestamps are distinguished from log reception times
