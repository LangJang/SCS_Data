"""
Export dialog — spatial crop + resolution downsampling + multi-format save.

Supports: PNG, JPG, TIFF, PDF (map image), NetCDF, CSV (data subset).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QGroupBox,
    QFileDialog, QMessageBox, QDialogButtonBox, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView,
)
from PyQt6.QtCore import Qt

from src.core.canonical import SourceMeta
from src.core.export import to_csv, to_netcdf


FORMATS = [
    ("PNG Image (*.png)",   ".png",  "image"),
    ("JPEG Image (*.jpg)",  ".jpg",  "image"),
    ("TIFF Image (*.tiff)", ".tiff", "image"),
    ("PDF Document (*.pdf)", ".pdf", "image"),
    ("NetCDF (*.nc)",       ".nc",   "data"),
    ("CSV Table (*.csv)",   ".csv",  "data"),
]


class ExportDialog(QDialog):
    """Export the current map or a spatially-cropped data subset.

    Data export uses *real* spatial slicing (``sel(slice)``) for
    1-D rectilinear grids, plus optional ``coarsen().mean()``
    downsampling to the target resolution selected in the param panel.
    """

    def __init__(
        self,
        parent,
        ds: xr.Dataset,
        meta: SourceMeta,
        canonical_name: str,
        time_start_idx: int,
        time_end_idx: int,
        depth_options: list[tuple[int, str]],  # [(idx, label), ...]
        *,
        north: float = 90.0,
        south: float = -90.0,
        east: float = 180.0,
        west: float = -180.0,
        auto_name: str = "export",
        default_dir: str = "",
        target_resolution: float = 0.05,
        overlay_df = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.resize(550, 440)
        self.setModal(True)

        self._ds = ds
        self._meta = meta
        self._canon = canonical_name
        self._time_start_idx = time_start_idx
        self._time_end_idx = time_end_idx
        self._depth_options = depth_options
        self._north = north
        self._south = south
        self._east = east
        self._west = west
        self._auto_name = auto_name
        self._default_dir = default_dir or str(Path.home() / "Desktop")
        self._target_res = target_resolution
        self._overlay_df = overlay_df

        # Compute native resolution from the dataset
        lon_name = meta.coord_map.get("longitude", "longitude")
        self._lon_name = lon_name
        self._lat_name = meta.coord_map.get("latitude", "latitude")
        self._native_res = self._compute_native_res()

        self._init_ui()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_native_res(self) -> float:
        """Return native grid spacing in degrees."""
        da = self._ds[self._meta.source_var(self._canon)]
        lon_vals = da[self._lon_name].values
        if lon_vals.ndim == 1 and len(lon_vals) >= 2:
            return float(abs(lon_vals[1] - lon_vals[0]))
        return 0.05  # fallback

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
        form.addRow("Region:", QLabel(
            f"N={self._north:.2f}  S={self._south:.2f}  "
            f"E={self._east:.2f}  W={self._west:.2f}"
        ))
        layout.addWidget(summary)

        # ---- Output Settings ----
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

        layout.addWidget(fmt_group)

        # ---- Depth selection (multi-select, data formats only) ----
        depth_group = QGroupBox("Depth Levels (multi-select)")
        depth_layout = QVBoxLayout(depth_group)
        self._depth_list = QListWidget()
        self._depth_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._depth_list.setMaximumHeight(140)
        for idx, label in self._depth_options:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setSelected(True)  # all selected by default
            self._depth_list.addItem(item)
        # Select all / Deselect all buttons
        btn_row = QHBoxLayout()
        all_btn = QPushButton("Select All")
        all_btn.clicked.connect(lambda: self._depth_list.selectAll())
        none_btn = QPushButton("Deselect All")
        none_btn.clicked.connect(lambda: self._depth_list.clearSelection())
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addStretch()
        depth_layout.addWidget(self._depth_list)
        depth_layout.addLayout(btn_row)
        layout.addWidget(depth_group)

        # Resolution (coarsen target, read-only)
        res_group = QGroupBox("Resolution")
        res_layout = QFormLayout(res_group)
        stride = max(1, int(round(self._target_res / self._native_res))) \
            if self._native_res > 0 else 1
        self._res_label = QLabel(
            f"{self._native_res}° → {self._target_res}°  (coarsen factor: ×{stride})"
        )
        self._res_coarsen_stride = stride
        res_layout.addRow("Downsample:", self._res_label)
        layout.addWidget(res_group)

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
        """Toggle resolution label for image vs data formats."""
        _, cat = self._format_combo.currentData()
        self._res_label.setVisible(cat == "data")

    def _on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if path:
            self._path_edit.setText(path)

    @property
    def save_dir(self) -> str:
        return self._path_edit.text()

    def _selected_depth_indices(self) -> list[int]:
        """Return sorted list of selected depth level indices."""
        indices = []
        for item in self._depth_list.selectedItems():
            indices.append(item.data(Qt.ItemDataRole.UserRole))
        return sorted(indices)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

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

    def _save_image(self, path: Path) -> None:
        """Save the current canvas figure."""
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, '_preview'):
                parent._preview.canvas.figure.savefig(
                    path, dpi=200, bbox_inches="tight"
                )
                return
            parent = parent.parent()
        raise RuntimeError("Could not find map canvas to export.")

    def _save_data(self, path: Path) -> None:
        """Slice, crop, coarsen, and save the data subset."""
        meta = self._meta
        ds = self._ds
        src_var = meta.source_var(self._canon)
        da = ds[src_var]

        # -- 1. Slice time to the selected range --
        time_dim = meta.time_dim
        if time_dim and time_dim in da.dims:
            n_t = da.sizes[time_dim]
            t0 = max(0, self._time_start_idx)
            t1 = min(n_t, self._time_end_idx + 1)  # +1 = inclusive
            da = da.isel({time_dim: slice(t0, t1)})

        # -- 2. Slice depth to selected levels --
        depth_name = meta.coord_map.get("depth", "depth")
        selected_depths = self._selected_depth_indices()
        if not selected_depths:
            raise ValueError("No depth levels selected for export.")
        if depth_name in da.dims:
            da = da.isel({depth_name: selected_depths})
        elif "s_rho" in da.dims:
            da = da.isel({"s_rho": selected_depths})

        # -- 3. Spatial crop (real slicing for 1-D coords) --
        if da[self._lon_name].ndim == 1 and da[self._lat_name].ndim == 1:
            da = da.sel({
                self._lon_name: slice(self._west, self._east),
                self._lat_name: slice(self._south, self._north),
            })
        else:
            raise ValueError(
                "Spatial cropping is only supported for 1-D rectilinear grids. "
                "This dataset uses 2-D coordinates."
            )

        # -- 4. Coarsen to target resolution --
        stride = self._res_coarsen_stride
        if stride > 1:
            spatial_dims = [
                d for d in da.dims
                if d in (self._lon_name, self._lat_name, "longitude", "latitude")
            ]
            da = da.coarsen(
                {d: stride for d in spatial_dims},
                boundary="trim",
            ).mean()

        # -- 5. Add fishery overlay layers (NetCDF only) --
        subset = da.to_dataset()

        if path.suffix == ".nc" and self._overlay_df is not None and len(self._overlay_df) > 0:
            from src.core.fishery_raster import rasterize_fishery

            lon_arr = subset[self._lon_name].values
            lat_arr = subset[self._lat_name].values
            fishery_layers = rasterize_fishery(self._overlay_df, lon_arr, lat_arr)

            for layer_name, arr in fishery_layers.items():
                subset[layer_name] = (
                    [dim for dim in ["latitude", "longitude"]
                     if dim in subset.dims],
                    arr,
                )

        # -- 6. Write --
        if path.suffix == ".nc":
            to_netcdf(subset, path)
        else:
            df = subset.to_dataframe().reset_index()
            if src_var in df.columns:
                df = df.dropna(subset=[src_var])
            to_csv(df, path)
