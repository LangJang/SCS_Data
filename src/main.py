"""
SCS Marine Environmental Data Tool — Application Entry Point.

South China Sea oceanographic data aggregation, preprocessing,
visualization, and export utility.

Author: Wang Shuo
License: TBD
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Ensure src/ is on path when running directly
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ui.main_window import MainWindow


def main() -> int:
    """Launch the SCS Marine Data Tool GUI."""
    app = QApplication(sys.argv)
    app.setApplicationName("SCS Marine Data Tool")
    app.setOrganizationName("SCS_Data")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
