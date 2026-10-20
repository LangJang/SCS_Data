"""
Import / register new data — modal dialog.

Two registration kinds, both written to the SQLite registry (``registry.db``)
as equal (平权) rows and both *upserted* on the unique name/label key so that
re-importing an existing entry updates it instead of appending a duplicate:

- **Gridded NetCDF** — auto-detects the source via the adapter layer and
  builds a read template (``file_layout`` / ``time_axis`` / ``date_pattern``)
  that tells the main window how time is structured:

    * ``single``    — one file (its time axis may be ``internal`` or ``none``)
    * ``directory`` + ``per_file`` — one timestep per file, date in filename
    * ``directory`` + ``internal`` — several files, each internally multi-day

- **Point data (CSV/Excel)** — fishery scatter / station detail layers.

The grid summary fields are example metadata only (used for the search cards);
the actual plotting/export behaviour is governed by the read template.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QGroupBox, QLineEdit,
    QFileDialog, QMessageBox, QDialogButtonBox, QFrame,
)
from PyQt6.QtCore import Qt

from src.core import registry
from src.core.adapters import detect_source
from src.core.time_assembler import derive_date_from_filename


# strptime-style filename date patterns tried (in order) when guessing the
# per-file date template for a directory of single-timestep files.
_CANDIDATE_PATTERNS = [
    "roms_avg_%Y%m%dZ%H",
    "%Y%m%d",
    "%Y%m%d%H",
    "%Y-%m-%d",
    "%Y%j",
    "%Y%m",
]


class ImportDataDialog(QDialog):
    """Register a new gridded dataset or point overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import New Data")
        self.resize(560, 560)
        self.setModal(True)

        # Auto-detected grid metadata (dict or None until "Analyze" succeeds)
        self._detected: dict | None = None
        self._detected_files: list[Path] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ---- Kind selector ----
        kind_group = QGroupBox("Data Kind")
        kind_form = QFormLayout(kind_group)
        self._type_combo = QComboBox()
        self._type_combo.addItem("Gridded NetCDF", "gridded")
        self._type_combo.addItem("Point data (CSV / Excel)", "point")
        self._type_combo.currentIndexChanged.connect(self._on_kind_changed)
        kind_form.addRow("Type:", self._type_combo)
        layout.addWidget(kind_group)

        # ---- Gridded form ----
        layout.addWidget(self._build_gridded_group())

        # ---- Point form ----
        layout.addWidget(self._build_point_group())

        # ---- Buttons ----
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._on_kind_changed(0)

    def _build_gridded_group(self) -> QGroupBox:
        self._grid_group = QGroupBox("Gridded Dataset (NetCDF)")
        form = QFormLayout(self._grid_group)

        self._grid_name = QLineEdit()
        form.addRow("Name:", self._grid_name)

        self._grid_layout_combo = QComboBox()
        self._grid_layout_combo.addItem("Single file", "single")
        self._grid_layout_combo.addItem("Directory of files", "directory")
        self._grid_layout_combo.currentIndexChanged.connect(self._on_grid_layout_changed)
        form.addRow("Layout:", self._grid_layout_combo)

        path_row = QHBoxLayout()
        self._grid_path = QLineEdit()
        path_row.addWidget(self._grid_path, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_grid)
        path_row.addWidget(browse_btn)
        form.addRow("Path:", path_row)

        self._grid_pattern = QLineEdit("*.nc")
        form.addRow("File pattern:", self._grid_pattern)

        self._grid_keywords = QLineEdit()
        self._grid_keywords.setPlaceholderText("comma-separated")
        form.addRow("Keywords:", self._grid_keywords)

        analyze_btn = QPushButton("Analyze → auto-fill template")
        analyze_btn.clicked.connect(self._on_analyze)
        form.addRow(analyze_btn)

        self._grid_summary = QLabel("(select a file or directory, then Analyze)")
        self._grid_summary.setWordWrap(True)
        self._grid_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._grid_summary.setFrameShape(QFrame.Shape.StyledPanel)
        form.addRow("Detected:", self._grid_summary)

        self._grid_date_pattern = QLineEdit()
        self._grid_date_pattern.setPlaceholderText(
            "e.g. roms_avg_%Y%m%dZ%H  (only for per-file time)"
        )
        form.addRow("Date pattern:", self._grid_date_pattern)

        return self._grid_group

    def _build_point_group(self) -> QGroupBox:
        self._point_group = QGroupBox("Point Data (CSV / Excel)")
        form = QFormLayout(self._point_group)

        self._point_label = QLineEdit()
        form.addRow("Label:", self._point_label)

        self._point_type = QComboBox()
        self._point_type.addItem("Fishery (scatter)", "fishery")
        self._point_type.addItem("Station (detail)", "station")
        self._point_type.currentIndexChanged.connect(self._on_point_type_changed)
        form.addRow("Type:", self._point_type)

        path_row = QHBoxLayout()
        self._point_path = QLineEdit()
        path_row.addWidget(self._point_path, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_point)
        path_row.addWidget(browse_btn)
        form.addRow("Path:", path_row)

        self._point_keywords = QLineEdit()
        self._point_keywords.setPlaceholderText("comma-separated")
        form.addRow("Keywords:", self._point_keywords)

        self._point_summary = QLineEdit()
        form.addRow("Summary:", self._point_summary)

        # Station-only fields
        self._station_lat = QLineEdit()
        self._station_lon = QLineEdit()
        self._station_name = QLineEdit()
        form.addRow("Station lat:", self._station_lat)
        form.addRow("Station lon:", self._station_lon)
        form.addRow("Station name:", self._station_name)

        return self._point_group

    # ------------------------------------------------------------------
    # Kind / layout switching
    # ------------------------------------------------------------------

    def _on_kind_changed(self, idx: int) -> None:
        kind = self._type_combo.currentData()
        self._grid_group.setVisible(kind == "gridded")
        self._point_group.setVisible(kind == "point")

    def _on_grid_layout_changed(self, idx: int) -> None:
        is_dir = self._grid_layout_combo.currentData() == "directory"
        self._grid_pattern.setVisible(is_dir)

    def _on_point_type_changed(self, idx: int) -> None:
        is_station = self._point_type.currentData() == "station"
        for w in (self._station_lat, self._station_lon, self._station_name):
            w.setVisible(is_station)

    # ------------------------------------------------------------------
    # Browsing
    # ------------------------------------------------------------------

    def _on_browse_grid(self) -> None:
        if self._grid_layout_combo.currentData() == "single":
            path, _ = QFileDialog.getOpenFileName(
                self, "Select NetCDF file", "", "NetCDF (*.nc);;All files (*)"
            )
        else:
            path = QFileDialog.getExistingDirectory(self, "Select data directory")
        if path:
            self._grid_path.setText(path)

    def _on_browse_point(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select point data file", "",
            "Data (*.csv *.xlsx *.xls);;All files (*)"
        )
        if path:
            self._point_path.setText(path)

    # ------------------------------------------------------------------
    # Gridded analysis
    # ------------------------------------------------------------------

    def _on_analyze(self) -> None:
        try:
            files, layout, pattern = self._resolve_grid_files()
        except Exception as e:
            QMessageBox.warning(self, "Analyze", str(e))
            return

        try:
            first_ds = xr.open_dataset(files[0], engine="netcdf4")
            try:
                adapter_cls = detect_source(first_ds, str(files[0]))
                if adapter_cls is None:
                    raise RuntimeError("Could not detect data source.")
                meta = adapter_cls().adapt(first_ds)
                detected = self._extract_meta(first_ds, meta)
            finally:
                first_ds.close()
        except Exception as e:
            QMessageBox.warning(self, "Analyze", f"Failed to read data:\n{e}")
            return

        detected["file_layout"] = layout
        detected["file_pattern"] = pattern
        detected["path"] = str(files[0].parent) if layout == "single" else \
            str(Path(self._grid_path.text()))
        detected["files"] = files

        # Decide time_axis / date_pattern
        if layout == "single":
            detected["time_axis"] = "internal" if detected["time_dim"] else "none"
            detected["date_pattern"] = ""
        else:
            sizes = self._sample_time_sizes(files)
            if sizes and all(s == 1 for s in sizes):
                detected["time_axis"] = "per_file"
                detected["date_pattern"] = self._guess_date_pattern(files) or ""
            else:
                detected["time_axis"] = "internal"
                detected["date_pattern"] = ""
                if sizes and any(s != 1 for s in sizes) and any(s == 1 for s in sizes):
                    detected["_warn_mixed"] = True

            # For per_file data the real time range lives in the filenames,
            # not the (single-timestep) file contents.
            if detected["time_axis"] == "per_file" and detected["date_pattern"]:
                dates = [
                    d for d in
                    (derive_date_from_filename(f, detected["date_pattern"])
                     for f in files)
                    if d is not None
                ]
                if dates:
                    detected["time_start"] = min(dates).strftime("%Y-%m-%d")
                    detected["time_end"] = max(dates).strftime("%Y-%m-%d")

        self._detected = detected
        self._detected_files = files

        # Pre-fill name if empty
        if not self._grid_name.text().strip():
            self._grid_name.setText(detected.get("suggested_name", ""))

        # Reflect date pattern in the field (only meaningful for per_file)
        self._grid_date_pattern.setText(detected.get("date_pattern", ""))

        self._grid_summary.setText(self._format_detected(detected))

    def _resolve_grid_files(self) -> tuple[list[Path], str, str]:
        path_text = self._grid_path.text().strip()
        if not path_text:
            raise ValueError("Select a file or directory first.")
        path = Path(path_text)

        if self._grid_layout_combo.currentData() == "single":
            if not path.is_file():
                raise ValueError(f"Not a file: {path}")
            return [path], "single", path.name

        if not path.is_dir():
            raise ValueError(f"Not a directory: {path}")
        pattern = self._grid_pattern.text().strip() or "*.nc"
        files = sorted(path.glob(pattern))
        if not files:
            raise ValueError(f"No files matching '{pattern}' in {path}")
        return files, "directory", pattern

    def _extract_meta(self, ds: xr.Dataset, meta) -> dict:
        """Pull grid metadata from an adapted dataset into a raw-dict fragment."""
        lon_name = meta.coord_map.get("longitude")
        lat_name = meta.coord_map.get("latitude")

        # Spatial extent
        lon_min = lon_max = lat_min = lat_max = 0.0
        native_res = 0.05
        if lon_name and lon_name in ds.coords:
            lon_vals = ds[lon_name].values
            lon_min = float(np.nanmin(lon_vals))
            lon_max = float(np.nanmax(lon_vals))
            if lon_vals.ndim == 1 and len(lon_vals) >= 2:
                native_res = float(abs(lon_vals[1] - lon_vals[0]))
        if lat_name and lat_name in ds.coords:
            lat_vals = ds[lat_name].values
            lat_min = float(np.nanmin(lat_vals))
            lat_max = float(np.nanmax(lat_vals))

        # Time
        time_dim = meta.time_dim
        time_start = time_end = ""
        if time_dim and time_dim in ds.coords and len(ds[time_dim]) > 0:
            t_vals = ds[time_dim].values
            time_start = pd.Timestamp(t_vals[0]).strftime("%Y-%m-%d")
            time_end = pd.Timestamp(t_vals[-1]).strftime("%Y-%m-%d")

        # Vertical
        vert_name = meta.vertical_type.name.lower()  # depth / sigma / none
        vertical_type = "" if vert_name == "none" else vert_name
        vertical_layers = 0
        depth_values: list[float] = []
        depth_name = meta.coord_map.get("depth")
        if depth_name and depth_name in ds.dims:
            depth_values = [
                float(d) for d in ds[depth_name].values if float(d) >= 0
            ]
            vertical_layers = len(depth_values)
        elif "s_rho" in ds.dims:
            vertical_layers = int(ds.sizes["s_rho"])

        variables = sorted(meta.available_variables())

        return {
            "source": meta.source_name,
            "variables": variables,
            "time_dim": time_dim,
            "time_start": time_start,
            "time_end": time_end,
            "vertical_type": vertical_type,
            "vertical_layers": vertical_layers,
            "depth_values": depth_values,
            "lon_min": lon_min,
            "lon_max": lon_max,
            "lat_min": lat_min,
            "lat_max": lat_max,
            "native_res": round(native_res, 6),
            "suggested_name": meta.source_name,
        }

    def _sample_time_sizes(self, files: list[Path], n: int = 3) -> list[int]:
        """Return the time-dimension size of the first *n* files (0 = no time)."""
        sizes: list[int] = []
        for fp in files[:n]:
            try:
                ds = xr.open_dataset(fp, engine="netcdf4")
                try:
                    adapter_cls = detect_source(ds, str(fp))
                    m = adapter_cls().adapt(ds) if adapter_cls else None
                    td = m.time_dim if m else None
                    sizes.append(int(ds.sizes[td]) if td and td in ds.dims else 0)
                finally:
                    ds.close()
            except Exception:
                sizes.append(0)
        return sizes

    def _guess_date_pattern(self, files: list[Path]) -> str | None:
        """Find the first strptime-style pattern that matches every sampled file."""
        sample = files[:4]
        for pattern in _CANDIDATE_PATTERNS:
            if all(derive_date_from_filename(fp, pattern) is not None
                   for fp in sample):
                return pattern
        return None

    def _format_detected(self, d: dict) -> str:
        lines = [
            f"Source: {d['source']}",
            f"Variables: {', '.join(d['variables']) or '(none)'}",
            f"Vertical: {d['vertical_type'] or 'none'}"
            f" ({d['vertical_layers']} layers)",
            f"Spatial: lon [{d['lon_min']:.2f}, {d['lon_max']:.2f}]  "
            f"lat [{d['lat_min']:.2f}, {d['lat_max']:.2f}]",
            f"Time: {d['time_start']} → {d['time_end']}",
            f"Layout: {d['file_layout']}  |  Time axis: {d['time_axis']}",
        ]
        if d.get("time_axis") == "per_file":
            lines.append(
                f"Date pattern: {d['date_pattern'] or '(NOT FOUND — must set)'}"
            )
        if d.get("_warn_mixed"):
            lines.append("⚠ Mixed per-file time sizes — treating as internal.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        kind = self._type_combo.currentData()
        try:
            if kind == "gridded":
                self._save_gridded()
            else:
                self._save_point()
        except Exception as e:
            QMessageBox.warning(self, "Import", str(e))
            return
        self.accept()

    def _save_gridded(self) -> None:
        name = self._grid_name.text().strip()
        if not name:
            raise ValueError("Enter a dataset name.")

        if self._detected is None:
            raise ValueError("Run 'Analyze' first to build the read template.")

        layout = self._detected["file_layout"]
        time_axis = self._detected["time_axis"]
        date_pattern = self._grid_date_pattern.text().strip()

        if time_axis == "per_file" and not date_pattern:
            raise ValueError(
                "This directory has one timestep per file, so a date pattern "
                "is required (e.g. roms_avg_%Y%m%dZ%H)."
            )

        keywords = _split_csv(self._grid_keywords.text())
        depth_values = self._detected["depth_values"]
        vertical_range = (
            [min(depth_values), max(depth_values)] if depth_values else []
        )

        raw = {
            "name": name,
            "source": self._detected["source"],
            "keywords": keywords,
            "variables": self._detected["variables"],
            "resolution": {
                "default": self._detected["native_res"],
                "available": [self._detected["native_res"]],
            },
            "spatial": {
                "lon": {"min": self._detected["lon_min"],
                        "max": self._detected["lon_max"]},
                "lat": {"min": self._detected["lat_min"],
                        "max": self._detected["lat_max"]},
            },
            "temporal": {
                "start": self._detected["time_start"],
                "end": self._detected["time_end"],
                "frequency": "",
            },
            "vertical": {
                "type": self._detected["vertical_type"],
                "layers": self._detected["vertical_layers"],
                "range": vertical_range,
                "depth_values": depth_values,
            },
            "path": self._detected["path"],
            "file_pattern": self._detected["file_pattern"],
            "hidden": False,
            "file_layout": layout,
            "time_axis": time_axis,
            "date_pattern": date_pattern,
        }

        registry.insert_dataset(raw)

    def _save_point(self) -> None:
        label = self._point_label.text().strip()
        path = self._point_path.text().strip()
        if not label:
            raise ValueError("Enter a label.")
        if not path:
            raise ValueError("Select a data file.")

        otype = self._point_type.currentData()
        raw = {
            "label": label,
            "type": otype,
            "path": path,
            "keywords": _split_csv(self._point_keywords.text()),
            "summary": self._point_summary.text().strip(),
        }
        if otype == "station":
            raw["station_lat"] = _safe_float(self._station_lat.text())
            raw["station_lon"] = _safe_float(self._station_lon.text())
            raw["station_name"] = self._station_name.text().strip()

        registry.insert_overlay(raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_csv(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def _safe_float(text: str) -> float:
    try:
        return float(text.strip())
    except ValueError:
        return 0.0
