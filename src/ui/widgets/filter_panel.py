"""
Dynamic filtering panel for overlay point data.

Appears in the "Make a Graph" right column only when an overlay dataset
is active.  Provides per-column filters with AND / OR logic between
filter groups.

Filters supported per overlay type:
- Fishery points: Species, Method, Date range, Location
- Future (eddy/front): Show/Hide toggle only

Signals
-------
filter_changed(df: pd.DataFrame | None)
    Emitted when any filter changes, with the filtered DataFrame.
"""

from __future__ import annotations

from typing import Dict, Set

import numpy as np
import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QCheckBox, QDateEdit, QDoubleSpinBox, QScrollArea,
    QButtonGroup, QRadioButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal


# ---------------------------------------------------------------------------
# FilterPanel
# ---------------------------------------------------------------------------

class FilterPanel(QGroupBox):
    """Dynamic filter controls for the active overlay dataset."""

    filter_changed = pyqtSignal(object)  # pd.DataFrame | None

    def __init__(self, parent=None):
        super().__init__("Overlay Filters", parent)
        self._full_df: pd.DataFrame | None = None
        self._active_df: pd.DataFrame | None = None
        self._overlay_label: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---- Scroll area for filter groups ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._scroll_content = QWidget()
        self._filter_layout = QVBoxLayout(self._scroll_content)
        self._filter_layout.setSpacing(6)
        self._filter_layout.addStretch()
        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll, 1)

        # ---- AND / OR toggle ----
        logic_row = QHBoxLayout()
        logic_row.addWidget(QLabel("Group logic:"))
        self._logic_group = QButtonGroup(self)
        self._and_btn = QRadioButton("AND")
        self._or_btn = QRadioButton("OR")
        self._and_btn.setChecked(True)
        self._logic_group.addButton(self._and_btn, 0)
        self._logic_group.addButton(self._or_btn, 1)
        self._and_btn.toggled.connect(self._apply)
        self._or_btn.toggled.connect(self._apply)
        logic_row.addWidget(self._and_btn)
        logic_row.addWidget(self._or_btn)
        logic_row.addStretch()
        layout.addLayout(logic_row)

        # Store checkboxes by group
        self._source_cbs: list[QCheckBox] = []
        self._species_cbs: list[QCheckBox] = []
        self._method_cbs: list[QCheckBox] = []
        self._location_spins: dict[str, QDoubleSpinBox] = {}

        self.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_df(self) -> pd.DataFrame | None:
        """Return the currently displayed (filtered) DataFrame, or None."""
        return self._active_df

    def set_overlay(self, df: pd.DataFrame | None, label: str = "") -> None:
        """Populate filters from an overlay DataFrame.

        Pass ``None`` to hide the panel.
        """
        if df is None:
            self._full_df = None
            self._overlay_label = ""
            self._active_df = None
            self.setVisible(False)
            return

        self._full_df = df
        self._overlay_label = label
        self._clear_filters()
        self._build_filters(df)
        self.setVisible(True)
        self._apply()

    # ------------------------------------------------------------------
    # Filter builders
    # ------------------------------------------------------------------

    def _clear_filters(self) -> None:
        """Remove all filter widgets."""
        for cb in self._source_cbs + self._species_cbs + self._method_cbs:
            cb.deleteLater()
        self._source_cbs.clear()
        self._species_cbs.clear()
        self._method_cbs.clear()
        for spin in self._location_spins.values():
            spin.deleteLater()
        self._location_spins.clear()

        # Remove all except the trailing stretch
        while self._filter_layout.count() > 1:
            item = self._filter_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_filters(self, df: pd.DataFrame) -> None:
        """Create filter groups based on available columns."""

        # ---- Source (multi-dataset) ----
        if "source" in df.columns and df["source"].nunique() > 1:
            group = QGroupBox("Dataset")
            gl = QVBoxLayout(group)
            for src in sorted(df["source"].unique()):
                cb = QCheckBox(str(src))
                cb.setChecked(True)
                cb.toggled.connect(self._apply)
                gl.addWidget(cb)
                self._source_cbs.append(cb)
            self._filter_layout.insertWidget(
                self._filter_layout.count() - 1, group
            )
        else:
            self._source_cbs.clear()

        # ---- Species ----
        if "species" in df.columns:
            group = QGroupBox("Species")
            gl = QVBoxLayout(group)
            for sp in sorted(df["species"].unique()):
                cb = QCheckBox(str(sp))
                cb.setChecked(True)
                cb.toggled.connect(self._apply)
                gl.addWidget(cb)
                self._species_cbs.append(cb)
            self._filter_layout.insertWidget(
                self._filter_layout.count() - 1, group
            )

        # ---- Method ----
        if "method" in df.columns:
            group = QGroupBox("Method")
            gl = QVBoxLayout(group)
            for m in sorted(df["method"].unique()):
                cb = QCheckBox(str(m))
                cb.setChecked(True)
                cb.toggled.connect(self._apply)
                gl.addWidget(cb)
                self._method_cbs.append(cb)
            self._filter_layout.insertWidget(
                self._filter_layout.count() - 1, group
            )

        # ---- Date Range ----
        if "date" in df.columns:
            group = QGroupBox("Date Range")
            gl = QHBoxLayout(group)
            dates = pd.to_datetime(df["date"])
            gl.addWidget(QLabel("From:"))
            from_d = QDateEdit()
            from_d.setCalendarPopup(True)
            from_d.setDisplayFormat("yyyy-MM-dd")
            from_d.setDate(QDate(dates.min().year, dates.min().month, dates.min().day))
            from_d.dateChanged.connect(self._apply)
            gl.addWidget(from_d)
            self._date_from = from_d

            gl.addWidget(QLabel("To:"))
            to_d = QDateEdit()
            to_d.setCalendarPopup(True)
            to_d.setDisplayFormat("yyyy-MM-dd")
            to_d.setDate(QDate(dates.max().year, dates.max().month, dates.max().day))
            to_d.dateChanged.connect(self._apply)
            gl.addWidget(to_d)
            self._date_to = to_d

            self._filter_layout.insertWidget(
                self._filter_layout.count() - 1, group
            )
        else:
            self._date_from = None
            self._date_to = None

        # ---- Location ----
        group = QGroupBox("Location")
        gl = QVBoxLayout(group)

        for axis, label, rng in [
            ("north", "N", (-90, 90)),
            ("south", "S", (-90, 90)),
            ("east", "E", (-180, 180)),
            ("west", "W", (-180, 180)),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}:"))
            spin = QDoubleSpinBox()
            spin.setRange(*rng)
            spin.setDecimals(2)
            if axis == "north":
                spin.setValue(df["lat"].max())
            elif axis == "south":
                spin.setValue(df["lat"].min())
            elif axis == "east":
                spin.setValue(df["lon"].max())
            else:
                spin.setValue(df["lon"].min())
            spin.valueChanged.connect(self._apply)
            row.addWidget(spin)
            gl.addLayout(row)
            self._location_spins[axis] = spin

        self._filter_layout.insertWidget(
            self._filter_layout.count() - 1, group
        )

    # ------------------------------------------------------------------
    # Apply filters
    # ------------------------------------------------------------------

    def _apply(self) -> None:
        """Evaluate all filters and emit the filtered DataFrame."""
        if self._full_df is None:
            self.filter_changed.emit(None)
            return

        df = self._full_df
        use_and = self._and_btn.isChecked()
        masks: list[pd.Series] = []

        # Source filter (multi-dataset)
        if self._source_cbs:
            selected = {cb.text() for cb in self._source_cbs if cb.isChecked()}
            if selected:
                masks.append(df["source"].isin(selected))

        # Species filter
        if self._species_cbs:
            selected = {cb.text() for cb in self._species_cbs if cb.isChecked()}
            if selected:
                masks.append(df["species"].isin(selected))

        # Method filter
        if self._method_cbs:
            selected = {cb.text() for cb in self._method_cbs if cb.isChecked()}
            if selected:
                masks.append(df["method"].isin(selected))

        # Date filter
        if hasattr(self, "_date_from") and self._date_from is not None:
            fd = self._date_from.date().toString("yyyy-MM-dd")
            td = self._date_to.date().toString("yyyy-MM-dd")
            masks.append(
                (df["date"] >= fd) & (df["date"] <= td)
            )

        # Location filter
        if self._location_spins:
            n = self._location_spins["north"].value()
            s = self._location_spins["south"].value()
            e = self._location_spins["east"].value()
            w = self._location_spins["west"].value()
            masks.append(
                (df["lat"] >= s) & (df["lat"] <= n) &
                (df["lon"] >= w) & (df["lon"] <= e)
            )

        # Combine
        if not masks:
            self._active_df = df
            self.filter_changed.emit(df)
            return

        if use_and:
            result = masks[0]
            for m in masks[1:]:
                result = result & m
        else:
            result = masks[0]
            for m in masks[1:]:
                result = result | m

        self._active_df = df[result].copy()
        self.filter_changed.emit(self._active_df)
