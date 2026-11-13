"""Phigros Diagnostic Tool - Logcat Monitor Module."""

import re
import subprocess
import threading
import time
from datetime import datetime, timezone


class LogcatMonitor:
    """Monitors Android device logcat via ADB subprocess.
    
    Supports start/pause/resume/stop controls, PID filtering,
    and raw log preservation with thread-safe callbacks.
    """

    def __init__(self):
        """Initialize the monitor with empty state."""
        self._process = None
        self._thread = None
        self._running = False
        self._paused = False
        self._pid_filter = None
        self._callbacks = []  # List of callback functions
        self._lock = threading.Lock()
        self._last_line_time = None
        self._device_name = None

    @property
    def is_running(self):
        """Check if monitor is actively reading logs."""
        return self._running

    @property
    def is_paused(self):
        """Check if monitor is paused."""
        return self._paused

    @property
    def pid_filter(self):
        """Get current PID filter."""
        return self._pid_filter

    @pid_filter.setter
    def pid_filter(self, pid):
        """Set PID filter for logcat output."""
        self._pid_filter = pid

    def set_device(self, device_name):
        """Set the ADB device name."""
        self._device_name = device_name

    def _build_command(self):
        """Build the ADB logcat command."""
        cmd = ["adb"]
        if self._device_name:
            cmd.extend(["-s", self._device_name])
        cmd.append("logcat")
        
        # Add PID filter if set
        if self._pid_filter:
            cmd.extend(["--pid", self._pid_filter])
        
        # threadtime includes date/time, PID, TID, priority and tag
        cmd.extend(["-v", "threadtime"])
        
        return cmd

    # threadtime: "MM-DD HH:MM:SS.mmm  PID  TID P TAG: message"
    THREADTIME_RE = re.compile(
        r'^(\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEFA])\s+(.*?)\s*:\s?(.*)$'
    )

    def _parse_adb_output(self, line):
        """Parse a threadtime logcat line.

        Returns:
            dict with keys: device_timestamp_raw (str or None), pid (str or None),
            tid (str or None), priority (str or None), tag (str or None), raw_line (str)
        """
        match = self.THREADTIME_RE.match(line)
        if not match:
            return {
                'device_timestamp_raw': None, 'pid': None, 'tid': None,
                'priority': None, 'tag': None, 'raw_line': line,
            }
        date_part, time_part, pid, tid, priority, tag, _message = match.groups()
        return {
            'device_timestamp_raw': f"{date_part} {time_part}",
            'pid': pid,
            'tid': tid,
            'priority': priority,
            'tag': tag.strip(),
            'raw_line': line,
        }

    def _read_loop(self):
        """Internal loop to read from logcat subprocess."""
        try:
            while self._running and not self._paused:
                if self._process and self._process.poll() is None:
                    line = self._process.stdout.readline()
                    if line:
                        line = line.strip()
                        if line:
                            fields = self._parse_adb_output(line)
                            raw_line = fields['raw_line']

                            # Device timestamp is kept as a naive, timezone-less
                            # value. It is NOT UTC: the device clock is unknown.
                            log_time = None
                            if fields['device_timestamp_raw']:
                                try:
                                    log_time = datetime.strptime(
                                        f"{datetime.now().year}-{fields['device_timestamp_raw']}",
                                        "%Y-%m-%d %H:%M:%S.%f"
                                    )
                                except ValueError:
                                    log_time = None

                            # Receive time is timezone-aware UTC (tool clock)
                            now = datetime.now(timezone.utc)
                            for cb in self._callbacks:
                                try:
                                    cb(raw_line, log_time, now, fields)
                                except Exception as e:
                                    print(f"Callback error: {e}")
                    
                    self._last_line_time = datetime.now(timezone.utc)
                elif self._process and self._process.poll() is not None:
                    # Process ended unexpectedly
                    break
                else:
                    time.sleep(0.1)
        except Exception as e:
            print(f"Logcat read error: {e}")
        finally:
            self._running = False

    def start(self):
        """Start reading logcat from ADB device."""
        if self._running:
            return
        
        try:
            cmd = self._build_command()
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=True,
                bufsize=1  # Line buffered
            )
            self._running = True
            self._paused = False
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
        except FileNotFoundError:
            raise RuntimeError("ADB not found. Please install Android SDK Platform-Tools.")
        except Exception as e:
            self._running = False
            raise RuntimeError(f"Failed to start logcat: {e}")

    def pause(self):
        """Pause logcat reading (keeps connection alive)."""
        self._paused = True

    def resume(self):
        """Resume logcat reading after pause."""
        self._paused = False

    def stop(self):
        """Stop logcat reading and terminate subprocess."""
        self._paused = False
        self._running = False
        
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                if self._process.poll() is None:
                    self._process.kill()
        
        if self._thread:
            self._thread.join(timeout=2)
        
        self._process = None
        self._thread = None

    def add_callback(self, callback):
        """Add a callback function for new log lines.
        
        Args:
            callback: Function signature: callback(raw_line, log_time, receive_time)
                     - raw_line: str, the complete log line
                     - log_time: datetime or None, parsed log timestamp
                     - receive_time: datetime, when this line was received
        """
        with self._lock:
            self._callbacks.append(callback)

    def remove_callback(self, callback):
        """Remove a previously added callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def get_device_info(self, device_id):
        """Read basic device properties over ADB.

        Each property is read independently. A failed read is recorded as
        None with an error string, never as a guessed value.

        Returns:
            dict: {'serial', 'model', 'android_version', 'errors'}
        """
        info = {'serial': device_id, 'model': None, 'android_version': None, 'errors': []}
        prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        queries = {
            'model': ["shell", "getprop", "ro.product.model"],
            'android_version': ["shell", "getprop", "ro.build.version.release"],
        }
        for key, args in queries.items():
            try:
                result = subprocess.run(
                    prefix + args, capture_output=True, text=True, timeout=5
                )
                value = result.stdout.strip()
                if result.returncode == 0 and value:
                    info[key] = value
                else:
                    info['errors'].append(f"{key}: empty or failed")
            except Exception as e:
                info['errors'].append(f"{key}: {e}")
        return info

    def get_device_list(self):
        """Get list of connected ADB devices.
        
        Returns:
            list: List of (device_id, status) tuples
        """
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10
            )
            devices = []
            for line in result.stdout.strip().split('\n')[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    devices.append((parts[0], parts[1]))
            return devices
        except Exception:
            return []

    def check_adb_connection(self):
        """Check if ADB is working and device is connected.
        
        Returns:
            dict: {'success': bool, 'message': str, 'devices': list}
        """
        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return {
                    'success': False,
                    'message': 'ADB command failed',
                    'devices': []
                }
            
            devices = self.get_device_list()
            connected = [d for d in devices if d[1] == 'device']
            
            if not connected:
                return {
                    'success': False,
                    'message': 'No Android device connected',
                    'devices': devices
                }
            
            return {
                'success': True,
                'message': f'Connected to {len(connected)} device(s)',
                'devices': connected
            }
        except FileNotFoundError:
            return {
                'success': False,
                'message': 'ADB not installed',
                'devices': []
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e),
                'devices': []
            }
