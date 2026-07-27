"""
SCS Marine Environmental Data Tool — Application Entry Point.

South China Sea oceanographic data aggregation, preprocessing,
visualization, and export utility.

Author: Wang Shuo
License: TBD
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor

# Ensure both project root and src/ are on path
SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
for p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ui.main_window import MainWindow


def main() -> int:
    """Launch the SCS Marine Data Tool GUI."""
    app = QApplication(sys.argv)
    app.setApplicationName("SCS Marine Data Tool")
    app.setOrganizationName("SCS_Data")

    # Force light theme regardless of system setting
    app.setStyle(QStyleFactory.create("Fusion"))
    light = QPalette()
    light.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    light.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 30))
    light.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    light.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
    light.setColor(QPalette.ColorRole.Text, QColor(30, 30, 30))
    light.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    light.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 30))
    light.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    light.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(light)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
