"""
Station biological survey panel.

Displays detailed biological measurement data for a fixed survey station.
Appears below the FilterPanel in the Make a Graph right column when a
station-type overlay card is selected.

In future multi-station mode, a station selector dropdown will appear
at the top.
"""

from __future__ import annotations

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy,
    QPushButton, QDialog, QVBoxLayout as QDialogLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class StationPanel(QGroupBox):
    """Biological survey station detail panel.

    Shows station metadata (name, lat, lon, species) and a summary table
    of morphometric measurements for all specimens at the station.

    Parameters
    ----------
    parent : QWidget or None
    """

    def __init__(self, parent=None):
        super().__init__("Station Survey", parent)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(2)

        # ---- Metadata labels (tight) ----
        self._station_lbl = QLabel("")
        self._station_lbl.setWordWrap(True)
        self._station_lbl.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._station_lbl)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._summary_lbl)

        # ---- Mini table (first 5 rows preview) ----
        self._table = QTableWidget()
        self._table.setMaximumHeight(180)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        # ---- View full table button ----
        btn_row = QVBoxLayout()
        self._full_btn = QPushButton("View Full Table")
        self._full_btn.clicked.connect(self._show_full_table)
        btn_row.addWidget(self._full_btn)
        layout.addLayout(btn_row)

        # Internal
        self._full_df: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_station(self, entry: dict, df: pd.DataFrame | None) -> None:
        """Populate the panel with station survey data.

        Parameters
        ----------
        entry : dict
            Registry entry dict with keys: label, station_lat, station_lon,
            station_name.
        df : pd.DataFrame or None
            Measurements table (from Excel/CSV).
        """
        if df is None or len(df) == 0:
            self.setVisible(False)
            return

        self._full_df = df
        lat = entry.get("station_lat", "?")
        lon = entry.get("station_lon", "?")
        sname = entry.get("station_name", entry.get("label", "?"))

        # Metadata
        self._station_lbl.setText(
            f"<b>Station:</b> {sname} &nbsp; "
            f"<b>Lat:</b> {lat}°N &nbsp; <b>Lon:</b> {lon}°E"
        )

        n = len(df)
        cols = list(df.columns)
        self._summary_lbl.setText(
            f"<b>Specimens:</b> {n} &nbsp; "
            f"<b>Columns:</b> {', '.join(cols[:6])}"
            + (" ..." if len(cols) > 6 else "")
        )

        # Preview table (first 5 rows, first 6 columns)
        preview_cols = cols[:6]
        preview = df[preview_cols].head(5)
        self._table.setRowCount(len(preview))
        self._table.setColumnCount(len(preview_cols))
        self._table.setHorizontalHeaderLabels(
            [str(c) for c in preview_cols]
        )

        for r in range(len(preview)):
            for c in range(len(preview_cols)):
                val = preview.iloc[r, c]
                text = f"{val:.1f}" if isinstance(val, float) else str(val)
                self._table.setItem(r, c, QTableWidgetItem(text))

        self._table.resizeColumnsToContents()
        self.setVisible(True)

    def clear(self) -> None:
        """Hide and reset the panel."""
        self.setVisible(False)
        self._full_df = None

    # ------------------------------------------------------------------
    # Full table dialog
    # ------------------------------------------------------------------

    def _show_full_table(self) -> None:
        """Open a dialog with the full measurements table."""
        if self._full_df is None:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Full Measurements Table")
        dlg.resize(900, 500)
        layout = QDialogLayout(dlg)

        table = QTableWidget()
        df = self._full_df
        cols = [str(c) for c in df.columns]
        table.setRowCount(len(df))
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for r in range(len(df)):
            for c in range(len(cols)):
                val = df.iloc[r, c]
                text = f"{val:.1f}" if isinstance(val, float) else str(val)
                table.setItem(r, c, QTableWidgetItem(text))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(table)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec()
