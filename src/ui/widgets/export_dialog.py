"""
Export dialog for data subset and figure download.

Supports: PNG, JPG, TIFF, PDF (map image), NetCDF, CSV (data subset).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QSpinBox, QPushButton, QGroupBox,
    QFileDialog, QMessageBox, QDialogButtonBox, QLineEdit,
)
from PyQt6.QtCore import Qt

from src.core.canonical import SourceMeta
from src.core.export import to_csv, to_netcdf


# Format definitions: (label, extension, category)
FORMATS = [
    ("PNG Image (*.png)",   ".png",  "image"),
    ("JPEG Image (*.jpg)",  ".jpg",  "image"),
    ("TIFF Image (*.tiff)", ".tiff", "image"),
    ("PDF Document (*.pdf)","*.pdf", "image"),
    ("NetCDF (*.nc)",       ".nc",   "data"),
    ("CSV Table (*.csv)",   ".csv",  "data"),
]

class ExportDialog(QDialog):
    """Export the current map or data subset to a file.

    Parameters
    ----------
    auto_name : str
        Pre-filled filename stem (e.g. "SST_2023-01-01_2023-01-31_SCS").
    """

    def __init__(
        self,
        parent,
        ds: xr.Dataset,
        meta: SourceMeta,
        canonical_name: str,
        time_idx: int,
        level_idx: int,
        *,
        north: float = 90.0,
        south: float = -90.0,
        east: float = 180.0,
        west: float = -180.0,
        auto_name: str = "export",
        default_dir: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.resize(480, 380)
        self.setModal(True)

        self._ds = ds
        self._meta = meta
        self._canon = canonical_name
        self._time_idx = time_idx
        self._level_idx = level_idx
        self._north = north
        self._south = south
        self._east = east
        self._west = west
        self._auto_name = auto_name
        self._default_dir = default_dir or str(Path.home() / "Desktop")

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
        form.addRow("Region:", QLabel(
            f"N={self._north:.2f}  S={self._south:.2f}  "
            f"E={self._east:.2f}  W={self._west:.2f}"
        ))
        layout.addWidget(summary)

        # ---- Format ----
        fmt_group = QGroupBox("Output Settings")
        fmt_layout = QFormLayout(fmt_group)

        self._format_combo = QComboBox()
        for label, ext, cat in FORMATS:
            self._format_combo.addItem(label, (ext, cat))
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_layout.addRow("Format:", self._format_combo)

        # Filename
        name_row = QHBoxLayout()
        self._name_edit = QLineEdit(self._auto_name)
        name_row.addWidget(QLabel("Name:"))
        name_row.addWidget(self._name_edit)
        fmt_layout.addRow(name_row)

        # Save path
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit(self._default_dir)
        path_row.addWidget(QLabel("Save to:"))
        path_row.addWidget(self._path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(browse_btn)
        fmt_layout.addRow(path_row)

        # Downsample (data formats only)
        self._stride_spin = QSpinBox()
        self._stride_spin.setMinimum(1)
        self._stride_spin.setMaximum(10)
        self._stride_spin.setValue(1)
        self._stride_spin.setToolTip("Take every Nth grid point (1 = full resolution)")
        fmt_layout.addRow("Downsample:", self._stride_spin)

        layout.addWidget(fmt_group)

        # ---- Buttons ----
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_format_changed(self, idx: int) -> None:
        """Toggle downsample availability for image vs data formats."""
        _, cat = self._format_combo.currentData()
        self._stride_spin.setEnabled(cat == "data")

    @property
    def save_dir(self) -> str:
        """The last save directory chosen by the user."""
        return self._path_edit.text()

    def _on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if path:
            self._path_edit.setText(path)

    def _on_save(self) -> None:
        ext, cat = self._format_combo.currentData()
        name = self._name_edit.text().strip() or "export"
        save_dir = Path(self._path_edit.text())
        save_dir.mkdir(parents=True, exist_ok=True)
        full_path = save_dir / f"{name}{ext}"

        try:
            if cat == "image":
                self._save_image(full_path)
            else:
                self._save_data(full_path)

            QMessageBox.information(self, "Export Complete",
                                    f"Saved to:\n{full_path}")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))

    # ------------------------------------------------------------------
    # Save methods
    # ------------------------------------------------------------------

    def _save_image(self, path: Path) -> None:
        """Save the current canvas figure."""
        parent = self.parent()
        # Walk up to find the MainWindow
        while parent is not None:
            if hasattr(parent, '_preview'):
                parent._preview.canvas.figure.savefig(
                    path, dpi=200, bbox_inches="tight"
                )
                return
            parent = parent.parent()
        raise RuntimeError("Could not find map canvas to export.")

    def _save_data(self, path: Path) -> None:
        """Build subset and save as NetCDF or CSV."""
        ds = self._ds
        meta = self._meta
        src_var = meta.source_var(self._canon)
        da = ds[src_var]
        stride = self._stride_spin.value()

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

        # Spatial subset (NaN-mask outside bounds, works for both 1-D and 2-D coords)
        lon_name = meta.coord_map.get("longitude", "longitude")
        lat_name = meta.coord_map.get("latitude", "latitude")
        lon_arr = ds[lon_name].values
        lat_arr = ds[lat_name].values

        if lon_arr.ndim == 2 and lat_arr.ndim == 2:
            mask = ((lon_arr < self._west) | (lon_arr > self._east) |
                    (lat_arr < self._south) | (lat_arr > self._north))
        else:
            lon2d, lat2d = np.meshgrid(lon_arr, lat_arr)
            mask = ((lon2d < self._west) | (lon2d > self._east) |
                    (lat2d < self._south) | (lat2d > self._north))

        vals = da.values.astype(float).copy()
        vals[mask] = np.nan
        da.values = vals

        # Downsample
        if stride > 1:
            exclude = {time_dim, depth_name, "s_rho"}
            da = da.isel({
                dim: slice(None, None, stride)
                for dim in da.dims if dim not in exclude
            })

        subset = da.to_dataset()

        if path.suffix == ".nc":
            to_netcdf(subset, path)
        else:
            df = subset.to_dataframe().reset_index()
            src_var_name = meta.source_var(self._canon)
            if src_var_name in df.columns:
                df = df.dropna(subset=[src_var_name])
            to_csv(df, path)
