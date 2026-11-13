"""Phigros Diagnostic Tool - Main Window UI Module.

Integrates logcat monitoring, event parsing, timeline display,
experiment marking, and report export into a single PySide6 application.
"""

import os
import threading
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabWidget, QPushButton, QLabel, QComboBox, QStatusBar,
    QFileDialog, QMessageBox, QGroupBox, QFormLayout, QTextEdit,
    QCheckBox, QSpinBox, QFrame, QSystemTrayIcon, QToolTip
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QIcon, QAction, QColor

from logcat_monitor import LogcatMonitor
from event_parser import EventParser, EventType
from timeline import EventTableModel, TimelineView, ExperimentMarkWidget, StatisticsWidget, FilterBar
from experiment import ExperimentManager, ExperimentSession
from report_exporter import ReportExporter


class MainWindow(QMainWindow):
    """Main application window for Phigros Diagnostic Tool."""

    # Emitted from the logcat reader thread; delivered to the GUI thread via queued connection
    log_line_received = Signal(str, object, object, object)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phigros Diagnostic Tool v0.1")
        self.setMinimumSize(1200, 800)
        
        # Core components
        self.monitor = LogcatMonitor()
        self.parser = EventParser()
        self.experiment_mgr = ExperimentManager()
        self.exporter = None  # Created when needed
        
        # Data model
        self.event_model = EventTableModel()
        self.all_events = []  # For persistence across sessions
        
        # Shared stats timer (avoid creating new timers per log line)
        self._stats_timer = QTimer()
        self._stats_timer.setSingleShot(True)
        self._stats_timer.timeout.connect(self.update_statistics)

        # Queued connection: slot runs on the GUI thread
        self.log_line_received.connect(self.on_log_line_received, Qt.QueuedConnection)
        
        # Setup UI
        self.setup_ui()
        self.update_exporter()
        self.check_adb_connection()
        
        # Auto-connect if device available (disabled to avoid conflicts)
        # self.auto_connect()
    
    def setup_ui(self):
        """Build the complete UI layout."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Status bar must be created BEFORE any component might call show_status()
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Top control bar
        main_layout.addWidget(self.create_control_bar())
        
        # Main content area with tabs
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Tab 1: Timeline
        self.tab_widget.addTab(self.create_timeline_tab(), "Timeline")
        
        # Tab 2: Experiment Marks
        self.tab_widget.addTab(self.create_experiment_tab(), "Experiment Marks")
        
        # Tab 3: Statistics
        self.tab_widget.addTab(self.create_statistics_tab(), "Statistics")
        
        # Tab 4: Raw Logs
        self.tab_widget.addTab(self.create_raw_logs_tab(), "Raw Logs")
        
        # Remove the old status bar message since we now have one from __init__
        # (it was set before status_bar existed, so ignore that earlier call)
    
    def create_control_bar(self):
        """Create the top control bar with connection and monitoring controls."""
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.StyledPanel)
        layout = QHBoxLayout(control_frame)
        
        # Left section: Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QFormLayout()
        
        self.device_combo = QComboBox()
        self.refresh_devices()
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        self.refresh_btn = QPushButton("Refresh Devices")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        
        conn_layout.addRow("Device:", self.device_combo)
        conn_layout.addRow(self.connect_btn)
        conn_layout.addRow(self.refresh_btn)
        conn_group.setLayout(conn_layout)
        
        # Middle section: PID filter
        pid_group = QGroupBox("PID Filter")
        pid_layout = QFormLayout()
        
        self.pid_input = QSpinBox()
        self.pid_input.setRange(0, 99999)
        self.pid_input.valueChanged.connect(self.on_pid_changed)
        
        pid_layout.addRow("PID:", self.pid_input)
        pid_group.setLayout(pid_layout)
        
        # Right section: Session controls
        session_group = QGroupBox("Session")
        session_layout = QFormLayout()
        
        self.session_combo = QComboBox()
        self.update_session_combo()
        
        self.new_session_btn = QPushButton("New Session")
        self.new_session_btn.clicked.connect(self.create_new_session)
        
        self.export_btn = QPushButton("Export All")
        self.export_btn.clicked.connect(self.export_all_data)
        
        session_layout.addRow("Session:", self.session_combo)
        session_layout.addRow(self.new_session_btn)
        session_layout.addRow(self.export_btn)
        session_group.setLayout(session_layout)
        
        # Add groups to main layout
        layout.addWidget(conn_group)
        layout.addWidget(pid_group)
        layout.addWidget(session_group)
        layout.addStretch()
        
        return control_frame
    
    def create_timeline_tab(self):
        """Create the timeline tab with filter bar and event table."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Filter bar
        self.filter_bar = FilterBar(list(EventType))
        self.filter_bar.filter_changed.connect(self.on_filter_changed)
        layout.addWidget(self.filter_bar)
        
        # Event table
        self.timeline_view = TimelineView()
        self.timeline_view.populate_from_model(self.event_model)
        layout.addWidget(self.timeline_view)
        
        # Event count label
        self.event_count_label = QLabel(f"Events: {self.event_model.event_count}")
        layout.addWidget(self.event_count_label)
        
        return widget
    
    def create_experiment_tab(self):
        """Create the experiment marks tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Manual mark widget
        self.experiment_mark = ExperimentMarkWidget()
        self.experiment_mark.mark_added.connect(self.on_manual_mark_added)
        layout.addWidget(self.experiment_mark)
        
        return widget
    
    def create_statistics_tab(self):
        """Create the statistics tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.statistics = StatisticsWidget()
        layout.addWidget(self.statistics)
        
        return widget
    
    def create_raw_logs_tab(self):
        """Create the raw logs display tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.raw_log_display = QTextEdit()
        self.raw_log_display.setReadOnly(True)
        self.raw_log_display.setFontFamily("monospace")
        self.raw_log_display.setMaximumHeight(300)
        layout.addWidget(self.raw_log_display)
        
        # Clear button
        clear_btn = QPushButton("Clear Raw Logs")
        clear_btn.clicked.connect(self.raw_log_display.clear)
        layout.addWidget(clear_btn)
        
        return widget
    
    def on_log_line_received(self, raw_line, log_time, receive_time, fields=None):
        """Handle a logcat line on the GUI thread (queued from the reader thread)."""
        events = self.parser.parse_line(raw_line, log_time, receive_time, fields)
        if not events:
            return
        
        self.timeline_view.wrapper.append_events(events)
        
        session = self.experiment_mgr.get_current_session()
        if session:
            session.add_parsed_events(events)
        
        self.event_count_label.setText(f"Events: {self.event_model.event_count}")
        
        # Limit raw log display to prevent memory growth
        self.raw_log_display.append(f"[{events[0].receive_time.strftime('%H:%M:%S.%f')[:-3]}] {events[0].raw_line}")
        if self.raw_log_display.document().blockCount() > 1000:
            # Simple approach: just clear occasionally
            if self.raw_log_display.document().blockCount() > 2000:
                self.raw_log_display.clear()
        
        # Update statistics periodically (use shared timer to avoid pileup)
        if not self._stats_timer.isActive():
            self._stats_timer.start(500)
    
    def update_statistics(self):
        """Update the statistics display."""
        summary = self.parser.get_event_summary(self.event_model.events)
        lifecycle = self.parser.get_lifecycle_pairs(self.event_model.events)
        self.statistics.update_stats(summary, lifecycle)
    
    def toggle_connection(self):
        """Toggle between connect and disconnect states."""
        if self.monitor.is_running:
            self.disconnect()
        else:
            self.connect_to_device()
    
    def connect_to_device(self):
        """Connect to the selected ADB device."""
        device_index = self.device_combo.currentIndex()
        if device_index < 0:
            self.show_status("No device selected", "error")
            return
        
        device_id = self.device_combo.itemData(device_index)
        self.monitor.set_device(device_id)
        
        try:
            # Register before start so no lines are dropped
            self.monitor.add_callback(self.log_line_received.emit)
            self.monitor.start()
            
            session = self.experiment_mgr.get_current_session()
            if session:
                info = self.monitor.get_device_info(device_id)
                session.device_name = device_id
                session.device_info = info
            
            self.connect_btn.setText("Disconnect")
            self.device_combo.setEnabled(False)
            self.show_status(f"Connected to {device_id}", "success")
        except Exception as e:
            self.show_status(f"Connection failed: {e}", "error")
    
    def disconnect(self):
        """Disconnect from ADB device."""
        self.monitor.stop()
        
        self.connect_btn.setText("Connect")
        self.device_combo.setEnabled(True)
        self.show_status("Disconnected", "info")
    
    def refresh_devices(self):
        """Refresh the list of connected ADB devices."""
        self.device_combo.clear()
        
        result = self.monitor.check_adb_connection()
        if result['success']:
            for device_id, status in result['devices']:
                self.device_combo.addItem(f"{device_id} ({status})", device_id)
            self.show_status(result['message'], "success")
        else:
            self.show_status(result['message'], "error")
            if not result['devices']:
                # Show empty combo with hint
                self.device_combo.addItem("No devices found", "")
    
    def check_adb_connection(self):
        """Check ADB connection status on startup."""
        result = self.monitor.check_adb_connection()
        if not result['success']:
            QMessageBox.warning(
                self, 
                "ADB Connection Warning",
                f"Could not connect to ADB:\n\n{result['message']}\n\n"
                "Please ensure:\n"
                "1. Android SDK Platform-Tools is installed\n"
                "2. An Android device is connected and visible to ADB\n"
                "3. USB debugging is enabled"
            )
    
    def auto_connect(self):
        """Automatically connect if exactly one device is available."""
        devices = self.monitor.get_device_list()
        connected = [d for d in devices if d[1] == 'device']
        
        if len(connected) == 1:
            device_id = connected[0][0]
            self.device_combo.setCurrentIndex(0)
            QTimer.singleShot(1000, lambda: self.connect_to_device())
    
    def on_pid_changed(self, value):
        """Handle PID filter changes."""
        if value > 0:
            self.monitor.pid_filter = str(value)
            self.show_status(f"PID filter set to {value}", "info")
        else:
            self.monitor.pid_filter = None
            self.show_status("PID filter cleared", "info")
    
    def on_filter_changed(self, active_types):
        """Handle filter changes from the filter bar."""
        # Note: Full filter implementation would require updating the proxy model
        # For now, this is a placeholder for future filtering
        pass
    
    def create_new_session(self):
        """Create a new experiment session."""
        from PySide6.QtWidgets import QInputDialog
        
        description, ok = QInputDialog.getText(
            self, "New Session", "Enter session description:"
        )
        if ok:
            session = self.experiment_mgr.create_session(description)
            self.update_session_combo()
            self.update_exporter()
            self.show_status(f"Created session: {session.session_id}", "success")
    
    def update_session_combo(self):
        """Update the session combo box with all sessions."""
        self.session_combo.clear()
        
        for sid, session in self.experiment_mgr.get_all_sessions().items():
            display = f"{sid[:12]}... ({len(session.manual_marks)} marks)"
            if session.description:
                display += f" - {session.description}"
            self.session_combo.addItem(display, sid)
        
        # Switch to current session if it exists
        current = self.experiment_mgr.get_current_session()
        if current:
            for i, sid in enumerate(self.experiment_mgr.sessions.keys()):
                if sid == current.session_id:
                    self.session_combo.setCurrentIndex(i)
                    break
    
    def switch_session(self, session_id):
        """Switch to a different experiment session."""
        session = self.experiment_mgr.switch_session(session_id)
        if session:
            self.update_exporter()
            self.show_status(f"Switched to session: {session.session_id}", "info")
        else:
            self.show_status("Failed to switch session", "error")
    
    def update_exporter(self):
        """Recreate the exporter with current experiment manager."""
        self.exporter = ReportExporter(self.experiment_mgr)
    
    def on_manual_mark_added(self, mark_data):
        """Handle manual experiment mark addition."""
        session = self.experiment_mgr.get_current_session()
        if session:
            session.add_manual_mark(mark_data)
            self.show_status(f"Added mark: {mark_data['type']}", "success")
        
        # Update session combo to reflect new mark count
        self.update_session_combo()
    
    def export_all_data(self):
        """Export all data from current session."""
        session = self.experiment_mgr.get_current_session()
        if not session:
            QMessageBox.warning(self, "No Session", "Please create a session first.")
            return
        
        # Ask for output directory
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Export Directory"
        )
        
        if output_dir:
            try:
                results = self.exporter.export_all(output_dir)
                
                msg = QMessageBox(self)
                msg.setWindowTitle("Export Complete")
                msg.setText(f"Exported {len(results)} files to:\n{output_dir}")
                
                details = "\n".join(f"- {k}: {v}" for k, v in results.items())
                msg.setDetailedText(details)
                msg.exec()
                
                self.show_status("Export completed successfully", "success")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Export failed:\n{e}")
                self.show_status(f"Export failed: {e}", "error")
    
    def show_status(self, message, level="info"):
        """Show a status message with color coding."""
        if not hasattr(self, 'status_bar') or self.status_bar is None:
            return
        
        colors = {
            "success": "#4CAF50",
            "error": "#F44336",
            "info": "#2196F3"
        }
        
        color = colors.get(level, "#666666")
        self.status_bar.setStyleSheet(f"QStatusBar {{ color: {color}; }}")
        self.status_bar.showMessage(message)
        
        # Reset color after delay
        QTimer.singleShot(3000, lambda: self.status_bar.setStyleSheet(""))
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Stop monitoring if running
        if self.monitor.is_running:
            self.monitor.stop()
        
        # Save current session data
        if self.experiment_mgr.current_session:
            reply = QMessageBox.question(
                self,
                "Save Data",
                "Do you want to save the current session data?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Yes:
                self.experiment_mgr.save_sessions_to_json()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        
        event.accept()
