"""
Overlay data panel — searchable point-data list (mirrors SearchSection).

Search bar  →  matching dataset cards  →  click to toggle overlay on map.

Each overlay dataset is defined in a registry (label, csv_path, keywords).
Search matches against label, keywords, species names, or methods
(fetched from the CSV on first load).

Signals
-------
overlay_toggled(df: pd.DataFrame | None, label: str)
    Emitted when a card is clicked to activate / deactivate.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QMouseEvent


# ---------------------------------------------------------------------------
# OverlayCard
# ---------------------------------------------------------------------------

class OverlayCard(QFrame):
    """A clickable card that toggles overlay display on the map.

    Visually matches InfoCard in SearchSection.  Selected state adds a
    blue border + light-blue background.
    """

    toggled = pyqtSignal(object, bool)  # (entry_dict, selected)

    STYLE_BASE = (
        "OverlayCard { background: #ffffff; border: 1px solid #ccc; "
        "border-radius: 4px; padding: 8px; } "
        "OverlayCard:hover { border: 2px solid #2a82da; }"
    )
    STYLE_SELECTED = (
        "OverlayCard { background: #e8f0fe; border: 2px solid #2a82da; "
        "border-radius: 4px; padding: 8px; } "
    )

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._selected = False

        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(self.STYLE_BASE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(280)
        self.setMaximumWidth(320)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)

        name = QLabel(entry["label"])
        name_font = QFont()
        name_font.setBold(True)
        name.setFont(name_font)
        layout.addWidget(name)

        # Summary rows — same format as InfoCard
        try:
            df = pd.read_csv(entry["path"])
            n = len(df)
            sp = df["species"].nunique() if "species" in df.columns else "?"
            mt = df["method"].nunique() if "method" in df.columns else "?"
            t_min = df["date"].min() if "date" in df.columns else "?"
            t_max = df["date"].max() if "date" in df.columns else "?"
            layout.addWidget(QLabel(f"<b>Points:</b>  {n}"))
            layout.addWidget(QLabel(f"<b>Species:</b>  {sp}  |  <b>Methods:</b>  {mt}"))
            layout.addWidget(QLabel(f"<b>Date:</b>  {t_min} → {t_max}"))

            # Tooltip
            tooltip_lines = [f"<b>{entry['label']}</b>", f"Points: {n}"]
            if "species" in df.columns:
                top = df["species"].value_counts().head(7)
                tooltip_lines.append("<br><b>Species:</b><br>" + "<br>".join(
                    f"  &middot; {s} ({c})" for s, c in top.items()
                ))
            if "method" in df.columns:
                top = df["method"].value_counts().head(5)
                tooltip_lines.append("<br><b>Methods:</b><br>" + "<br>".join(
                    f"  &middot; {m} ({c})" for m, c in top.items()
                ))
            if "catch_kg" in df.columns:
                c = df["catch_kg"]
                tooltip_lines.append(
                    f"<br><b>Catch:</b> {c.min():.0f} ~ {c.max():.0f} kg"
                )
            self.setToolTip("<br>".join(tooltip_lines))
        except Exception:
            fallback = entry.get("summary", "(data file not available)")
            lbl = QLabel(fallback)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._selected = not self._selected
        self.setStyleSheet(self.STYLE_SELECTED if self._selected
                           else self.STYLE_BASE)
        self.toggled.emit(self._entry, self._selected)
        super().mousePressEvent(event)

    def deselect(self) -> None:
        """Programmatically deselect this card."""
        self._selected = False
        self.setStyleSheet(self.STYLE_BASE)


# ---------------------------------------------------------------------------
# OverlayPanel
# ---------------------------------------------------------------------------

class OverlayPanel(QGroupBox):
    """Search bar + clickable overlay cards (same pattern as SearchSection)."""

    overlay_toggled = pyqtSignal(object)  # dict with keys: df, label, type, entry

    def __init__(self, overlays: list[dict] | None = None, parent=None):
        super().__init__("Overlay Data", parent)
        self._registry: list[dict] = overlays or []
        self._loaded: dict[str, pd.DataFrame] = {}
        self._active_cards: set[str] = set()  # paths of selected cards

        layout = QVBoxLayout(self)

        # ---- Search row ----
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Search — e.g. trawl, Nemipterus, Trawl ..."
        )
        self._search_input.setClearButtonEnabled(True)
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input, 1)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        # ---- Cards area (scrollable) ----
        self._cards_area = QScrollArea()
        self._cards_area.setWidgetResizable(True)
        self._cards_area.setStyleSheet("QScrollArea { border: none; }")
        self._cards_widget = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_widget)
        self._cards_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._cards_layout.addStretch()
        self._cards_area.setWidget(self._cards_widget)
        layout.addWidget(self._cards_area)

        # ---- Show all on init ----
        self._on_search()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        query = self._search_input.text().strip().lower()

        # Clear old cards
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for entry in self._registry:
            matches = (query == "" or
                       query in entry["label"].lower() or
                       any(query in kw.lower()
                           for kw in entry.get("keywords", [])))
            # Also search inside the CSV
            if not matches and query:
                try:
                    df = self._load(entry["path"])
                    if df is not None:
                        if ("species" in df.columns and
                            df["species"].str.lower().str.contains(query).any()):
                            matches = True
                        elif ("method" in df.columns and
                              df["method"].str.lower().str.contains(query).any()):
                            matches = True
                except Exception:
                    pass

            if matches:
                card = OverlayCard(entry)
                card.toggled.connect(self._on_card_toggled)
                self._cards_layout.insertWidget(
                    self._cards_layout.count() - 1, card
                )

    # ------------------------------------------------------------------
    # Card toggle
    # ------------------------------------------------------------------

    def _on_card_toggled(self, entry: dict, selected: bool) -> None:
        """A card was clicked — add/remove from multi-selection, merge & emit."""
        path = entry["path"]
        etype = entry.get("type", "fishery")

        if selected:
            self._active_cards.add(path)
        else:
            self._active_cards.discard(path)

        # Only handle fishery-type cards for merged scatter
        fishery_entries = [
            e for e in self._registry
            if e["path"] in self._active_cards and e.get("type", "fishery") == "fishery"
        ]
        station_entries = [
            e for e in self._registry
            if e["path"] in self._active_cards and e.get("type", "") == "station"
        ]

        # Build fishery payload
        fishery_payload = None
        if fishery_entries:
            dfs, labels = [], []
            for fe in fishery_entries:
                df = self._load(fe["path"])
                if df is not None:
                    df = df.copy()
                    df["source"] = fe["label"]
                    dfs.append(df)
                    labels.append(fe["label"])
            if dfs:
                merged = pd.concat(dfs, ignore_index=True)
                fishery_payload = {
                    "type": "fishery",
                    "label": ", ".join(labels),
                    "entry": fishery_entries[0],
                    "df": merged,
                }

        # Build station payload
        station_payload = None
        if station_entries:
            sentry = station_entries[-1]
            sdf = self._load(sentry["path"])
            station_payload = {
                "type": "station",
                "label": sentry["label"],
                "entry": sentry,
                "df": sdf,
            }

        # Emit combined
        self.overlay_toggled.emit({
            "fishery": fishery_payload,
            "station": station_payload,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load(self, path: str) -> pd.DataFrame | None:
        """Load CSV or Excel (cached)."""
        if path in self._loaded:
            return self._loaded[path]
        try:
            if path.endswith(".xlsx") or path.endswith(".xls"):
                df = pd.read_excel(path, sheet_name=0)
            else:
                df = pd.read_csv(path)
            self._loaded[path] = df
            return df
        except Exception:
            return None
