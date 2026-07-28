"""
Search bar and dataset info cards (top section — "Find the Data").

Features:
- Keyword search with autocomplete dropdown
- Multi-dataset info cards displayed horizontally
- Back button to return to search state
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QCompleter,
    QPushButton, QLabel, QGroupBox, QScrollArea, QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt6.QtGui import QFont, QMouseEvent

from src.core.config_reader import AppConfig, DatasetConfig


class InfoCard(QFrame):
    """A clickable dataset info card displayed after a successful search."""

    clicked = pyqtSignal(object)  # emits DatasetConfig

    def __init__(self, ds: DatasetConfig, parent=None):
        super().__init__(parent)
        self._ds = ds
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(
            "InfoCard { background: #ffffff; border: 1px solid #ccc; "
            "border-radius: 4px; padding: 8px; } "
            "InfoCard:hover { border: 2px solid #2a82da; }"
        )
        self.setMinimumWidth(280)
        self.setMaximumWidth(320)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)

        name_lbl = QLabel(ds.name)
        name_font = QFont()
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        layout.addWidget(name_lbl)

        for label, value in ds.to_info_dict().items():
            if label == "Dataset":
                continue
            row = QLabel(f"<b>{label}:</b>  {value}")
            row.setWordWrap(True)
            layout.addWidget(row)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self._ds)
        super().mousePressEvent(event)


class SearchSection(QGroupBox):
    """Top section: search bar → multi-dataset info cards.

    Signals
    -------
    dataset_selected(dataset_config)
        Emitted when a dataset card is clicked (for future use).
    """

    dataset_selected = pyqtSignal(object)

    def __init__(self, config: AppConfig, parent=None):
        super().__init__("Find the Data", parent)
        self._config = config
        self._results: list[DatasetConfig] = []

        self._init_ui()

    def _init_ui(self) -> None:
        main = QVBoxLayout(self)

        # ---- Search row ----
        search_row = QHBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Search datasets — e.g. temperature, chlorophyll, ROMS, CMEMS ..."
        )
        self._search_input.setClearButtonEnabled(True)
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input, 1)

        # Autocomplete from all keywords + names
        completions: set[str] = set()
        for ds in self._config.datasets:
            completions.add(ds.name)
            completions.update(ds.keywords)
            completions.update(ds.variables)
        model = QStringListModel(sorted(completions))
        completer = QCompleter(model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._search_input.setCompleter(completer)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)

        main.addLayout(search_row)

        # ---- Results area (scrollable cards) ----
        self._cards_area = QScrollArea()
        self._cards_area.setWidgetResizable(True)
        self._cards_area.setMaximumHeight(220)
        self._cards_area.setStyleSheet("QScrollArea { border: none; }")
        self._cards_widget = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_widget)
        self._cards_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._cards_layout.addStretch()
        self._cards_area.setWidget(self._cards_widget)
        self._cards_area.hide()
        main.addWidget(self._cards_area)

        # ---- Back button (hidden until search) ----
        back_row = QHBoxLayout()
        back_row.addStretch()
        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self._on_back)
        self._back_btn.hide()
        back_row.addWidget(self._back_btn)
        main.addLayout(back_row)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        query = self._search_input.text()
        self._results = self._config.search(query)

        # Clear old cards
        while self._cards_layout.count() > 1:  # keep the trailing stretch
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new cards
        for ds in self._results:
            card = InfoCard(ds)
            card.clicked.connect(self.dataset_selected.emit)
            self._cards_layout.insertWidget(
                self._cards_layout.count() - 1, card
            )

        self._cards_area.setVisible(len(self._results) > 0)
        self._back_btn.setVisible(len(self._results) > 0)

    def _on_back(self) -> None:
        """Clear results and return to initial search state."""
        self._search_input.clear()
        self._results.clear()
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards_area.hide()
        self._back_btn.hide()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def results(self) -> list[DatasetConfig]:
        return self._results
