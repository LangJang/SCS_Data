"""
Parameter panel and preview map (middle section — "Make a Graph").

Left: variable selector, time range, spatial range, resolution, color style.
Right: low-resolution preview map with colorbar.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QDateEdit, QDoubleSpinBox, QSplitter,
    QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal

from src.core.config_reader import AppConfig, DatasetConfig, PresetRegion
from src.ui.widgets.map_canvas import MapCanvas


# ---------------------------------------------------------------------------
# Statistics scale options
# ---------------------------------------------------------------------------

STAT_SCALES = {
    "Daily":          "day",
    "Weekly Mean":    "W-MON",
    "Monthly Mean":   "ME",
    "Annual Mean":    "YE",
}


# ---------------------------------------------------------------------------
# ParamPanel (left side)
# ---------------------------------------------------------------------------

class ParamPanel(QGroupBox):
    """Time / space / resolution / color controls.

    Signals
    -------
    params_changed()
        Emitted when any parameter value changes.
    """

    params_changed = pyqtSignal()

    def __init__(self, config: AppConfig, parent=None):
        super().__init__("Graph Settings", parent)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- Variable ----
        layout.addWidget(QLabel("Variable:"))
        self._var_combo = QComboBox()
        self._var_combo.currentIndexChanged.connect(self.params_changed.emit)
        layout.addWidget(self._var_combo)

        # ---- Depth / Level ----
        layout.addWidget(QLabel("Depth / Level:"))
        self._depth_combo = QComboBox()
        self._depth_combo.currentIndexChanged.connect(self.params_changed.emit)
        layout.addWidget(self._depth_combo)

        # ---- Time: start / end ----
        layout.addWidget(QLabel("Time Range:"))
        tr = QHBoxLayout()
        self._time_start = QDateEdit()
        self._time_start.setCalendarPopup(True)
        self._time_start.setDisplayFormat("yyyy-MM-dd")
        tr.addWidget(QLabel("Start:"))
        tr.addWidget(self._time_start)
        self._time_end = QDateEdit()
        self._time_end.setCalendarPopup(True)
        self._time_end.setDisplayFormat("yyyy-MM-dd")
        tr.addWidget(QLabel("End:"))
        tr.addWidget(self._time_end)
        layout.addLayout(tr)

        # Statistics scale
        self._stat_combo = QComboBox()
        self._stat_combo.addItems(list(STAT_SCALES.keys()))
        self._stat_combo.currentIndexChanged.connect(self.params_changed.emit)
        layout.addWidget(self._stat_combo)

        # ---- Spatial: N/S/E/W ----
        layout.addWidget(QLabel("Spatial Range:"))
        grid = QVBoxLayout()

        # North / South
        ns = QHBoxLayout()
        ns.addWidget(QLabel("N:"))
        self._north_spin = QDoubleSpinBox()
        self._north_spin.setRange(-90, 90)
        self._north_spin.setDecimals(2)
        self._north_spin.setValue(30)
        self._north_spin.valueChanged.connect(self.params_changed.emit)
        ns.addWidget(self._north_spin)
        ns.addWidget(QLabel("S:"))
        self._south_spin = QDoubleSpinBox()
        self._south_spin.setRange(-90, 90)
        self._south_spin.setDecimals(2)
        self._south_spin.setValue(0)
        self._south_spin.valueChanged.connect(self.params_changed.emit)
        ns.addWidget(self._south_spin)
        grid.addLayout(ns)

        # East / West
        ew = QHBoxLayout()
        ew.addWidget(QLabel("E:"))
        self._east_spin = QDoubleSpinBox()
        self._east_spin.setRange(-180, 180)
        self._east_spin.setDecimals(2)
        self._east_spin.setValue(125)
        self._east_spin.valueChanged.connect(self.params_changed.emit)
        ew.addWidget(self._east_spin)
        ew.addWidget(QLabel("W:"))
        self._west_spin = QDoubleSpinBox()
        self._west_spin.setRange(-180, 180)
        self._west_spin.setDecimals(2)
        self._west_spin.setValue(105)
        self._west_spin.valueChanged.connect(self.params_changed.emit)
        ew.addWidget(self._west_spin)
        grid.addLayout(ew)

        layout.addLayout(grid)

        # Preset regions
        region_row = QHBoxLayout()
        region_row.addWidget(QLabel("Preset:"))
        self._region_combo = QComboBox()
        self._region_combo.addItem("— Custom —")
        for r in self._config.preset_regions:
            self._region_combo.addItem(r.name)
        self._region_combo.currentIndexChanged.connect(self._on_region_changed)
        region_row.addWidget(self._region_combo, 1)
        layout.addLayout(region_row)

        # ---- Resolution ----
        layout.addWidget(QLabel("Resolution:"))
        res_row = QHBoxLayout()
        self._res_combo = QComboBox()
        res_row.addWidget(self._res_combo, 1)
        self._orig_res_lbl = QLabel("")
        res_row.addWidget(self._orig_res_lbl)
        layout.addLayout(res_row)
        self._res_combo.currentIndexChanged.connect(self.params_changed.emit)

        # ---- Color style ----
        layout.addWidget(QLabel("Color Style:"))
        self._cmap_combo = QComboBox()
        self._cmap_combo.addItems(self._config.color_styles)
        self._cmap_combo.setCurrentText("Spectral_r")
        self._cmap_combo.currentIndexChanged.connect(self.params_changed.emit)
        layout.addWidget(self._cmap_combo)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Dataset binding
    # ------------------------------------------------------------------

    def set_dataset(self, ds: DatasetConfig) -> None:
        """Configure controls for a specific dataset."""
        # Variables
        self._var_combo.blockSignals(True)
        self._var_combo.clear()
        for v in ds.variables:
            self._var_combo.addItem(v)
        self._var_combo.blockSignals(False)

        # Time
        if ds.time_start:
            self._time_start.setDate(QDate.fromString(ds.time_start, "yyyy-MM-dd"))
        if ds.time_end:
            self._time_end.setDate(QDate.fromString(ds.time_end, "yyyy-MM-dd"))

        # Spatial
        self._north_spin.setValue(ds.lat_max)
        self._south_spin.setValue(ds.lat_min)
        self._east_spin.setValue(ds.lon_max)
        self._west_spin.setValue(ds.lon_min)

        # Resolution
        self._res_combo.blockSignals(True)
        self._res_combo.clear()
        for r in ds.available_resolutions:
            self._res_combo.addItem(f"{r}°", r)
        default_idx = ds.available_resolutions.index(ds.default_resolution) \
            if ds.default_resolution in ds.available_resolutions else 0
        self._res_combo.setCurrentIndex(default_idx)
        self._res_combo.blockSignals(False)
        self._orig_res_lbl.setText(f"(original: {ds.default_resolution}°)")

        # cmap
        self._cmap_combo.setCurrentText("Spectral_r")

        # Depth — pre-populate from config (refined after Plot loads real data)
        self._prepopulate_depths(ds)

    def _prepopulate_depths(self, ds: DatasetConfig) -> None:
        """Pre-fill depth combo from config metadata before data loads."""
        self._depth_combo.blockSignals(True)
        self._depth_combo.clear()

        if ds.vertical_type == "depth" and ds.vertical_layers > 0:
            if ds.depth_values:
                for i, d in enumerate(ds.depth_values):
                    self._depth_combo.addItem(f"{float(d):.0f} m", i)
            elif ds.vertical_range and len(ds.vertical_range) == 2:
                d_min, d_max = ds.vertical_range
                depths = np.linspace(d_min, d_max, ds.vertical_layers)
                for i, d in enumerate(depths):
                    self._depth_combo.addItem(f"{float(d):.0f} m", i)
            else:
                for i in range(ds.vertical_layers):
                    self._depth_combo.addItem(f"level {i}", i)
            self._depth_combo.setCurrentIndex(0)
        elif ds.vertical_type == "sigma" and ds.vertical_layers > 0:
            n = ds.vertical_layers
            for i in range(n):
                label = f"s_rho[{i}] (surface)" if i == n - 1 else \
                       f"s_rho[{i}] (bottom)" if i == 0 else f"s_rho[{i}]"
                self._depth_combo.addItem(label, i)
            self._depth_combo.setCurrentIndex(n - 1)  # surface
        else:
            self._depth_combo.addItem("(2-D only)", 0)

        self._depth_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Value accessors
    # ------------------------------------------------------------------

    @property
    def variable(self) -> str:
        return self._var_combo.currentText()

    @property
    def depth_index(self) -> int:
        """Return the selected depth/level index (0-based)."""
        data = self._depth_combo.currentData()
        return data if data is not None else 0

    def set_depth_levels(self, ds: xr.Dataset, meta) -> None:
        """Populate depth combo from a loaded dataset."""
        self._depth_combo.blockSignals(True)
        self._depth_combo.clear()

        depth_name = meta.coord_map.get("depth", "depth")
        if depth_name in ds.dims or depth_name in ds.coords:
            depths = ds[depth_name].values
            for i, d in enumerate(depths):
                if float(d) < 0:  # skip fill values (e.g. -99999)
                    continue
                self._depth_combo.addItem(f"{float(d):.0f} m", i)
            self._depth_combo.setCurrentIndex(0)  # surface = first
        elif "s_rho" in ds.dims:
            n = ds.sizes["s_rho"]
            for i in range(n):
                label = f"s_rho[{i}] (surface)" if i == n - 1 else \
                       f"s_rho[{i}] (bottom)" if i == 0 else f"s_rho[{i}]"
                self._depth_combo.addItem(label, i)
            self._depth_combo.setCurrentIndex(n - 1)  # surface = last
        else:
            self._depth_combo.addItem("(2-D only)", 0)

        self._depth_combo.blockSignals(False)

    @property
    def time_start_str(self) -> str:
        return self._time_start.date().toString("yyyy-MM-dd")

    @property
    def time_end_str(self) -> str:
        return self._time_end.date().toString("yyyy-MM-dd")

    @property
    def stat_scale(self) -> str:
        return STAT_SCALES.get(self._stat_combo.currentText(), "day")

    @property
    def north(self) -> float:
        return self._north_spin.value()

    @property
    def south(self) -> float:
        return self._south_spin.value()

    @property
    def east(self) -> float:
        return self._east_spin.value()

    @property
    def west(self) -> float:
        return self._west_spin.value()

    @property
    def resolution(self) -> float:
        return self._res_combo.currentData() or 0.1

    @property
    def cmap(self) -> str:
        return self._cmap_combo.currentText()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_region_changed(self, idx: int) -> None:
        if idx <= 0:
            return
        region = self._config.preset_regions[idx - 1]
        self._north_spin.setValue(region.north)
        self._south_spin.setValue(region.south)
        self._east_spin.setValue(region.east)
        self._west_spin.setValue(region.west)


# ---------------------------------------------------------------------------
# PreviewSection (right side)
# ---------------------------------------------------------------------------

class PreviewSection(QGroupBox):
    """Preview map + colorbar area.

    Wraps :class:`MapCanvas` with a label and provides a simple
    ``show_preview()`` method used by the main window's Plot action.
    """

    def __init__(self, parent=None):
        super().__init__("Preview Map", parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self._canvas = MapCanvas()
        layout.addWidget(self._canvas)

        # Toolbar
        toolbar = self._canvas.create_toolbar(self)
        toolbar.setMaximumHeight(32)
        layout.addWidget(toolbar)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def update_preview(
        self,
        da: xr.DataArray,
        lon: np.ndarray,
        lat: np.ndarray,
        *,
        title: str = "",
        cmap: str = "Spectral_r",
        unit: str = "",
        extent: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Render a low-resolution preview, optionally zoomed to *extent*."""
        self._canvas.update_map(da, lon, lat, title=title, cmap=cmap, unit=unit,
                                 extent=extent)

    @property
    def canvas(self) -> MapCanvas:
        return self._canvas
