"""
Dataset registry reader for config.yaml.

Loads dataset metadata (name, source, variables, resolution options,
spatial/temporal extent, file path) and provides keyword-based search.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class DatasetConfig:
    """Metadata for one registered dataset."""

    __slots__ = (
        "name", "source", "keywords", "variables",
        "default_resolution", "available_resolutions",
        "lon_min", "lon_max", "lat_min", "lat_max",
        "time_start", "time_end", "time_frequency",
        "vertical_type", "vertical_layers", "vertical_range",
        "path", "file_pattern",
    )

    def __init__(self, raw: dict) -> None:
        self.name: str = raw["name"]
        self.source: str = raw.get("source", "")
        self.keywords: list[str] = raw.get("keywords", [])
        self.variables: list[str] = raw.get("variables", [])

        res = raw.get("resolution", {})
        self.default_resolution: float = res.get("default", 0.1)
        self.available_resolutions: list[float] = res.get("available", [])

        spat = raw.get("spatial", {})
        self.lon_min: float = spat.get("lon", {}).get("min", -180)
        self.lon_max: float = spat.get("lon", {}).get("max", 180)
        self.lat_min: float = spat.get("lat", {}).get("min", -90)
        self.lat_max: float = spat.get("lat", {}).get("max", 90)

        temp = raw.get("temporal", {})
        self.time_start: str = str(temp.get("start", ""))
        self.time_end: str = str(temp.get("end", ""))
        self.time_frequency: str = temp.get("frequency", "")

        vert = raw.get("vertical", {})
        self.vertical_type: str = vert.get("type", "")
        self.vertical_layers: int = vert.get("layers", 0)
        self.vertical_range: list[float] = vert.get("range", [])

        self.path: str = raw.get("path", "")
        self.file_pattern: str = raw.get("file_pattern", "")

    def resolve_path(self, base_dir: Path) -> Path:
        """Return absolute data path, resolving relative paths."""
        p = Path(self.path)
        if p.is_absolute():
            return p
        return (base_dir / p).resolve()

    def to_info_dict(self) -> dict:
        """Return a flat dict for UI info display."""
        vert_str = self.vertical_type
        if self.vertical_range:
            vert_str += f" [{self.vertical_range[0]:.0f}–{self.vertical_range[1]:.0f} m]"
        elif self.vertical_layers:
            vert_str += f" ({self.vertical_layers} layers)"
        return {
            "Dataset": self.name,
            "Source": self.source,
            "Variables": ", ".join(self.variables),
            "Resolution": f"{self.default_resolution}°",
            "Spatial": f"lon [{self.lon_min}, {self.lon_max}]  "
                       f"lat [{self.lat_min}, {self.lat_max}]",
            "Time": f"{self.time_start} → {self.time_end}  ({self.time_frequency})",
            "Depth": vert_str,
        }


class PresetRegion:
    """Predefined geographic bounding box."""
    __slots__ = ("name", "north", "south", "east", "west")

    def __init__(self, raw: dict) -> None:
        self.name: str = raw["name"]
        self.north: float = raw["north"]
        self.south: float = raw["south"]
        self.east: float = raw["east"]
        self.west: float = raw["west"]


class AppConfig:
    """Top-level application configuration loaded from config.yaml."""

    def __init__(self, yaml_path: str | Path) -> None:
        yaml_path = Path(yaml_path)
        with open(yaml_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        self._base_dir = yaml_path.parent

        self.datasets: list[DatasetConfig] = [
            DatasetConfig(d) for d in raw.get("datasets", [])
            if not d.get("hidden", False)
        ]
        self.preset_regions: list[PresetRegion] = [
            PresetRegion(r) for r in raw.get("preset_regions", [])
        ]
        self.color_styles: list[str] = raw.get("color_styles", ["viridis"])

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[DatasetConfig]:
        """Return datasets matching *query* in name, source, or keywords.

        An empty query returns all datasets.  Matching is case-insensitive.
        """
        q = query.strip().lower()
        if not q:
            return list(self.datasets)

        results: list[DatasetConfig] = []
        for ds in self.datasets:
            if q in ds.name.lower():
                results.append(ds)
            elif q in ds.source.lower():
                results.append(ds)
            elif any(q in kw.lower() for kw in ds.keywords):
                results.append(ds)
            elif any(q in v.lower() for v in ds.variables):
                results.append(ds)
        return results

    def dataset_names(self) -> list[str]:
        """Return all dataset names (for dropdown)."""
        return [d.name for d in self.datasets]


# ---------------------------------------------------------------------------
# Singleton loader
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load the application config (cached)."""
    return AppConfig(path or _CONFIG_PATH)
