"""
Time / depth selector bar for interactive map browsing.

Provides :class:`ControlBar` — a horizontal widget with:
- Time selector (slider for CMEMS; combo-box for ROMS discrete dates)
- Depth / level selector (slider with meter labels)
- Pre-computed per-variable depth validity cache

Signals
------
controls_changed(time_idx, level_idx)
    Emitted whenever the user moves either slider or selects a new date.
"""

from __future__ import annotations

from typing import Dict, List, Tuple
from collections import defaultdict

import numpy as np
import pandas as pd
import xarray as xr

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QSlider, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.core.canonical import SourceMeta, VerticalType


# ---------------------------------------------------------------------------
# Depth validity cache builder
# ---------------------------------------------------------------------------

def compute_depth_validity(
    ds: xr.Dataset,
    meta: SourceMeta,
) -> Dict[str, List[Tuple[int, float, float]]]:
    """Pre-compute per-variable per-depth validity ratios.

    Called once at data-load time. Iterates each variable's depth
    dimension (using ``time=0`` as the reference slice) and records
    the fraction of non-NaN grid cells.

    Returns
    -------
    dict[str, list[tuple[int, float, float]]]
        ``{canonical_name: [(depth_idx, depth_meters, valid_ratio), ...]}``.
    """
    depth_name = meta.coord_map.get("depth", "depth")
    if depth_name not in ds.dims and depth_name not in ds.coords:
        return {}

    depths = ds[depth_name].values
    cache: Dict[str, List[Tuple[int, float, float]]] = {}

    for canon in meta.available_variables():
        src_var = meta.source_var(canon)
        da = ds[src_var]
        if depth_name not in da.dims:
            continue

        entries: List[Tuple[int, float, float]] = []
        for i in range(da.sizes[depth_name]):
            layer = da.isel({depth_name: i})
            # Use first time step for the reference slice
            time_dim = meta.time_dim
            if time_dim and time_dim in layer.dims:
                layer = layer.isel({time_dim: 0})
            valid = float((~np.isnan(layer.values)).mean())
            entries.append((i, float(depths[i]), valid))

        cache[canon] = entries

    return cache


# ---------------------------------------------------------------------------
# ControlBar
# ---------------------------------------------------------------------------

class ControlBar(QWidget):
    """Time and depth/level selector bar.

    Parameters
    ----------
    parent : QWidget or None
    """

    controls_changed = pyqtSignal(int, int)
    """Emitted as ``controls_changed(time_idx, level_idx)``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ---- Time selector ----
        self._time_label = QLabel("Time:")
        self._time_slider = QSlider(Qt.Orientation.Horizontal)
        self._time_slider.setMinimum(0)
        self._time_slider.setMaximum(0)
        self._time_value_lbl = QLabel("—")

        # ROMS discrete combo (hidden by default)
        self._time_combo = QComboBox()
        self._time_combo.hide()

        # ---- Depth selector ----
        self._depth_label = QLabel("Depth:")
        self._depth_slider = QSlider(Qt.Orientation.Horizontal)
        self._depth_slider.setMinimum(0)
        self._depth_slider.setMaximum(0)
        self._depth_value_lbl = QLabel("—")

        # ---- Layout ----
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Time row
        layout.addWidget(self._time_label)
        layout.addWidget(self._time_slider, 3)
        layout.addWidget(self._time_combo, 3)
        layout.addWidget(self._time_value_lbl)
        layout.addSpacing(12)

        # Depth row
        layout.addWidget(self._depth_label)
        layout.addWidget(self._depth_slider, 3)
        layout.addWidget(self._depth_value_lbl)

        # ---- Internal state ----
        self._time_vals: np.ndarray | None = None
        self._depth_cache: Dict[str, List[Tuple[int, float, float]]] = {}
        self._current_depth_cache: List[Tuple[int, float, float]] = []
        self._is_roms: bool = False
        self._time_idx: int = 0
        self._level_idx: int = -1

        # ---- Connect ----
        self._time_slider.valueChanged.connect(self._on_time_changed)
        self._time_combo.currentIndexChanged.connect(self._on_combo_changed)
        self._depth_slider.valueChanged.connect(self._on_depth_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configure(
        self,
        ds: xr.Dataset,
        meta: SourceMeta,
        time_vals: np.ndarray,
        depth_cache: Dict[str, List[Tuple[int, float, float]]] | None = None,
    ) -> None:
        """Configure sliders for a specific dataset and source.

        Parameters
        ----------
        ds : xr.Dataset
        meta : SourceMeta
        time_vals : np.ndarray
            1-D array of datetime64 values.
        depth_cache : dict or None
            Pre-computed depth validity (from :func:`compute_depth_validity`).
        """
        self._time_vals = time_vals
        self._is_roms = (meta.source_name == "ROMS")
        self._depth_cache = depth_cache or {}

        n_t = len(time_vals)

        # ---- Time ----
        if self._is_roms and n_t <= 50:
            # ROMS — discrete combo box
            self._time_slider.hide()
            self._time_combo.clear()
            for i in range(n_t):
                label = pd.Timestamp(time_vals[i]).strftime("%Y-%m-%d")
                self._time_combo.addItem(label, i)
            self._time_combo.show()
            self._time_idx = 0
            self._time_value_lbl.setText("")
        else:
            # CMEMS — continuous slider
            self._time_combo.hide()
            self._time_slider.show()
            self._time_slider.setMinimum(0)
            self._time_slider.setMaximum(max(n_t - 1, 0))
            self._time_slider.setValue(0)
            self._time_idx = 0
            self._update_time_label(0)

        # ---- Depth ----
        vertical_type = meta.vertical_type
        if vertical_type == VerticalType.DEPTH:
            depth_name = meta.coord_map.get("depth", "depth")
            if depth_name in ds.dims or depth_name in ds.coords:
                n_d = ds.sizes.get(depth_name, 0)
                self._depth_slider.setMinimum(0)
                self._depth_slider.setMaximum(max(n_d - 1, 0))
                self._depth_slider.setValue(0)
                self._level_idx = 0
                self._depth_slider.setEnabled(True)
                self._depth_label.setText("Depth:")
                self._update_depth_label(0)
            else:
                self._depth_slider.setEnabled(False)
                self._depth_value_lbl.setText("—")
                self._level_idx = 0
        elif vertical_type == VerticalType.SIGMA:
            n_layers = ds.sizes.get("s_rho", 0)
            self._depth_slider.setMinimum(0)
            self._depth_slider.setMaximum(max(n_layers - 1, 0))
            self._depth_slider.setValue(n_layers - 1)  # surface = last index
            self._level_idx = n_layers - 1
            self._depth_slider.setEnabled(True)
            self._depth_label.setText("Sigma:")
            self._update_sigma_label(n_layers - 1, n_layers)
        else:
            self._depth_slider.setEnabled(False)
            self._depth_value_lbl.setText("(2-D)")
            self._level_idx = -1

    def set_variable_depth_cache(self, canon: str) -> None:
        """Switch the depth label to show meters for *canon*."""
        self._current_depth_cache = self._depth_cache.get(canon, [])
        idx = self._depth_slider.value()
        self._update_depth_label(idx)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def time_idx(self) -> int:
        return self._time_idx

    @property
    def level_idx(self) -> int:
        return self._level_idx

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_time_changed(self, idx: int) -> None:
        self._time_idx = idx
        self._update_time_label(idx)
        self.controls_changed.emit(self._time_idx, self._level_idx)

    def _on_combo_changed(self, idx: int) -> None:
        if idx < 0:
            return
        self._time_idx = self._time_combo.currentData()
        self.controls_changed.emit(self._time_idx, self._level_idx)

    def _on_depth_changed(self, idx: int) -> None:
        self._level_idx = idx
        self._update_depth_label(idx)
        self.controls_changed.emit(self._time_idx, self._level_idx)

    # ------------------------------------------------------------------
    # Label formatting
    # ------------------------------------------------------------------

    def _update_time_label(self, idx: int) -> None:
        if self._time_vals is not None and 0 <= idx < len(self._time_vals):
            ts = pd.Timestamp(self._time_vals[idx])
            self._time_value_lbl.setText(ts.strftime("%Y-%m-%d"))
        else:
            self._time_value_lbl.setText(f"[{idx}]")

    def _update_depth_label(self, idx: int) -> None:
        """Show depth in meters using pre-computed cache."""
        for di, meters, valid in self._current_depth_cache:
            if di == idx:
                self._depth_value_lbl.setText(f"{meters:.1f} m  ({valid:.0%})")
                return
        # Fallback — just show index
        self._depth_value_lbl.setText(f"level {idx}")

    def _update_sigma_label(self, idx: int, n_total: int) -> None:
        """Show sigma layer index relative to total (0=bottom, N=surface)."""
        self._depth_value_lbl.setText(f"s_rho[{idx}]  (0=bottom, {n_total - 1}=surface)")
