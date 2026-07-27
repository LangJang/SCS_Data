"""
Main application window — SCS Marine Environmental Data Tool.

Left-right split layout: data tree + interactive map.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QStatusBar, QMenuBar, QMenu, QFileDialog, QMessageBox,
    QPushButton,
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QKeySequence

from src.core.pipeline import MarineDataPipeline
from src.core.roms_utils import extract_field
from src.core.canonical import SourceMeta
from src.ui.widgets.map_canvas import MapCanvas
from src.ui.widgets.data_tree import DataTree
from src.ui.widgets.control_bar import ControlBar, compute_depth_validity
from src.ui.widgets.timeseries_popup import TimeseriesPopup
from src.ui.widgets.export_dialog import ExportDialog


class MainWindow(QMainWindow):
    """Top-level application window.

    Layout::

        ┌────────────┬──────────────────────────┐
        │  DataTree  │                          │
        │            │     MapCanvas            │
        │            │                          │
        │  (meta)    ├──────────────────────────┤
        │            │     ControlBar           │
        └────────────┴──────────────────────────┘
    """

    WINDOW_TITLE = "SCS Marine Environmental Data Tool"
    DEFAULT_SIZE = (1400, 900)

    def __init__(self) -> None:
        super().__init__()
        self._pipeline: MarineDataPipeline | None = None
        self._current_key: str = ""
        self._current_canon: str = ""
        self._current_meta: SourceMeta | None = None
        self._selected_bbox: tuple[float, float, float, float] | None = None

        self._init_ui()
        self._connect_signals()
        self._restore_settings()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(*self.DEFAULT_SIZE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)

        # ---- Left: DataTree ----
        self._data_tree = DataTree()

        # ---- Right: Map + Controls ----
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Map
        self._map_canvas = MapCanvas()
        right_splitter.addWidget(self._map_canvas)

        # Navigation toolbar
        toolbar = self._map_canvas.create_toolbar(self)
        toolbar.setMaximumHeight(32)

        # Control bar (time + depth sliders)
        self._control_bar = ControlBar()

        # Buttons
        self._draw_btn = QPushButton("&Generate Map")
        self._draw_btn.setEnabled(False)
        self._draw_btn.setShortcut(QKeySequence("Ctrl+G"))
        self._draw_btn.setToolTip("Render the map with current selections (Ctrl+G)")

        self._export_btn = QPushButton("Export Subset...")
        self._export_btn.setEnabled(False)

        self._save_png_btn = QPushButton("Save Map PNG")
        self._save_png_btn.setEnabled(False)

        ctrl_row = QWidget()
        ctrl_layout = QHBoxLayout(ctrl_row)
        ctrl_layout.setContentsMargins(4, 4, 4, 4)
        ctrl_layout.addWidget(self._control_bar, 1)
        ctrl_layout.addWidget(self._draw_btn)
        ctrl_layout.addWidget(self._export_btn)
        ctrl_layout.addWidget(self._save_png_btn)

        # Compose right side
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(toolbar)
        right_layout.addWidget(right_splitter)
        right_layout.addWidget(ctrl_row)
        right_splitter.setStretchFactor(0, 1)

        # ---- Main splitter (left | right) ----
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self._data_tree)
        main_splitter.addWidget(right_widget)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        root.addWidget(main_splitter)

        # ---- Menus ----
        self._build_menus()

        # ---- Status bar ----
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — File → Open Data Folder to begin.")

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")

        open_roms = QAction("Open ROMS Folder...", self)
        open_roms.setShortcut("Ctrl+R")
        open_roms.triggered.connect(lambda: self._on_open_folder("roms"))
        file_menu.addAction(open_roms)

        open_cmems = QAction("Open CMEMS Folder...", self)
        open_cmems.setShortcut("Ctrl+M")
        open_cmems.triggered.connect(lambda: self._on_open_folder("cmems"))
        file_menu.addAction(open_cmems)

        file_menu.addSeparator()

        generate_action = QAction("Generate Map", self)
        generate_action.setShortcut(QKeySequence("Ctrl+G"))
        generate_action.triggered.connect(self._on_generate_map)
        file_menu.addAction(generate_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help
        help_menu = mb.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._data_tree.variable_selected.connect(self._on_variable_selected)
        self._control_bar.controls_changed.connect(self._on_controls_changed)
        self._draw_btn.clicked.connect(self._on_generate_map)
        self._save_png_btn.clicked.connect(self._on_save_png)
        self._export_btn.clicked.connect(self._on_export_subset)
        self._map_canvas.map_clicked.connect(self._on_map_clicked)
        self._map_canvas.region_selected.connect(self._on_region_selected)

    # ------------------------------------------------------------------
    # Slots — data loading
    # ------------------------------------------------------------------

    def _on_open_folder(self, source_hint: str) -> None:
        """Open a data folder, auto-detect sources, and populate the tree."""
        path = QFileDialog.getExistingDirectory(
            self, f"Select {source_hint.upper()} Data Folder",
            "",
        )
        if not path:
            return

        self._status.showMessage(f"Loading data from {path} ...")
        try:
            self._pipeline = MarineDataPipeline(path)
            self._pipeline.load_all()
            self._data_tree.load_pipeline(self._pipeline)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", str(e))
            self._status.showMessage("Ready.")
            return

        # Enable buttons
        self._draw_btn.setEnabled(True)
        self._export_btn.setEnabled(True)
        self._save_png_btn.setEnabled(True)

        sources = self._pipeline.sources()
        summary = ", ".join(f"{s}: {len(v)} files" for s, v in sources.items())
        self._status.showMessage(f"Loaded: {summary} — select a variable, then click Generate Map.")

    # ------------------------------------------------------------------
    # Slots — variable selection (no auto-render)
    # ------------------------------------------------------------------

    def _on_variable_selected(self, key: str, canon: str, meta, ds) -> None:
        """Variable clicked — configure controls only.  User must click Generate Map."""
        self._current_key = key
        self._current_canon = canon
        self._current_meta = meta

        # Pre-compute depth validity
        depth_cache = compute_depth_validity(ds, meta)

        # Configure control bar
        time_dim = meta.time_dim
        time_vals = ds[time_dim].values if time_dim and time_dim in ds.coords else ds[time_dim].values
        self._control_bar.configure(ds, meta, time_vals, depth_cache)
        self._control_bar.set_variable_depth_cache(canon)

        self._map_canvas.show_loading(meta.display_label(canon))
        self._status.showMessage(
            f"Ready: {meta.display_label(canon)} ({key}) — "
            f"adjust time/depth, then Ctrl+G to render."
        )

    def _on_controls_changed(self, time_idx: int, level_idx: int) -> None:
        """Slider moved — update status only.  No auto-render."""
        pass  # User controls the render timing via Generate Map button

    # ------------------------------------------------------------------
    # Generate Map (explicit user action)
    # ------------------------------------------------------------------

    def _on_generate_map(self) -> None:
        """User clicked Generate Map — show loading and render after 3s delay."""
        if not self._current_key or not self._current_canon or not self._current_meta:
            self._status.showMessage("Select a variable first.")
            return

        self._map_canvas.show_loading(
            self._current_meta.display_label(self._current_canon)
        )
        self._status.showMessage(f"Generating {self._current_canon} ...")
        QTimer.singleShot(3000, self._render_map)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _render_map(self) -> None:
        """Extract the current field and update the map canvas."""
        key = self._current_key
        canon = self._current_canon
        meta = self._current_meta
        if meta is None or self._pipeline is None:
            return

        ds = self._pipeline.ds_for(key)
        time_idx = self._control_bar.time_idx
        level_idx = self._control_bar.level_idx

        try:
            da, lon, lat = extract_field(ds, meta, canon, time_idx, level_idx)
        except (KeyError, ValueError) as e:
            self._status.showMessage(f"Extract error: {e}")
            return

        title = f"{meta.source_name} — {meta.display_label(canon)}"
        unit = meta.standard_units(canon)

        self._map_canvas.update_map(da, lon, lat, title=title, cmap="Spectral_r", unit=unit)
        self._status.showMessage(
            f"{key}  →  {canon}  |  time={time_idx}  level={level_idx}"
        )

    # ------------------------------------------------------------------
    # Slots — map interaction
    # ------------------------------------------------------------------

    def _on_map_clicked(self, lon: float, lat: float) -> None:
        """Map clicked — open time-series popup."""
        if self._pipeline is None or self._current_meta is None:
            self._status.showMessage("Load data first.")
            return

        ds = self._pipeline.ds_for(self._current_key)
        popup = TimeseriesPopup(
            self, ds, self._current_meta,
            self._current_canon, lon, lat,
        )
        popup.exec()

    def _on_region_selected(self, lon_min, lon_max, lat_min, lat_max) -> None:
        """Region selected on map — store for export."""
        self._selected_bbox = (lon_min, lon_max, lat_min, lat_max)
        self._status.showMessage(
            f"Region selected: lon=[{lon_min:.4f}, {lon_max:.4f}]  "
            f"lat=[{lat_min:.4f}, {lat_max:.4f}] — use Export Subset to save"
        )

    # ------------------------------------------------------------------
    # Slots — export
    # ------------------------------------------------------------------

    def _on_save_png(self) -> None:
        """Save the current map view as a PNG file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Map as PNG", "map_snapshot.png",
            "PNG Images (*.png)",
        )
        if not path:
            return
        try:
            self._map_canvas.figure.savefig(path, dpi=200, bbox_inches="tight")
            self._status.showMessage(f"Saved: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    def _on_export_subset(self) -> None:
        """Open the export dialog for the current variable selection."""
        if self._pipeline is None or self._current_meta is None:
            self._status.showMessage("Select a variable first.")
            return

        ds = self._pipeline.ds_for(self._current_key)

        dlg = ExportDialog(
            self, ds, self._current_meta,
            self._current_canon,
            self._control_bar.time_idx,
            self._control_bar.level_idx,
            bbox=self._selected_bbox,
        )
        dlg.exec()

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About SCS Marine Data Tool",
            "SCS Marine Environmental Data Tool\n\n"
            "Multi-source oceanographic data browsing, visualization, and export.\n\n"
            "Data sources: ROMS (model output) + CMEMS (Copernicus Marine)\n"
            "Built with Python 3.11 + PyQt6 + Cartopy.",
        )

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _restore_settings(self) -> None:
        settings = QSettings("SCS_Data", "SCS_Marine_Tool")
        geo = settings.value("window/geometry")
        if geo:
            self.restoreGeometry(geo)

    def closeEvent(self, event) -> None:
        settings = QSettings("SCS_Data", "SCS_Marine_Tool")
        settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)
