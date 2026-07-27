"""
Time-series extraction popup dialog.

Opened when the user clicks a point on the :class:`MapCanvas`.
Extracts the full time series at the nearest grid point using
:func:`~src.core.roms_utils.extract_point` and renders it with
:func:`~src.viz.time_plotter.plot_timeseries`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog,
)
from PyQt6.QtCore import Qt

from src.core.canonical import SourceMeta
from src.core.roms_utils import extract_point, TimeseriesResult
from src.viz.time_plotter import plot_timeseries


class TimeseriesPopup(QDialog):
    """Modal dialog showing the time series at a clicked map location.

    Parameters
    ----------
    parent : QWidget or None
    ds : xr.Dataset
        Dataset containing the multi-timestep variable.
    meta : SourceMeta
    canonical_name : str
    lon, lat : float
        Clicked geographic coordinates.
    missing_indices : list[int] or None
        Indices of days *before* a gap (for shading in the plot).
    """

    def __init__(
        self,
        parent,
        ds: xr.Dataset,
        meta: SourceMeta,
        canonical_name: str,
        lon: float,
        lat: float,
        missing_indices: list[int] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            f"{meta.display_label(canonical_name)} at ({lon:.4f}, {lat:.4f})"
        )
        self.resize(800, 500)
        self.setModal(True)

        # ---- Extract time series ----
        try:
            ts: TimeseriesResult = extract_point(ds, meta, canonical_name, lon, lat)
        except Exception as e:
            error_label = QLabel(f"Extraction failed:\n{e}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout = QVBoxLayout(self)
            layout.addWidget(error_label)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)
            return

        # ---- Matplotlib figure ----
        fig = plot_timeseries(
            ts,
            missing_indices=missing_indices,
            output_path=None,  # Don't save — embed instead
            show=False,
        )

        # ---- Canvas ----
        canvas = FigureCanvasQTAgg(fig)
        canvas.setParent(self)

        # ---- Toolbar ----
        toolbar = NavToolbar(canvas, self)

        # ---- Save button ----
        save_btn = QPushButton("Save as PNG...")
        save_btn.clicked.connect(lambda: self._save_figure(fig))

        btn_row = QHBoxLayout()
        btn_row.addWidget(toolbar)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)

        # ---- Layout ----
        layout = QVBoxLayout(self)
        layout.addWidget(canvas)
        layout.addLayout(btn_row)

    def _save_figure(self, fig) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Time Series as PNG",
            "timeseries.png", "PNG Images (*.png)",
        )
        if path:
            fig.savefig(path, dpi=200, bbox_inches="tight")
