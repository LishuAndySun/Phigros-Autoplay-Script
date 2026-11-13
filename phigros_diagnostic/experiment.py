"""Phigros Diagnostic Tool - Experiment Module.

Manages experiment sessions, manual marks, and data organization
for multiple independent experiments.
"""

import json
import os
from datetime import datetime, timezone


class ExperimentSession:
    """Represents a single experiment session with marks and events."""
    
    def __init__(self, session_id=None):
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.created_at = datetime.now(timezone.utc)
        self.description = ""
        
        # Manual marks added by user
        self.manual_marks = []
        
        # Parsed events (reference to what parser collected)
        self.parsed_events = []
        
        # Metadata
        self.device_name = ""
        self.device_info = {}
        self.pid_filter = ""
        self.notes = ""
    
    def add_manual_mark(self, mark_data):
        """Add a manually marked experiment event.
        
        Args:
            mark_data: dict with keys: type, notes, timestamp, id
        """
        mark_data['session_id'] = self.session_id
        self.manual_marks.append(mark_data)
    
    def add_parsed_events(self, events):
        """Add parsed events from logcat.
        
        Args:
            events: List of ParsedEvent objects
        """
        self.parsed_events.extend(events)
    
    def to_dict(self):
        """Convert session to dictionary for serialization."""
        return {
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat(),
            'description': self.description,
            'device_name': self.device_name,
            'device_info': self.device_info,
            'pid_filter': self.pid_filter,
            'notes': self.notes,
            'manual_marks': self.manual_marks,
            'parsed_event_count': len(self.parsed_events),
            'manual_mark_count': len(self.manual_marks)
        }
    
    def get_timeline(self):
        """Get combined timeline of manual marks and key parsed events.
        
        Returns:
            list: Combined events sorted by receive_time
        """
        timeline = []
        
        # Add manual marks
        for mark in self.manual_marks:
            try:
                ts = datetime.fromisoformat(mark['timestamp'])
            except (ValueError, KeyError):
                ts = datetime.now(timezone.utc)
            
            timeline.append({
                'type': 'manual',
                'label': f"[{mark.get('type', 'Unknown')}]",
                'notes': mark.get('notes', ''),
                'timestamp': ts,
                'receive_time': ts
            })
        
        # Add key parsed events (PlayerBase/TrackPlayerBase lifecycle)
        from event_parser import EventType
        
        for event in self.parsed_events:
            if event.event_type in (
                EventType.PLAYER_BASE_CREATED,
                EventType.PLAYER_BASE_DESTROYED,
                EventType.TRACK_PLAYER_BASE_CREATED,
                EventType.TRACK_PLAYER_BASE_DESTROYED
            ):
                timeline.append({
                    'type': 'parsed',
                    'label': event.event_type.value,
                    'notes': '',
                    'timestamp': event.timestamp,
                    'receive_time': event.receive_time
                })
        
        # Sort by receive time
        timeline.sort(key=lambda x: x['receive_time'] or datetime.min.replace(tzinfo=timezone.utc))
        
        return timeline


class ExperimentManager:
    """Manages multiple experiment sessions and their data."""
    
    def __init__(self):
        self.sessions = {}  # session_id -> ExperimentSession
        self.current_session = None
        self.data_dir = None
    
    def create_session(self, description=""):
        """Create a new experiment session.
        
        Args:
            description: Optional description for the session
            
        Returns:
            ExperimentSession: The newly created session
        """
        session = ExperimentSession()
        session.description = description
        self.sessions[session.session_id] = session
        self.current_session = session
        return session
    
    def get_current_session(self):
        """Get the current active session.
        
        Returns:
            ExperimentSession or None
        """
        return self.current_session
    
    def switch_session(self, session_id):
        """Switch to a different session.
        
        Args:
            session_id: ID of the session to switch to
            
        Returns:
            ExperimentSession or None
        """
        if session_id in self.sessions:
            self.current_session = self.sessions[session_id]
            return self.current_session
        return None
    
    def get_all_sessions(self):
        """Get all sessions.
        
        Returns:
            dict: {session_id: ExperimentSession}
        """
        return self.sessions
    
    def delete_session(self, session_id):
        """Delete a session.
        
        Args:
            session_id: ID of session to delete
            
        Returns:
            bool: True if deleted successfully
        """
        if session_id in self.sessions and session_id != (self.current_session.session_id if self.current_session else None):
            del self.sessions[session_id]
            return True
        return False
    
    def set_data_dir(self, data_dir):
        """Set the directory for storing experiment data.
        
        Args:
            data_dir: Path to data directory
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
    
    def save_sessions_to_json(self, filepath=None):
        """Save all sessions to a JSON file.
        
        Args:
            filepath: Path to save to. If None, uses default location.
            
        Returns:
            str: Path where data was saved
        """
        if not self.data_dir:
            self.data_dir = os.path.join(os.getcwd(), "experiment_data")
        os.makedirs(self.data_dir, exist_ok=True)
        
        if not filepath:
            filepath = os.path.join(self.data_dir, "sessions.json")
        
        data = {
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'total_sessions': len(self.sessions),
            'sessions': [session.to_dict() for session in self.sessions.values()]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def load_sessions_from_json(self, filepath):
        """Load sessions from a JSON file.
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            int: Number of sessions loaded
        """
        if not os.path.exists(filepath):
            return 0
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        count = 0
        for session_data in data.get('sessions', []):
            session = ExperimentSession(session_data.get('session_id'))
            session.description = session_data.get('description', '')
            session.device_name = session_data.get('device_name', '')
            session.device_info = session_data.get('device_info', {})
            session.pid_filter = session_data.get('pid_filter', '')
            session.notes = session_data.get('notes', '')
            session.manual_marks = session_data.get('manual_marks', [])
            # Note: parsed_events are not persisted to keep files small
            self.sessions[session.session_id] = session
            count += 1
        
        return count
