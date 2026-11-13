"""Phigros Diagnostic Tool - Event Parser Module.

Parses raw logcat lines into structured events for PlayerBase,
TrackPlayerBase, and other Phigros lifecycle markers.
"""

import re
from datetime import datetime
from enum import Enum


class EventType(Enum):
    """Types of events that can be parsed from logs."""
    PLAYER_BASE_CREATED = "PlayerBase::PlayerBase()"
    PLAYER_BASE_DESTROYED = "PlayerBase::~PlayerBase()"
    TRACK_PLAYER_BASE_CREATED = "TrackPlayerBase::TrackPlayerBase()"
    TRACK_PLAYER_BASE_DESTROYED = "TrackPlayerBase::~TrackPlayerBase()"
    CHART_NOTE = "ChartNote"
    BPM_CHANGE = "BPM"
    OFFSET = "offset"
    HP_DISPLAY = "HPDisplay"
    CLICK_CONTROL = "ClickControl"
    DRAG_CONTROL = "DragControl"
    FLICK_CONTROL = "FlickControl"
    HOLD_CONTROL = "HoldControl"
    AUDIO_SOURCE = "AudioSource"
    MULTI_LANGUAGE_TEXT = "MultiLanguageText"
    UNITY_APPLICATION_INFO = "ApplicationInfo"
    DEBUG_LOG = "Debug"
    WARNING_LOG = "Warning"
    ERROR_LOG = "Error"
    EXCEPTION_LOG = "Exception"
    GC_WARNING = "GC"
    UNKNOWN = "Unknown"


class ParsedEvent:
    """Represents a single parsed event from a log line."""
    
    def __init__(self, event_type, timestamp, receive_time, raw_line, details=None,
                 pid=None, tid=None, priority=None, tag=None):
        self.event_type = event_type
        # Device-side timestamp: naive datetime, NOT UTC (device clock unknown)
        self.timestamp = timestamp
        self.receive_time = receive_time  # When received by tool (tz-aware UTC)
        self.raw_line = raw_line
        self.details = details or {}
        # Fields from logcat threadtime; None when unavailable (never guessed)
        self.pid = pid
        self.tid = tid
        self.priority = priority
        self.tag = tag
    
    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'receive_time': self.receive_time.isoformat() if self.receive_time else None,
            'raw_line': self.raw_line,
            'details': self.details,
            'pid': self.pid,
            'tid': self.tid,
            'priority': self.priority,
            'tag': self.tag,
        }


class EventParser:
    """Parses raw logcat lines into structured events.
    
    Uses regex patterns to identify Phigros-specific events
    from Unity/Android logcat output.
    """
    
    # Patterns for key Phigros classes
    PATTERNS = [
        (EventType.PLAYER_BASE_CREATED, r'PlayerBase::PlayerBase\(\)'),
        (EventType.PLAYER_BASE_DESTROYED, r'PlayerBase::~PlayerBase\(\)'),
        (EventType.TRACK_PLAYER_BASE_CREATED, r'TrackPlayerBase::TrackPlayerBase\(\)'),
        (EventType.TRACK_PLAYER_BASE_DESTROYED, r'TrackPlayerBase::~TrackPlayerBase\(\)'),
        (EventType.CHART_NOTE, r'ChartNote'),
        (EventType.BPM_CHANGE, r'\bBPM\b'),
        (EventType.OFFSET, r'\boffset\b'),
        (EventType.HP_DISPLAY, r'HPDisplay'),
        (EventType.CLICK_CONTROL, r'ClickControl'),
        (EventType.DRAG_CONTROL, r'DragControl'),
        (EventType.FLICK_CONTROL, r'FlickControl'),
        (EventType.HOLD_CONTROL, r'HoldControl'),
        (EventType.AUDIO_SOURCE, r'AudioSource'),
        (EventType.MULTI_LANGUAGE_TEXT, r'MultiLanguageText'),
        (EventType.UNITY_APPLICATION_INFO, r'ApplicationInfo'),
        # Legacy text fallback only (used when no threadtime priority is known).
        (EventType.DEBUG_LOG, r'\bDebug\b'),
        (EventType.WARNING_LOG, r'\bWarning\b|\bWARN\b'),
        (EventType.ERROR_LOG, r'\bError\b|\bERROR\b'),
        (EventType.GC_WARNING, r'\bGC\b.*\bwarning\b|\bGC\b.*\bgc\b'),
    ]

    # Java/Unity exception class names, e.g. java.lang.SecurityException.
    # Case-sensitive on purpose: ordinary text like "exception" must not match.
    EXCEPTION_CLASS_PATTERN = r'\b[A-Za-z_][\w.]*(?:Exception|Error)\b'

    # Threadtime priority letters that mean a real error (E/F/A = error/fatal/assert)
    ERROR_PRIORITIES = ('E', 'F', 'A')
    # Messages that contain the word "error" but are not failures
    NON_FAILURE_PATTERNS = [
        r'error\s*=\s*EGL_SUCCESS',
        r'with error 0\b',
        r'_SUCCESS\b',
    ]
    
    # Priority order for matching (first match wins for ambiguous cases)
    PRIORITY_ORDER = [
        EventType.PLAYER_BASE_CREATED,
        EventType.PLAYER_BASE_DESTROYED,
        EventType.TRACK_PLAYER_BASE_CREATED,
        EventType.TRACK_PLAYER_BASE_DESTROYED,
        EventType.CHART_NOTE,
        EventType.UNITY_APPLICATION_INFO,
        EventType.ERROR_LOG,
        EventType.EXCEPTION_LOG,
        EventType.WARNING_LOG,
        EventType.GC_WARNING,
        EventType.BPM_CHANGE,
        EventType.OFFSET,
        EventType.HP_DISPLAY,
        EventType.CLICK_CONTROL,
        EventType.DRAG_CONTROL,
        EventType.FLICK_CONTROL,
        EventType.HOLD_CONTROL,
        EventType.AUDIO_SOURCE,
        EventType.MULTI_LANGUAGE_TEXT,
        EventType.DEBUG_LOG,
        EventType.UNKNOWN,
    ]
    
    def parse_line(self, raw_line, log_time=None, receive_time=None, fields=None):
        """Parse a single logcat line and return matched event(s).
        
        Args:
            raw_line: The complete log line string
            log_time: Device timestamp (naive datetime, not UTC) or None
            receive_time: When this line was received by the tool
            fields: Optional dict from threadtime parsing with keys
                pid, tid, priority, tag (None when unavailable)
            
        Returns:
            list: List of ParsedEvent objects (may be empty if no match)
        """
        if not raw_line:
            return []
        
        fields = fields or {}
        pid = fields.get('pid')
        tid = fields.get('tid')
        priority = fields.get('priority')
        tag = fields.get('tag')
        receive_time = receive_time or datetime.now()
        
        events = []
        message = raw_line
        
        # Lifecycle and Phigros markers first (most important)
        for event_type in self.PRIORITY_ORDER:
            if event_type == EventType.UNKNOWN:
                continue
            if not self._matches(event_type, message, priority):
                continue
            details = self._extract_details(event_type, raw_line)
            events.append(ParsedEvent(
                event_type=event_type,
                timestamp=log_time,
                receive_time=receive_time,
                raw_line=raw_line,
                details=details,
                pid=pid, tid=tid, priority=priority, tag=tag,
            ))
            break  # First match wins
        
        if not events:
            events.append(ParsedEvent(
                event_type=EventType.UNKNOWN,
                timestamp=log_time,
                receive_time=receive_time,
                raw_line=raw_line,
                details={},
                pid=pid, tid=tid, priority=priority, tag=tag,
            ))
        
        return events

    def _matches(self, event_type, message, priority):
        """Return True if the line belongs to event_type."""
        if event_type == EventType.ERROR_LOG:
            if priority is not None:
                # Trust logcat priority (E/F/A) over message text
                return priority in self.ERROR_PRIORITIES
            # Text fallback (no threadtime info): drop known non-failures
            if any(re.search(p, message, re.IGNORECASE) for p in self.NON_FAILURE_PATTERNS):
                return False
            return bool(re.search(r'\bError\b|\bERROR\b', message))
        
        if event_type == EventType.EXCEPTION_LOG:
            # Java/Unity exception class names (case-sensitive)
            if re.search(self.EXCEPTION_CLASS_PATTERN, message):
                return True
            return bool(re.search(r'\bException\b', message))
        
        if event_type == EventType.DEBUG_LOG:
            if priority is not None:
                return priority == 'D'
            return bool(re.search(r'\bDebug\b', message, re.IGNORECASE))
        
        if event_type == EventType.WARNING_LOG:
            if priority is not None:
                return priority == 'W'
            return bool(re.search(r'\bWarning\b|\bWARN\b', message, re.IGNORECASE))
        
        pattern = None
        for et, pat in self.PATTERNS:
            if et == event_type:
                pattern = pat
                break
        return bool(pattern and re.search(pattern, message, re.IGNORECASE))
    
    def _extract_details(self, event_type, raw_line):
        """Extract additional details from a log line based on event type.
        
        Args:
            event_type: The matched event type
            raw_line: The original log line
            
        Returns:
            dict: Extracted details
        """
        details = {}
        
        if event_type in (EventType.PLAYER_BASE_CREATED, EventType.PLAYER_BASE_DESTROYED,
                          EventType.TRACK_PLAYER_BASE_CREATED, EventType.TRACK_PLAYER_BASE_DESTROYED):
            # PID/TID come from threadtime fields on ParsedEvent, never from
            # guessing numbers in the message text.
            # Try to extract any class name before the method
            class_match = re.search(r'([\w.]+)::', raw_line)
            if class_match:
                details['class_name'] = class_match.group(1)
        
        elif event_type == EventType.UNITY_APPLICATION_INFO:
            # Extract version info
            version_match = re.search(r'versionName=(\S+)', raw_line)
            if version_match:
                details['version_name'] = version_match.group(1)
            code_match = re.search(r'versionCode=(\S+)', raw_line)
            if code_match:
                details['version_code'] = code_match.group(1)
        
        elif event_type == EventType.CHART_NOTE:
            # Try to extract note-related data
            note_id = re.search(r'id[=:]\s*(\S+)', raw_line, re.IGNORECASE)
            if note_id:
                details['note_id'] = note_id.group(1)
        
        elif event_type == EventType.BPM_CHANGE:
            bpm_match = re.search(r'BPM[=:]\s*([\d.]+)', raw_line, re.IGNORECASE)
            if bpm_match:
                try:
                    details['bpm_value'] = float(bpm_match.group(1))
                except ValueError:
                    pass
        
        elif event_type == EventType.OFFSET:
            offset_match = re.search(r'offset[=:]\s*([-\d.]+)', raw_line, re.IGNORECASE)
            if offset_match:
                try:
                    details['offset_value'] = float(offset_match.group(1))
                except ValueError:
                    pass
        
        return details
    
    def get_event_summary(self, events):
        """Get a summary count of events by type.
        
        Args:
            events: List of ParsedEvent objects
            
        Returns:
            dict: {EventType: count}
        """
        summary = {}
        for event in events:
            key = event.event_type
            summary[key] = summary.get(key, 0) + 1
        return summary
    
    def get_lifecycle_pairs(self, events):
        """Group lifecycle events into create/destroy pairs, per PID.
        
        Pairing is done inside each PID so events from different processes
        are never mixed. Events without a PID are kept in a separate group
        (key None) and are never paired with PID-bearing events.
        
        Args:
            events: List of ParsedEvent objects (in arrival order)
            
        Returns:
            dict with keys:
              'player_bases': [(create, destroy)]
              'track_player_bases': [(create, destroy)]
              'unpaired_creates': [event] constructors with no later destructor
              'unpaired_destroys': [event] destructors with no earlier constructor
        """
        create_types = {
            EventType.PLAYER_BASE_CREATED: 'player_bases',
            EventType.TRACK_PLAYER_BASE_CREATED: 'track_player_bases',
        }
        destroy_types = {
            EventType.PLAYER_BASE_DESTROYED: 'player_bases',
            EventType.TRACK_PLAYER_BASE_DESTROYED: 'track_player_bases',
        }
        
        result = {
            'player_bases': [],
            'track_player_bases': [],
            'unpaired_creates': [],
            'unpaired_destroys': [],
        }
        
        # Pending constructors keyed by (group, pid)
        pending = {}
        
        for event in events:
            if event.event_type in create_types:
                group = create_types[event.event_type]
                pending.setdefault((group, event.pid), []).append(event)
            elif event.event_type in destroy_types:
                group = destroy_types[event.event_type]
                queue = pending.get((group, event.pid))
                if queue:
                    create_event = queue.pop(0)
                    result[group].append((create_event, event))
                else:
                    result['unpaired_destroys'].append(event)
        
        for (_group, _pid), queue in pending.items():
            result['unpaired_creates'].extend(queue)
        
        return result
