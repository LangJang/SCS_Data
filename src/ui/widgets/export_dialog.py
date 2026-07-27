"""
Export dialog for subset data download.

Provides a :class:`ExportDialog` that guides the user through:
1. Review current selection (variable, time, depth, spatial region)
2. Choose output format (PNG / NetCDF / CSV)
3. Optional downsampling stride
4. Save to file
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QSpinBox, QPushButton, QGroupBox,
    QFileDialog, QMessageBox, QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from src.core.canonical import SourceMeta
from src.core.export import to_csv, to_netcdf
from src.core.preprocess import subset_bbox


class ExportDialog(QDialog):
    """Export the current map selection to a file.

    Parameters
    ----------
    parent : QWidget or None
    ds : xr.Dataset
        Full source dataset.
    meta : SourceMeta
    canonical_name : str
        Currently selected canonical variable.
    time_idx : int
        Current time index.
    level_idx : int
        Current depth/level index.
    bbox : (lon_min, lon_max, lat_min, lat_max) or None
        Optional spatial bounding box from map selection.
    """

    FORMATS = ["NetCDF (.nc)", "CSV (.csv)"]

    def __init__(
        self,
        parent,
        ds: xr.Dataset,
        meta: SourceMeta,
        canonical_name: str,
        time_idx: int,
        level_idx: int,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Data Subset")
        self.resize(450, 350)
        self.setModal(True)

        self._ds = ds
        self._meta = meta
        self._canon = canonical_name
        self._time_idx = time_idx
        self._level_idx = level_idx
        self._bbox = bbox
        self._output_path: str = ""

        self._init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ---- Selection summary ----
        summary = QGroupBox("Current Selection")
        form = QFormLayout(summary)

        form.addRow("Variable:", QLabel(
            f"{self._meta.display_label(self._canon)} ({self._canon})"
        ))
        form.addRow("Source:", QLabel(self._meta.source_name))
        form.addRow("Time index:", QLabel(str(self._time_idx)))
        form.addRow("Level index:", QLabel(str(self._level_idx)))

        if self._bbox:
            form.addRow("Region:", QLabel(
                f"lon=[{self._bbox[0]:.4f}, {self._bbox[1]:.4f}]  "
                f"lat=[{self._bbox[2]:.4f}, {self._bbox[3]:.4f}]"
            ))
        else:
            form.addRow("Region:", QLabel("Full domain"))

        layout.addWidget(summary)

        # ---- Format ----
        fmt_group = QGroupBox("Output Format")
        fmt_layout = QFormLayout(fmt_group)

        self._format_combo = QComboBox()
        self._format_combo.addItems(self.FORMATS)
        fmt_layout.addRow("Format:", self._format_combo)

        self._stride_spin = QSpinBox()
        self._stride_spin.setMinimum(1)
        self._stride_spin.setMaximum(10)
        self._stride_spin.setValue(1)
        self._stride_spin.setToolTip(
            "Take every Nth grid point (1 = full resolution, "
            "2 = half resolution, etc.)"
        )
        fmt_layout.addRow("Downsample stride:", self._stride_spin)

        layout.addWidget(fmt_group)

        # ---- Buttons ----
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_export)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Export logic
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        """Execute the export based on user selections."""
        fmt = self._format_combo.currentText()
        stride = self._stride_spin.value()

        # Determine file extension and filter
        if "NetCDF" in fmt:
            ext_filter = "NetCDF Files (*.nc)"
            default_name = f"{self._canon}_subset.nc"
        else:
            ext_filter = "CSV Files (*.csv)"
            default_name = f"{self._canon}_subset.csv"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Subset As", default_name, ext_filter,
        )
        if not path:
            return

        try:
            subset = self._build_subset(stride)

            if "NetCDF" in fmt:
                to_netcdf(subset, path)
            else:
                # Convert to DataFrame and save
                df = subset.to_dataframe().reset_index()
                # Drop rows where the variable is NaN to reduce file size
                src_var = self._meta.source_var(self._canon)
                if src_var in df.columns:
                    df = df.dropna(subset=[src_var])
                to_csv(df, path)

            QMessageBox.information(
                self, "Export Complete",
                f"Subset saved to:\n{path}",
            )
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _build_subset(self, stride: int) -> xr.Dataset:
        """Build the xarray Dataset subset from the current selection."""
        ds = self._ds
        meta = self._meta
        src_var = meta.source_var(self._canon)
        da = ds[src_var]

        # Slice time
        time_dim = meta.time_dim
        if time_dim and time_dim in da.dims:
            da = da.isel({time_dim: self._time_idx})

        # Slice vertical
        depth_name = meta.coord_map.get("depth", "depth")
        if depth_name in da.dims:
            da = da.isel({depth_name: self._level_idx})
        elif "s_rho" in da.dims:
            da = da.isel({"s_rho": self._level_idx})

        # Spatial subset (bbox)
        if self._bbox:
            lon_min, lon_max, lat_min, lat_max = self._bbox
            lon_name = meta.coord_map.get("longitude", "longitude")
            lat_name = meta.coord_map.get("latitude", "latitude")

            if lon_name in ds.coords:
                da = da.where(
                    (ds[lon_name] >= lon_min) & (ds[lon_name] <= lon_max),
                    drop=True,
                )
            if lat_name in ds.coords:
                da = da.where(
                    (ds[lat_name] >= lat_min) & (ds[lat_name] <= lat_max),
                    drop=True,
                )

        # Downsample
        if stride > 1:
            da = da.isel(
                {dim: slice(None, None, stride)
                 for dim in da.dims if dim not in (time_dim, depth_name, "s_rho")}
            )

        return da.to_dataset()
