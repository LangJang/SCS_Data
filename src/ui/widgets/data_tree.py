"""
Data-source tree view with metadata panel.

Provides :class:`DataTree` — a composite widget with a ``QTreeView``
(Source → File → Variable) and a ``QTextBrowser`` showing metadata
for the selected item.

Signals
------
variable_selected(key, canonical_name, meta, ds)
    Emitted when the user clicks a leaf (variable) node.  The main
    window connects this to :meth:`MapCanvas.update_map`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import xarray as xr

from PyQt6.QtWidgets import (
    QVBoxLayout, QWidget, QTreeView, QTextBrowser, QSplitter,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem

from src.core.canonical import SourceMeta


# ---------------------------------------------------------------------------
# Tree node roles
# ---------------------------------------------------------------------------

ROLE_SOURCE = Qt.ItemDataRole.UserRole + 1   # "ROMS" | "CMEMS"
ROLE_KEY    = Qt.ItemDataRole.UserRole + 2   # dataset key (filename)
ROLE_CANON  = Qt.ItemDataRole.UserRole + 3   # canonical variable name
ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 4  # "source" | "file" | "variable"


# ---------------------------------------------------------------------------
# DataTree
# ---------------------------------------------------------------------------

class DataTree(QWidget):
    """Data-source browser: tree + metadata panel.

    Parameters
    ----------
    parent : QWidget or None
    """

    variable_selected = pyqtSignal(str, str, SourceMeta, xr.Dataset)
    """Emits ``(key, canonical_name, meta, ds)`` when a variable is clicked."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ---- Tree ----
        self._tree = QTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)

        self._model = QStandardItemModel()
        self._tree.setModel(self._model)
        self._tree.clicked.connect(self._on_item_clicked)

        # ---- Metadata panel ----
        self._meta_panel = QTextBrowser()
        self._meta_panel.setMaximumHeight(180)
        self._meta_panel.setPlaceholderText("Select a variable to see metadata.")

        # ---- Layout (tree above, metadata below) ----
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._meta_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # ---- Internal state ----
        self._pipeline: object | None = None
        self._metas: Dict[str, SourceMeta] = {}
        self._datasets: Dict[str, xr.Dataset] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_pipeline(self, pipeline) -> None:
        """Populate the tree from a :class:`~src.core.pipeline.MarineDataPipeline`.

        Parameters
        ----------
        pipeline : MarineDataPipeline
            Must have :meth:`load_all` already called.
        """
        self._pipeline = pipeline
        self._model.clear()
        self._metas.clear()
        self._datasets.clear()

        sources = pipeline.sources()  # {"ROMS": [...], "CMEMS": [...]}

        for source_name, keys in sources.items():
            if not keys:
                continue

            # Source node
            src_item = QStandardItem(f"{source_name}  ({len(keys)} files)")
            src_item.setData(source_name, ROLE_SOURCE)
            src_item.setData("source", ROLE_NODE_TYPE)
            src_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._model.appendRow(src_item)

            for key in sorted(keys):
                try:
                    meta = pipeline.meta_for(key)
                    ds = pipeline.ds_for(key)
                except KeyError:
                    continue

                self._metas[key] = meta
                self._datasets[key] = ds

                # File node
                file_item = QStandardItem(key)
                file_item.setData(source_name, ROLE_SOURCE)
                file_item.setData(key, ROLE_KEY)
                file_item.setData("file", ROLE_NODE_TYPE)
                file_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                src_item.appendRow(file_item)

                # Variable leaf nodes
                for canon in sorted(meta.available_variables()):
                    label = meta.display_label(canon)
                    units = meta.standard_units(canon)
                    text = f"{label}  ({units})" if units else label

                    var_item = QStandardItem(text)
                    var_item.setData(source_name, ROLE_SOURCE)
                    var_item.setData(key, ROLE_KEY)
                    var_item.setData(canon, ROLE_CANON)
                    var_item.setData("variable", ROLE_NODE_TYPE)
                    file_item.appendRow(var_item)

        self._tree.expandAll()

    def clear(self) -> None:
        """Remove all items from the tree."""
        self._model.clear()
        self._metas.clear()
        self._datasets.clear()
        self._meta_panel.clear()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_clicked(self, index) -> None:
        """Handle tree item click — show metadata; emit signal for variables."""
        node_type = self._model.data(index, ROLE_NODE_TYPE)
        if node_type == "variable":
            source = self._model.data(index, ROLE_SOURCE)
            key = self._model.data(index, ROLE_KEY)
            canon = self._model.data(index, ROLE_CANON)
            meta = self._metas.get(key)
            ds = self._datasets.get(key)
            if meta is None or ds is None:
                return
            self._show_variable_meta(key, canon, meta, ds)
            self.variable_selected.emit(key, canon, meta, ds)

        elif node_type == "file":
            key = self._model.data(index, ROLE_KEY)
            meta = self._metas.get(key)
            ds = self._datasets.get(key)
            if meta is not None and ds is not None:
                self._show_file_meta(key, meta, ds)

        elif node_type == "source":
            source = self._model.data(index, ROLE_SOURCE)
            self._show_source_meta(source)

    # ------------------------------------------------------------------
    # Metadata formatting
    # ------------------------------------------------------------------

    def _show_variable_meta(
        self, key: str, canon: str, meta: SourceMeta, ds: xr.Dataset,
    ) -> None:
        """Display metadata for a single variable."""
        src_var = meta.source_var(canon)
        da = ds[src_var]

        lines = [
            f"<b>Variable:</b> {meta.display_label(canon)} ({canon})",
            f"<b>Source var:</b> {src_var}",
            f"<b>Units:</b> {meta.standard_units(canon) or '—'}",
            f"<b>Dimensions:</b> {dict(da.sizes)}",
        ]

        # Data range (first timestep)
        try:
            vals = da.isel({meta.time_dim: 0}).values if meta.time_dim and meta.time_dim in da.dims else da.values
            lines.append(
                f"<b>Range:</b> [{np.nanmin(vals):.4g}, {np.nanmax(vals):.4g}]"
            )
            valid = float((~np.isnan(vals)).mean()) * 100
            lines.append(f"<b>Valid data:</b> {valid:.1f}% of grid")
        except Exception:
            pass

        lines.append(f"<b>Source:</b> {meta.source_name} ({meta.grid_type.name})")
        lines.append(f"<b>File:</b> {key}")

        self._meta_panel.setHtml("<br>".join(lines))

    def _show_file_meta(
        self, key: str, meta: SourceMeta, ds: xr.Dataset,
    ) -> None:
        """Display metadata for a file (dataset)."""
        n_vars = len(meta.available_variables())
        n_t = ds.sizes.get(meta.time_dim, "?") if meta.time_dim else "?"

        lines = [
            f"<b>File:</b> {key}",
            f"<b>Source:</b> {meta.source_name}",
            f"<b>Grid:</b> {meta.grid_type.name}",
            f"<b>Vertical:</b> {meta.vertical_type.name}",
            f"<b>Time steps:</b> {n_t}",
            f"<b>Variables:</b> {n_vars}",
        ]
        self._meta_panel.setHtml("<br>".join(lines))

    def _show_source_meta(self, source: str) -> None:
        """Display metadata for a source group."""
        keys = [
            k for k, m in self._metas.items()
            if m.source_name.upper() == source.upper()
        ]
        n_files = len(keys)
        all_vars = set()
        for k in keys:
            all_vars |= self._metas[k].available_variables()

        lines = [
            f"<b>Source:</b> {source}",
            f"<b>Files:</b> {n_files}",
            f"<b>Total variables:</b> {len(all_vars)}",
        ]
        self._meta_panel.setHtml("<br>".join(lines))
