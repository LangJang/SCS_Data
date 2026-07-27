"""
Main application window for the SCS Marine Data Tool.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStatusBar, QMenuBar, QMenu, QTabWidget,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction


class MainWindow(QMainWindow):
    """Top-level application window with menu, tabs, and status bar."""

    WINDOW_TITLE = "SCS Marine Environmental Data Tool"
    DEFAULT_SIZE = (1280, 800)

    def __init__(self) -> None:
        super().__init__()
        self._data_dir: str = ""
        self._init_ui()
        self._restore_settings()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(*self.DEFAULT_SIZE)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        # Tab container (placeholder for data/viz/export panels)
        self._tabs = QTabWidget()
        self._tabs.addTab(QLabel("Data loading & preprocessing panel\n\nUse File → Open Data Folder to begin."), "Data")
        self._tabs.addTab(QLabel("Visualization panel"), "Visualization")
        self._tabs.addTab(QLabel("Export panel"), "Export")

        layout.addWidget(self._tabs)

        # Menu bar
        self._build_menus()

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — open a data folder to begin.")

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # ---- File menu ----
        file_menu = mb.addMenu("&File")

        open_action = QAction("Open Data Folder...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ---- Help menu ----
        help_menu = mb.addMenu("&Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_open_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Data Folder", self._data_dir or "",
        )
        if path:
            self._data_dir = path
            self._status.showMessage(f"Data folder: {path}")

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About SCS Marine Data Tool",
            "South China Sea Marine Environmental Data Tool\n\n"
            "Data aggregation, preprocessing, visualization, and export.\n"
            "Built with Python 3.11 + PyQt6.",
        )

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _restore_settings(self) -> None:
        settings = QSettings("SCS_Data", "SCS_Marine_Tool")
        geo = settings.value("window/geometry")
        if geo:
            self.restoreGeometry(geo)
        self._data_dir = settings.value("data/last_folder", "")

    def closeEvent(self, event) -> None:
        settings = QSettings("SCS_Data", "SCS_Marine_Tool")
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("data/last_folder", self._data_dir)
        super().closeEvent(event)
