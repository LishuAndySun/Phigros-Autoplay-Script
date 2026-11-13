"""Phigros Diagnostic Tool - Report Exporter Module.

Exports experiment data to various formats: TXT (raw logs),
JSON (structured events), CSV (statistics), and formatted reports.
"""

import csv
import json
import os
from datetime import datetime, timezone


class ReportExporter:
    """Exports diagnostic data to multiple file formats."""
    
    def __init__(self, experiment_manager):
        """Initialize exporter with experiment manager reference.
        
        Args:
            experiment_manager: ExperimentManager instance
        """
        self.experiment_manager = experiment_manager
    
    def export_raw_logs(self, filepath=None, session_id=None):
        """Export raw log lines to a TXT file.
        
        Args:
            filepath: Output file path. If None, auto-generates.
            session_id: Session to export. If None, exports current session.
            
        Returns:
            str: Path where data was saved
        """
        session = self._get_session(session_id)
        if not session:
            raise ValueError("No active session to export")
        
        if not filepath:
            filepath = self._generate_path("raw_logs", "txt")
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# Phigros Diagnostic Tool - Raw Logs\n")
            f.write(f"# Session: {session.session_id}\n")
            f.write(f"# Exported: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"# Device: {session.device_name}\n")
            f.write(f"# PID Filter: {session.pid_filter or 'None'}\n")
            f.write(f"# Total Events: {len(session.parsed_events)}\n")
            f.write(f"# Manual Marks: {len(session.manual_marks)}\n")
            f.write(f"\n{'='*80}\n\n")
            
            for event in session.parsed_events:
                f.write(f"[{event.raw_line}]\n")
        
        return filepath
    
    def export_events_json(self, filepath=None, session_id=None, include_raw=True):
        """Export parsed events to JSON format.
        
        Args:
            filepath: Output file path. If None, auto-generates.
            session_id: Session to export. If None, exports current session.
            include_raw: Whether to include raw log lines
            
        Returns:
            str: Path where data was saved
        """
        session = self._get_session(session_id)
        if not session:
            raise ValueError("No active session to export")
        
        if not filepath:
            filepath = self._generate_path("events", "json")
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        events_data = []
        for event in session.parsed_events:
            event_dict = event.to_dict()
            if not include_raw:
                event_dict.pop('raw_line', None)
            events_data.append(event_dict)
        
        report_data = {
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'session_id': session.session_id,
            'total_events': len(events_data),
            'events': events_data
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def export_statistics_csv(self, filepath=None, session_id=None):
        """Export event statistics to CSV format.
        
        Args:
            filepath: Output file path. If None, auto-generates.
            session_id: Session to export. If None, exports current session.
            
        Returns:
            str: Path where data was saved
        """
        from event_parser import EventParser
        
        session = self._get_session(session_id)
        if not session:
            raise ValueError("No active session to export")
        
        if not filepath:
            filepath = self._generate_path("statistics", "csv")
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        parser = EventParser()
        summary = parser.get_event_summary(session.parsed_events)
        lifecycle = parser.get_lifecycle_pairs(session.parsed_events)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Event type counts
            writer.writerow(['Event Type', 'Count'])
            for event_type, count in sorted(summary.items(), key=lambda x: -x[1]):
                writer.writerow([event_type.value, count])
            
            writer.writerow([])  # Blank row
            
            # Lifecycle pairs
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['PlayerBase Pairs (same PID)', len(lifecycle['player_bases'])])
            writer.writerow(['TrackPlayerBase Pairs (same PID)', len(lifecycle['track_player_bases'])])
            writer.writerow(['Unpaired Constructors', len(lifecycle['unpaired_creates'])])
            writer.writerow(['Unpaired Destructors', len(lifecycle['unpaired_destroys'])])
            
            # Intervals between TrackPlayerBase events
            writer.writerow([])  # Blank row
            writer.writerow(['Track Interval Analysis'])
            
            track_pairs = lifecycle['track_player_bases']
            if len(track_pairs) >= 2:
                intervals = []
                for i in range(1, len(track_pairs)):
                    prev_destroy = track_pairs[i-1][1].timestamp
                    curr_create = track_pairs[i][0].timestamp
                    if prev_destroy and curr_create:
                        delta = (curr_create - prev_destroy).total_seconds()
                        intervals.append(delta)
                
                if intervals:
                    writer.writerow(['Average Interval (s)', f"{sum(intervals)/len(intervals):.2f}"])
                    writer.writerow(['Min Interval (s)', f"{min(intervals):.2f}"])
                    writer.writerow(['Max Interval (s)', f"{max(intervals):.2f}"])
                    writer.writerow(['Sample Count', len(intervals)])
        
        return filepath
    
    def export_formatted_report(self, filepath=None, session_id=None):
        """Export a comprehensive formatted text report.
        
        Args:
            filepath: Output file path. If None, auto-generates.
            session_id: Session to export. If None, exports current session.
            
        Returns:
            str: Path where data was saved
        """
        from event_parser import EventParser
        
        session = self._get_session(session_id)
        if not session:
            raise ValueError("No active session to export")
        
        if not filepath:
            filepath = self._generate_path("report", "txt")
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        parser = EventParser()
        summary = parser.get_event_summary(session.parsed_events)
        lifecycle = parser.get_lifecycle_pairs(session.parsed_events)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("PHIGROS DIAGNOSTIC TOOL - EXPERIMENT REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            # Session info
            f.write("SESSION INFORMATION\n")
            f.write("-" * 40 + "\n")
            f.write(f"Session ID:       {session.session_id}\n")
            f.write(f"Created:          {session.created_at.isoformat()}\n")
            f.write(f"Description:      {session.description}\n")
            f.write(f"Device:           {session.device_name}\n")
            info = session.device_info or {}
            f.write(f"Device Model:     {info.get('model') or 'unavailable'}\n")
            f.write(f"Android Version:  {info.get('android_version') or 'unavailable'}\n")
            f.write(f"PID Filter:       {session.pid_filter or 'None'}\n")
            f.write(f"Total Events:     {len(session.parsed_events)}\n")
            f.write(f"Manual Marks:     {len(session.manual_marks)}\n")
            f.write("\n")
            
            # Event summary
            f.write("EVENT SUMMARY\n")
            f.write("-" * 40 + "\n")
            total = sum(summary.values())
            for event_type, count in sorted(summary.items(), key=lambda x: -x[1]):
                pct = (count / total * 100) if total > 0 else 0
                bar = '#' * int(pct / 2)
                f.write(f"{event_type.value:<35} {count:>6}  ({pct:>5.1f}%) {bar}\n")
            f.write(f"{'TOTAL':<35} {total:>6}\n")
            f.write("\n")
            
            # Lifecycle analysis
            f.write("LIFECYCLE ANALYSIS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Matched PlayerBase pairs (same PID):           {len(lifecycle['player_bases'])}\n")
            f.write(f"Matched TrackPlayerBase pairs (same PID):     {len(lifecycle['track_player_bases'])}\n")
            f.write(f"Constructors without observed destructor:     {len(lifecycle['unpaired_creates'])}\n")
            f.write(f"Destructors without observed constructor:     {len(lifecycle['unpaired_destroys'])}\n")
            f.write("Note: unpaired counts are observations, not leak claims.\n")
            
            # Track intervals
            track_pairs = lifecycle['track_player_bases']
            if len(track_pairs) >= 2:
                intervals = []
                for i in range(1, len(track_pairs)):
                    prev_destroy = track_pairs[i-1][1].timestamp
                    curr_create = track_pairs[i][0].timestamp
                    if prev_destroy and curr_create:
                        delta = (curr_create - prev_destroy).total_seconds()
                        intervals.append(delta)
                
                if intervals:
                    f.write(f"\nTrack Interval Statistics:\n")
                    f.write(f"  Average:  {sum(intervals)/len(intervals):.2f}s\n")
                    f.write(f"  Minimum:  {min(intervals):.2f}s\n")
                    f.write(f"  Maximum:  {max(intervals):.2f}s\n")
                    f.write(f"  Samples:  {len(intervals)}\n")
            f.write("\n")
            
            # Manual marks
            if session.manual_marks:
                f.write("MANUAL EXPERIMENT MARKS\n")
                f.write("-" * 40 + "\n")
                for i, mark in enumerate(session.manual_marks, 1):
                    f.write(f"{i}. [{mark.get('type', 'Unknown')}] at {mark.get('timestamp', 'N/A')}\n")
                    if mark.get('notes'):
                        f.write(f"   Notes: {mark['notes']}\n")
                f.write("\n")
            
            # Key observations
            f.write("KEY OBSERVATIONS\n")
            f.write("-" * 40 + "\n")
            
            # Check for PlayerBase/TrackPlayerBase timing relationship
            pb_creates = [e for e in session.parsed_events 
                         if e.event_type.value == 'PlayerBase::PlayerBase()']
            tp_creates = [e for e in session.parsed_events 
                         if e.event_type.value == 'TrackPlayerBase::TrackPlayerBase()']
            
            if pb_creates and tp_creates:
                f.write(f"- Found {len(pb_creates)} PlayerBase creation(s)\n")
                f.write(f"- Found {len(tp_creates)} TrackPlayerBase creation(s)\n")
                f.write(f"- NOTE: PlayerBase construction time is NOT assumed to be music playback start\n")
                f.write(f"- NOTE: Log timestamps are distinguished from log reception times\n")
            else:
                f.write("- No PlayerBase or TrackPlayerBase events found in this session\n")
                f.write("- Ensure ADB logcat is capturing Phigros process logs\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"Report generated at: {datetime.now(timezone.utc).isoformat()}\n")
            f.write("=" * 80 + "\n")
        
        return filepath
    
    def export_all(self, output_dir=None, session_id=None):
        """Export all formats to the same directory.
        
        Args:
            output_dir: Directory for exports. If None, uses default.
            session_id: Session to export. If None, exports current session.
            
        Returns:
            dict: {format: filepath} mapping of exported files
        """
        if not output_dir:
            output_dir = os.path.join(
                os.getcwd(), 
                "experiment_data", 
                session_id or (self.experiment_manager.current_session.session_id if self.experiment_manager.current_session else "default")
            )
        
        os.makedirs(output_dir, exist_ok=True)
        
        results = {}
        try:
            results['raw_logs'] = self.export_raw_logs(
                os.path.join(output_dir, "raw_logs.txt"), session_id
            )
        except Exception as e:
            print(f"Error exporting raw logs: {e}")
        
        try:
            results['events_json'] = self.export_events_json(
                os.path.join(output_dir, "events.json"), session_id
            )
        except Exception as e:
            print(f"Error exporting events JSON: {e}")
        
        try:
            results['statistics_csv'] = self.export_statistics_csv(
                os.path.join(output_dir, "statistics.csv"), session_id
            )
        except Exception as e:
            print(f"Error exporting statistics CSV: {e}")
        
        try:
            results['report'] = self.export_formatted_report(
                os.path.join(output_dir, "report.txt"), session_id
            )
        except Exception as e:
            print(f"Error exporting report: {e}")
        
        return results
    
    def _get_session(self, session_id=None):
        """Get a session by ID or current session.
        
        Args:
            session_id: Optional session ID
            
        Returns:
            ExperimentSession or None
        """
        if session_id:
            return self.experiment_manager.sessions.get(session_id)
        return self.experiment_manager.current_session
    
    def _generate_path(self, prefix, extension):
        """Auto-generate a file path with timestamp.
        
        Args:
            prefix: File name prefix
            extension: File extension (without dot)
            
        Returns:
            str: Generated file path
        """
        if not self.experiment_manager.data_dir:
            self.experiment_manager.data_dir = os.path.join(os.getcwd(), "experiment_data")
        
        os.makedirs(self.experiment_manager.data_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{prefix}_{timestamp}.{extension}"
        return os.path.join(self.experiment_manager.data_dir, filename)
