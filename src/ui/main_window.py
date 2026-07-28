"""
Main application window — SCS Marine Environmental Data Tool.

Three-section vertical layout (ERDDAP-inspired):

    ┌──────────────────────────────────────────┐
    │  SearchSection — "Find the Data"         │
    ├──────────────────────────────────────────┤
    │  ParamPanel  |  PreviewSection           │
    │  "Make a Graph"                          │
    ├──────────────────────────────────────────┤
    │  "Plot & Export"   [Plot]  [Export]      │
    └──────────────────────────────────────────┘

Workflow: search → select dataset → configure params → Plot → Export.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QStatusBar, QMenuBar, QMenu, QFileDialog, QMessageBox,
    QPushButton, QGroupBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QKeySequence

import numpy as np
import pandas as pd
import xarray as xr

from src.core.canonical import SourceMeta
from src.core.roms_utils import extract_field
from src.core.config_reader import AppConfig, DatasetConfig, load_config
from src.ui.widgets.search_section import SearchSection
from src.ui.widgets.param_section import ParamPanel, PreviewSection
from src.ui.widgets.export_dialog import ExportDialog


class MainWindow(QMainWindow):
    """Top-level application window."""

    WINDOW_TITLE = "SCS Marine Environmental Data Tool"
    DEFAULT_SIZE = (1500, 950)

    def __init__(self) -> None:
        super().__init__()
        self._config = load_config()
        self._current_ds_cfg: DatasetConfig | None = None
        self._current_ds: xr.Dataset | None = None
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
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ---- Section 1: Find the Data ----
        self._search_section = SearchSection(self._config)
        root.addWidget(self._search_section)

        # ---- Section 2: Make a Graph (left params | right preview) ----
        graph_group = QGroupBox("Make a Graph")
        graph_layout = QHBoxLayout(graph_group)

        self._param_panel = ParamPanel(self._config)
        self._preview = PreviewSection()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._param_panel)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        graph_layout.addWidget(splitter)
        root.addWidget(graph_group, 1)  # stretch = 1 (takes remaining space)

        # ---- Section 3: Plot & Export ----
        action_group = QGroupBox("Plot & Export")
        action_layout = QHBoxLayout(action_group)

        self._plot_btn = QPushButton("&Plot")
        self._plot_btn.setShortcut(QKeySequence("Ctrl+G"))
        self._plot_btn.setToolTip("Generate the map with current settings (Ctrl+G)")
        self._plot_btn.setMinimumHeight(36)
        self._plot_btn.setEnabled(False)

        self._export_btn = QPushButton("&Export")
        self._export_btn.setShortcut(QKeySequence("Ctrl+E"))
        self._export_btn.setToolTip("Export the current view (Ctrl+E)")
        self._export_btn.setMinimumHeight(36)
        self._export_btn.setEnabled(False)

        action_layout.addStretch()
        action_layout.addWidget(self._plot_btn)
        action_layout.addWidget(self._export_btn)
        action_layout.addStretch()

        root.addWidget(action_group)

        # ---- Menus ----
        self._build_menus()

        # ---- Status bar ----
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(
            "Ready — search for a dataset to begin."
        )

    def _build_menus(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")

        gen_action = QAction("&Plot", self)
        gen_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_action.triggered.connect(self._on_plot)
        file_menu.addAction(gen_action)

        export_action = QAction("&Export...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = mb.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._search_section.dataset_selected.connect(self._on_dataset_selected)
        self._param_panel.params_changed.connect(self._on_params_changed)
        self._plot_btn.clicked.connect(self._on_plot)
        self._export_btn.clicked.connect(self._on_export)
        self._preview.canvas.map_clicked.connect(self._on_map_clicked)
        self._preview.canvas.region_selected.connect(self._on_region_selected)

    # ------------------------------------------------------------------
    # Slots — dataset selection
    # ------------------------------------------------------------------

    def _on_dataset_selected(self, ds_cfg: DatasetConfig) -> None:
        """A dataset card was clicked in the search results."""
        self._current_ds_cfg = ds_cfg
        self._param_panel.set_dataset(ds_cfg)
        self._current_ds = None  # force reload on next Plot
        self._current_meta = None

        self._plot_btn.setEnabled(True)
        self._export_btn.setEnabled(True)

        self._status.showMessage(
            f"Selected: {ds_cfg.name} — configure settings, then click Plot."
        )

    def _on_params_changed(self) -> None:
        """Any parameter changed — refresh preview if data is loaded."""
        if self._current_ds is None or self._current_meta is None:
            return
        self._refresh_preview()

    # ------------------------------------------------------------------
    # Slots — Plot
    # ------------------------------------------------------------------

    def _on_plot(self) -> None:
        """Load data, apply filters, render preview map."""
        if self._current_ds_cfg is None:
            self._status.showMessage("Search and select a dataset first.")
            return

        self._plot_btn.setEnabled(False)
        self._status.showMessage("Loading data ...")

        QTimer.singleShot(500, self._do_plot)  # brief yield for UI update

    def _do_plot(self) -> None:
        """Load data, then refresh preview."""
        cfg = self._current_ds_cfg

        # Load the NetCDF file (only if not already loaded for this dataset)
        if self._current_ds is None:
            try:
                data_path = cfg.resolve_path(Path("."))
                nc_files = sorted(data_path.glob(cfg.file_pattern))
                if not nc_files:
                    raise FileNotFoundError(
                        f"No files matching '{cfg.file_pattern}' in {data_path}"
                    )
                self._current_ds = xr.open_dataset(nc_files[0], engine="netcdf4")
            except Exception as e:
                self._status.showMessage(f"Load error: {e}")
                self._plot_btn.setEnabled(True)
                return

            # Detect source and build meta
            from src.core.adapters import detect_source
            adapter_cls = detect_source(self._current_ds, str(nc_files[0]))
            if adapter_cls is None:
                self._status.showMessage("Could not detect data source.")
                self._plot_btn.setEnabled(True)
                return
            adapter = adapter_cls()
            self._current_meta = adapter.adapt(self._current_ds)

            # Populate depth levels from loaded data
            self._param_panel.set_depth_levels(self._current_ds, self._current_meta)

        self._refresh_preview()
        self._plot_btn.setEnabled(True)

    def _refresh_preview(self) -> None:
        """Re-extract field with current params and update the preview map."""
        if self._current_ds is None or self._current_meta is None:
            return

        ds = self._current_ds
        meta = self._current_meta
        cfg = self._current_ds_cfg
        canon = self._param_panel.variable

        time_idx = self._resolve_time_index(ds, meta)
        level_idx = self._param_panel.depth_index

        # Extract field
        try:
            da, lon, lat = extract_field(ds, meta, canon, time_idx, level_idx)
        except Exception as e:
            self._status.showMessage(f"Extract error: {e}")
            return

        # Apply spatial subset
        da = _apply_spatial_mask(da, lon, lat,
                                  self._param_panel.north,
                                  self._param_panel.south,
                                  self._param_panel.east,
                                  self._param_panel.west)

        # Compute padded extent for zoom
        west, east = self._param_panel.west, self._param_panel.east
        south, north = self._param_panel.south, self._param_panel.north
        pad_lon = (east - west) * 0.15
        pad_lat = (north - south) * 0.15
        extent = (west - pad_lon, east + pad_lon, south - pad_lat, north + pad_lat)

        # Render
        title = f"{cfg.source} — {meta.display_label(canon)}"
        cmap = self._param_panel.cmap
        unit = meta.standard_units(canon)

        self._preview.update_preview(da, lon, lat, title=title, cmap=cmap, unit=unit,
                                      extent=extent)

        self._status.showMessage(
            f"{cfg.name}  →  {canon}  "
            f"({self._param_panel.time_start_str})  "
            f"cmap={cmap}"
        )

    # ------------------------------------------------------------------
    # Slots — Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        """Open the export dialog."""
        if self._current_ds is None or self._current_meta is None:
            self._status.showMessage("Plot a dataset first.")
            return

        settings = QSettings("SCS_Data", "SCS_Marine_Tool")
        last_dir = settings.value("export/last_dir", "")

        dlg = ExportDialog(
            self,
            self._current_ds,
            self._current_meta,
            self._param_panel.variable,
            self._resolve_time_index(self._current_ds, self._current_meta),
            self._param_panel.depth_index,
            north=self._param_panel.north,
            south=self._param_panel.south,
            east=self._param_panel.east,
            west=self._param_panel.west,
            auto_name=self._build_auto_name(),
            default_dir=last_dir,
        )
        if dlg.exec():  # Accepted = truthy
            settings.setValue("export/last_dir", dlg.save_dir)

    # ------------------------------------------------------------------
    # Slots — map interaction
    # ------------------------------------------------------------------

    def _on_map_clicked(self, lon: float, lat: float) -> None:
        self._status.showMessage(f"Clicked: ({lon:.4f}, {lat:.4f})")

    def _on_region_selected(self, lon_min, lon_max, lat_min, lat_max) -> None:
        self._selected_bbox = (lon_min, lon_max, lat_min, lat_max)
        self._status.showMessage(
            f"Region: lon=[{lon_min:.2f}, {lon_max:.2f}]  "
            f"lat=[{lat_min:.2f}, {lat_max:.2f}]"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_time_index(self, ds: xr.Dataset, meta: SourceMeta) -> int:
        """Find the time index closest to the selected start date."""
        target = self._param_panel.time_start_str
        time_dim = meta.time_dim
        if not time_dim or time_dim not in ds.coords:
            return 0
        t_vals = ds[time_dim].values
        target_ns = pd.Timestamp(target).asm8.astype("datetime64[ns]").astype(np.int64)
        t_ns = t_vals.astype("datetime64[ns]").astype(np.int64)
        return int(np.argmin(np.abs(t_ns - target_ns)))

    def _build_auto_name(self) -> str:
        """Build auto filename: Variable_StartDate_EndDate_Depth."""
        var = self._param_panel.variable
        t1 = self._param_panel.time_start_str
        t2 = self._param_panel.time_end_str
        # Depth info from the combo label (e.g. "0 m" or "s_rho[44] (surface)")
        depth_text = self._param_panel._depth_combo.currentText()
        depth_part = depth_text.split()[0]  # first word only (e.g. "0", "s_rho[44]")
        depth_part = depth_part.replace(".", "p")  # avoid double extension
        return f"{var}_{t1}_{t2}_{depth_part}"

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About SCS Marine Data Tool",
            "SCS Marine Environmental Data Tool\n\n"
            "Multi-source oceanographic data browsing, visualization, and export.\n\n"
            "Data sources: ROMS (model output) + CMEMS (Copernicus Marine)\n"
            "Built with Python 3.11 + PyQt6 + Cartopy.",
        )

    def _restore_settings(self) -> None:
        settings = QSettings("SCS_Data", "SCS_Marine_Tool")
        geo = settings.value("window/geometry")
        if geo:
            self.restoreGeometry(geo)

    def closeEvent(self, event) -> None:
        settings = QSettings("SCS_Data", "SCS_Marine_Tool")
        settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _apply_spatial_mask(da, lon, lat, north, south, east, west):
    """Mask a DataArray outside the given geographic bounds.

    NaN-masks grid cells whose centre is outside [west, east] × [south, north].
    """
    import numpy as np

    vals = da.values.astype(float)

    if lon.ndim == 2 and lat.ndim == 2:
        mask = (lon < west) | (lon > east) | (lat < south) | (lat > north)
    else:
        # 1-D coords: broadcast
        lon2d, lat2d = np.meshgrid(lon, lat)
        mask = (lon2d < west) | (lon2d > east) | (lat2d < south) | (lat2d > north)

    vals[mask] = np.nan
    da.values = vals
    return da
