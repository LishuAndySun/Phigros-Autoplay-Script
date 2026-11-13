#!/usr/bin/env python3
"""
Phigros Diagnostic Tool - Main Entry Point

A standalone diagnostic tool for studying Phigros Unity game logs,
audio player lifecycle, and observable events via ADB Logcat.

This tool does NOT modify Phigros or PhiAPS.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Phigros Diagnostic Tool")
    app.setOrganizationName("PhiAPS")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
