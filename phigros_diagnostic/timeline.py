"""Phigros Diagnostic Tool - Timeline Module.

Provides PySide6 UI components for real-time event display,
timeline visualization, sorting, filtering, and interval calculation.
"""

import uuid
from datetime import datetime

from PySide6.QtWidgets import (
    QTableView, QListView, QHeaderView, QVBoxLayout, QHBoxLayout,
    QWidget, QComboBox, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QMenu, QTextEdit,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox, QApplication
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, QTimer, QAbstractTableModel
from PySide6.QtGui import QColor, QAction


class EventTableModel:
    """Simple data model for events in the timeline."""
    
    def __init__(self):
        self.events = []  # List of ParsedEvent objects
        self.manual_events = []  # List of manually marked events
        self.lock = None  # Will be set by caller for thread safety
    
    def add_events(self, events):
        """Add parsed events to the model."""
        if self.lock:
            with self.lock:
                self.events.extend(events)
        else:
            self.events.extend(events)
    
    def add_manual_event(self, event):
        """Add a manually marked experiment event."""
        if self.lock:
            with self.lock:
                self.manual_events.append(event)
        else:
            self.manual_events.append(event)
    
    def clear(self):
        """Clear all events."""
        if self.lock:
            with self.lock:
                self.events.clear()
                self.manual_events.clear()
        else:
            self.events.clear()
            self.manual_events.clear()
    
    @property
    def event_count(self):
        return len(self.events)
    
    @property
    def manual_event_count(self):
        return len(self.manual_events)


class FilterProxyModel(QSortFilterProxyModel):
    """Custom proxy model for filtering events by type."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_types = set()
        self._include_unknown = True
    
    def setActiveTypes(self, types):
        """Set which event types to include."""
        self._active_types = types
        self.invalidateFilter()
    
    def setIncludeUnknown(self, include):
        """Set whether to include UNKNOWN type events."""
        self._include_unknown = include
        self.invalidateFilter()
    
    def filterAcceptsRow(self, source_row, source_parent):
        """Override to filter by event type."""
        index = self.sourceModel().index(source_row, 0, source_parent)
        # Check if column for event type exists
        type_index = self.sourceModel().index(source_row, 
                            self.sourceModel().columnCount() - 2, source_parent)
        event_type = type_index.data(Qt.DisplayRole)
        
        if not self._active_types:
            return True
        
        if event_type in self._active_types:
            return True
        
        if event_type == 'Unknown' and self._include_unknown:
            return True
        
        return False


class TimelineView(QTableView):
    """Main timeline table view for displaying parsed events."""
    
    # Signal emitted when an event is selected
    event_selected = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Configure the table view."""
        # Single selection mode
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        
        # Horizontal header settings
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Timestamp column
        
        # Enable sorting
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)
        
        # Alternating row colors for readability
        self.setAlternatingRowColors(True)
        
        # Context menu for event details
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def show_context_menu(self, position):
        """Show context menu with event details."""
        menu = QMenu(self)
        
        copy_action = QAction("Copy Raw Log", self)
        copy_action.triggered.connect(self.copy_selected_log)
        menu.addAction(copy_action)
        
        menu.exec(self.mapToGlobal(position))
    
    def copy_selected_log(self):
        """Copy the raw log of the selected event to clipboard."""
        selection = self.selectionModel()
        if not selection.hasSelection():
            return
        
        rows = selection.selectedRows()
        if rows:
            row = rows[0].row()
            # Get raw log from the last column
            index = self.model().index(row, 5)
            log_text = index.data(Qt.DisplayRole)
            if log_text:
                QApplication.clipboard().setText(log_text)
    
    def populate_from_model(self, model):
        """Populate the table from an EventTableModel."""
        self.wrapper = EventTableWrapper(model)
        self.setModel(self.wrapper)
        
        # Hide the internal ID column if present
        if self.model().columnCount() > 6:
            self.hideColumn(6)


class EventTableWrapper(QAbstractTableModel):
    """Wraps EventTableModel for use with QTableView."""
    
    def __init__(self, event_model):
        super().__init__()
        self._event_model = event_model

    def append_events(self, events):
        """Append events to the model and notify attached views."""
        if not events:
            return
        first = len(self._event_model.events)
        self.beginInsertRows(self.index(0, 0).parent(), first, first + len(events) - 1)
        self._event_model.add_events(events)
        self.endInsertRows()
    
    def rowCount(self, parent=None):
        return len(self._event_model.events)
    
    def columnCount(self, parent=None):
        return 6
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        event = self._event_model.events[index.row()]
        
        if role == Qt.DisplayRole:
            col = index.column()
            if col == 0:
                return event.timestamp.isoformat() if event.timestamp else ''
            elif col == 1:
                return event.receive_time.isoformat() if event.receive_time else ''
            elif col == 2:
                return event.event_type.value
            elif col == 3:
                return event.details.get('pid', '')
            elif col == 4:
                return event.details.get('class_name', '')
            elif col == 5:
                return event.raw_line[:100] + ('...' if len(event.raw_line) > 100 else '')
        
        return None
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            headers = ['Timestamp', 'Receive Time', 'Event Type', 'PID', 'Class', 'Raw Log']
            return headers[section]
        return None
    
    def sort(self, column, order):
        """Sort events by the specified column."""
        reverse = (order == Qt.DescendingOrder)
        
        if column == 0:  # Sort by timestamp
            self._event_model.events.sort(
                key=lambda e: e.timestamp or datetime.min,
                reverse=reverse
            )
        elif column == 1:  # Sort by receive time
            self._event_model.events.sort(
                key=lambda e: e.receive_time or datetime.min,
                reverse=reverse
            )
        
        self.layoutChanged.emit()


class ExperimentMarkWidget(QWidget):
    """Widget for marking experiment events manually."""
    
    mark_added = Signal(dict)  # Signal when a new mark is added
    
    EXPERIMENT_TYPES = [
        "Game Start",
        "Song Select",
        "Map Load Start",
        "Map Load End",
        "Play Start",
        "Pause",
        "Resume",
        "Play End",
        "Score Screen",
        "PREVIEW_PLAYING",
        "START_TRIGGER",
        "PREVIEW_STOPPED",
        "GAMEPLAY_AUDIO_STARTED",
        "Other"
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mark_counter = 0
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the experiment marking UI."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Manual Experiment Marking")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Type selector
        type_layout = QHBoxLayout()
        type_label = QLabel("Event Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(self.EXPERIMENT_TYPES)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)
        
        # Notes input
        notes_layout = QHBoxLayout()
        notes_label = QLabel("Notes:")
        self.notes_input = QLineEdit()
        self.notes_input.placeholderText = "Optional notes..."
        notes_layout.addWidget(notes_label)
        notes_layout.addWidget(self.notes_input)
        layout.addLayout(notes_layout)
        
        # Add button
        add_btn = QPushButton("Add Mark")
        add_btn.clicked.connect(self.add_mark)
        layout.addWidget(add_btn)
        
        # Spacer
        layout.addStretch()
    
    def add_mark(self):
        """Add a manual experiment mark."""
        from datetime import datetime, timezone
        
        self.mark_counter += 1
        mark = {
            'type': self.type_combo.currentText(),
            'notes': self.notes_input.text(),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'id': f"manual_{uuid.uuid4().hex}"
        }
        
        self.mark_added.emit(mark)
        self.notes_input.clear()


class StatisticsWidget(QWidget):
    """Widget showing event statistics and interval calculations."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the statistics UI."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Event Statistics")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Stats table
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(3)
        self.stats_table.setHorizontalHeaderLabels(['Metric', 'Value', 'Details'])
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.stats_table)
        
        # Spacer
        layout.addStretch()
    
    def update_stats(self, event_summary, lifecycle_pairs):
        """Update statistics display with current data."""
        self.stats_table.setRowCount(0)
        
        # Total events
        total_events = sum(event_summary.values())
        self.add_stat_row("Total Events", str(total_events), "")
        
        # Events by type
        for event_type, count in sorted(event_summary.items(), key=lambda x: -x[1]):
            self.add_stat_row(event_type.value, str(count), "")
        
        # Lifecycle pairs
        pb_pairs = len(lifecycle_pairs.get('player_bases', []))
        tp_pairs = len(lifecycle_pairs.get('track_player_bases', []))
        self.add_stat_row("PlayerBase Pairs", str(pb_pairs), "Create/Destruct cycles")
        self.add_stat_row("TrackPlayerBase Pairs", str(tp_pairs), "Create/Destruct cycles")
        
        # Intervals (if we have paired events)
        if tp_pairs > 0:
            track_pairs = lifecycle_pairs['track_player_bases']
            if len(track_pairs) >= 2:
                intervals = []
                for i in range(1, len(track_pairs)):
                    prev_destroy = track_pairs[i-1][1].timestamp
                    curr_create = track_pairs[i][0].timestamp
                    if prev_destroy and curr_create:
                        delta = (curr_create - prev_destroy).total_seconds()
                        intervals.append(delta)
                
                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    min_interval = min(intervals)
                    max_interval = max(intervals)
                    self.add_stat_row("Avg Track Interval", f"{avg_interval:.2f}s", "Between tracks")
                    self.add_stat_row("Min Track Interval", f"{min_interval:.2f}s", "")
                    self.add_stat_row("Max Track Interval", f"{max_interval:.2f}s", "")
    
    def add_stat_row(self, metric, value, details):
        """Add a row to the statistics table."""
        row = self.stats_table.rowCount()
        self.stats_table.insertRow(row)
        self.stats_table.setItem(row, 0, QTableWidgetItem(metric))
        self.stats_table.setItem(row, 1, QTableWidgetItem(value))
        self.stats_table.setItem(row, 2, QTableWidgetItem(details))


class FilterBar(QWidget):
    """Horizontal bar for filtering events by type."""
    
    filter_changed = Signal(set)  # Signal when filter changes
    
    def __init__(self, available_types=None, parent=None):
        super().__init__(parent)
        self.available_types = available_types or []
        self.checkboxes = {}
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the filter bar UI."""
        layout = QHBoxLayout(self)
        
        label = QLabel("Filter:")
        layout.addWidget(label)
        
        # Add checkboxes for each event type
        for event_type in self.available_types:
            cb = QCheckBox(event_type.value)
            cb.setChecked(True)
            cb.stateChanged.connect(self.on_filter_changed)
            self.checkboxes[event_type] = cb
            layout.addWidget(cb)
        
        # Clear/Select All buttons
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clear_all)
        layout.addWidget(clear_btn)
        
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        layout.addWidget(select_all_btn)
        
        layout.addStretch()
    
    def get_active_types(self):
        """Get set of currently active event types."""
        return set(
            et for et, cb in self.checkboxes.items() if cb.isChecked()
        )
    
    def on_filter_changed(self):
        """Emit signal when filter state changes."""
        self.filter_changed.emit(self.get_active_types())
    
    def clear_all(self):
        """Uncheck all filters."""
        for cb in self.checkboxes.values():
            cb.setChecked(False)
        self.filter_changed.emit(self.get_active_types())
    
    def select_all(self):
        """Check all filters."""
        for cb in self.checkboxes.values():
            cb.setChecked(True)
        self.filter_changed.emit(self.get_active_types())
