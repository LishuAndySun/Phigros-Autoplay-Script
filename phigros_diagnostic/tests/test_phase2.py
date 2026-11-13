"""Phase 2 regression tests for the Phigros Diagnostic Tool.

Run from the phigros_diagnostic folder:
    QT_QPA_PLATFORM=offscreen ../venv/bin/python -m unittest discover -s tests -v

These tests never write to the diags/ folder. The regression test only reads
diags/1211202605/raw_logs.txt.
"""

import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_DIR)

from event_parser import EventParser, EventType  # noqa: E402
from logcat_monitor import LogcatMonitor  # noqa: E402

THREADTIME_LINE = (
    "04-14 12:16:45.824 3307 3350 D onGames.Phigros: PlayerBase::PlayerBase()"
)
LEGACY_LINE = "D( 3307) PlayerBase::PlayerBase()  (onGames.Phigros)"


class TestThreadtimeParsing(unittest.TestCase):
    """F1 and F2: threadtime fields are parsed and not guessed."""

    def setUp(self):
        self.monitor = LogcatMonitor()
        self.parser = EventParser()

    def test_threadtime_fields_extracted(self):
        fields = self.monitor._parse_adb_output(THREADTIME_LINE)
        self.assertEqual(fields['device_timestamp_raw'], "04-14 12:16:45.824")
        self.assertEqual(fields['pid'], "3307")
        self.assertEqual(fields['tid'], "3350")
        self.assertEqual(fields['priority'], "D")
        self.assertEqual(fields['tag'], "onGames.Phigros")
        self.assertEqual(fields['raw_line'], THREADTIME_LINE)

    def test_non_threadtime_line_has_no_fields(self):
        fields = self.monitor._parse_adb_output(LEGACY_LINE)
        self.assertIsNone(fields['device_timestamp_raw'])
        self.assertIsNone(fields['pid'])
        self.assertIsNone(fields['tid'])
        self.assertEqual(fields['raw_line'], LEGACY_LINE)

    def test_build_command_uses_threadtime(self):
        cmd = self.monitor._build_command()
        self.assertIn("threadtime", cmd)
        self.assertNotIn("process", cmd)

    def test_device_timestamp_is_naive_not_utc(self):
        fields = self.monitor._parse_adb_output(THREADTIME_LINE)
        log_time = datetime.strptime(
            f"{datetime.now().year}-{fields['device_timestamp_raw']}",
            "%Y-%m-%d %H:%M:%S.%f",
        )
        self.assertIsNone(log_time.tzinfo)

    def test_event_carries_pid_tid_and_timestamp(self):
        fields = self.monitor._parse_adb_output(THREADTIME_LINE)
        log_time = datetime(2026, 4, 14, 12, 16, 45, 824000)
        receive = datetime.now(timezone.utc)
        events = self.parser.parse_line(THREADTIME_LINE, log_time, receive, fields)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.event_type, EventType.PLAYER_BASE_CREATED)
        self.assertEqual(ev.pid, "3307")
        self.assertEqual(ev.tid, "3350")
        self.assertEqual(ev.timestamp, log_time)
        self.assertIsNotNone(ev.receive_time.tzinfo)
        d = ev.to_dict()
        self.assertEqual(d['pid'], "3307")
        self.assertEqual(d['tid'], "3350")

    def test_pid_not_guessed_from_message_text(self):
        line = "D( 4063) PlayerBase::PlayerBase()  (onGames.Phigros)"
        events = self.parser.parse_line(line, None, None, None)
        self.assertIsNone(events[0].pid)


class TestLifecyclePairing(unittest.TestCase):
    """F3: pairing is per PID and destructors are not silently dropped."""

    def setUp(self):
        self.parser = EventParser()

    def _ev(self, text, pid):
        fields = {'pid': pid, 'tid': None, 'priority': 'D', 'tag': 'x'}
        return self.parser.parse_line(text, None, None, fields)[0]

    def test_pairs_within_same_pid(self):
        events = [
            self._ev("PlayerBase::PlayerBase()", "1"),
            self._ev("PlayerBase::~PlayerBase()", "1"),
        ]
        result = self.parser.get_lifecycle_pairs(events)
        self.assertEqual(len(result['player_bases']), 1)
        self.assertEqual(result['unpaired_creates'], [])
        self.assertEqual(result['unpaired_destroys'], [])

    def test_different_pids_do_not_pair(self):
        events = [
            self._ev("PlayerBase::PlayerBase()", "1"),
            self._ev("PlayerBase::~PlayerBase()", "2"),
        ]
        result = self.parser.get_lifecycle_pairs(events)
        self.assertEqual(result['player_bases'], [])
        self.assertEqual(len(result['unpaired_creates']), 1)
        self.assertEqual(len(result['unpaired_destroys']), 1)

    def test_destructor_before_constructor_is_reported(self):
        events = [
            self._ev("TrackPlayerBase::~TrackPlayerBase()", "5"),
            self._ev("TrackPlayerBase::TrackPlayerBase()", "5"),
        ]
        result = self.parser.get_lifecycle_pairs(events)
        self.assertEqual(result['track_player_bases'], [])
        self.assertEqual(len(result['unpaired_destroys']), 1)
        self.assertEqual(len(result['unpaired_creates']), 1)

    def test_constructor_without_destructor_is_unpaired_not_leak(self):
        events = [self._ev("PlayerBase::PlayerBase()", "9")]
        result = self.parser.get_lifecycle_pairs(events)
        self.assertEqual(len(result['unpaired_creates']), 1)
        self.assertNotIn('leak', result)


class TestClassificationRules(unittest.TestCase):
    """F4, F5, F6: narrow Error, add Exception, priority-based Debug."""

    def setUp(self):
        self.parser = EventParser()

    def _type(self, text, priority=None):
        fields = {'pid': '1', 'tid': '2', 'priority': priority, 'tag': 'T'}
        return self.parser.parse_line(text, None, None, fields)[0].event_type

    def test_egl_success_is_not_error_by_text(self):
        line = "Failed to initialize 101010-2 format, error = EGL_SUCCESS"
        self.assertNotEqual(self._type(line), EventType.ERROR_LOG)

    def test_nlmsg_error_zero_is_not_error_by_text(self):
        line = "Received NLMSG_ERROR with error 0 for message GenericNetlinkMsg"
        self.assertNotEqual(self._type(line), EventType.ERROR_LOG)

    def test_splash_screen_exception_text_is_not_error(self):
        line = "SplashScreen checking exception for package com.PigeonGames.Phigros"
        self.assertNotEqual(self._type(line), EventType.ERROR_LOG)

    def test_error_priority_wins_with_threadtime(self):
        self.assertEqual(self._type("something broke", priority='E'), EventType.ERROR_LOG)

    def test_info_priority_not_error_even_with_word(self):
        self.assertNotEqual(self._type("ERROR text in info", priority='I'), EventType.ERROR_LOG)

    def test_security_exception_classified(self):
        line = "java.lang.SecurityException: getDataNetworkTypeForSubscriber"
        self.assertEqual(self._type(line), EventType.EXCEPTION_LOG)

    def test_plain_word_exception_not_classified_by_lowercase(self):
        self.assertNotEqual(self._type("no exception here"), EventType.EXCEPTION_LOG)

    def test_debug_priority_is_authoritative(self):
        # Legacy text "Debug" in the message must not win over priority 'I'
        self.assertNotEqual(self._type("Debug mode toggled", priority='I'), EventType.DEBUG_LOG)
        self.assertEqual(self._type("anything", priority='D'), EventType.DEBUG_LOG)


class TestDeviceInfo(unittest.TestCase):
    """F7: device info is read per property and failures are recorded."""

    def test_failure_is_recorded_not_guessed(self):
        monitor = LogcatMonitor()
        with mock.patch('logcat_monitor.subprocess.run', side_effect=OSError("no adb")):
            info = monitor.get_device_info("emu-1")
        self.assertIsNone(info['model'])
        self.assertIsNone(info['android_version'])
        self.assertEqual(len(info['errors']), 2)

    def test_success_is_recorded(self):
        monitor = LogcatMonitor()
        fake = mock.Mock(returncode=0, stdout="Pixel 6\n")
        with mock.patch('logcat_monitor.subprocess.run', return_value=fake):
            info = monitor.get_device_info("emu-1")
        self.assertEqual(info['model'], "Pixel 6")
        self.assertEqual(info['errors'], [])


class TestRegressionOnPhase1Data(unittest.TestCase):
    """Read-only regression on existing diags/1211202605 raw log."""

    RAW = os.path.join(PROJECT_DIR, 'diags', '1211202605', 'raw_logs.txt')

    def test_raw_log_still_readable_and_unchanged_size(self):
        if not os.path.exists(self.RAW):
            self.skipTest("phase 1 raw log not present")
        parser = EventParser()
        counts = {}
        with open(self.RAW, encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.rstrip('\n')
                if not line.startswith('['):
                    continue
                body = line[1:-1] if line.endswith(']') else line[1:]
                ev = parser.parse_line(body, None, None, None)[0]
                counts[ev.event_type] = counts.get(ev.event_type, 0) + 1
        # Old process-format data has no PID/TID; lifecycle counts must come
        # from the parser's text matches, not from numeric guesses.
        self.assertGreater(sum(counts.values()), 0)
        # F4 regression: 'error 0' / EGL_SUCCESS / SplashScreen lines must not
        # be ERROR_LOG. The one genuine error ('Error adding epoll events') must
        # still be classified, so the count is exactly 1 for this log.
        self.assertEqual(counts.get(EventType.ERROR_LOG, 0), 1)
        # F5 regression: SecurityException must now be classified
        self.assertGreater(counts.get(EventType.EXCEPTION_LOG, 0), 0)


if __name__ == '__main__':
    unittest.main()
