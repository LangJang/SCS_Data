"""
Unified marine data processing pipeline.

``MarineDataPipeline`` ties together file scanning, source detection,
metadata inspection, field extraction, visualization, and export
behind a single interface.

Usage::

    from src.core.pipeline import MarineDataPipeline

    pipe = MarineDataPipeline("D:/data/roms")
    pipe.scan()                         # list all .nc files
    pipe.sources()                      # {"ROMS": [...], "CMEMS": [...]}

    # Inspect one dataset
    pipe.inspect(source="CMEMS")

    # Plot snapshot maps for every field in every CMEMS file
    pipe.process("CMEMS", output_dir="output/cmems")

    # Or target a specific file
    pipe.process_key("roms_avg.nc", output_dir="output/roms")
"""

from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple
from collections import defaultdict

import xarray as xr
import numpy as np
import pandas as pd

from src.core.nc_reader import NCReader
from src.core.canonical import SourceMeta, GridType, VerticalType
from src.core.roms_utils import (
    extract_field, extract_all_fields, current_speed,
    snapshot_all_fields, available_fields,
)
from src.viz.map_plotter import plot_map


# ---------------------------------------------------------------------------
# MarineDataPipeline
# ---------------------------------------------------------------------------

class MarineDataPipeline:
    """Unified pipeline for marine environmental data from multiple sources.

    Parameters
    ----------
    data_dir : str or Path
        Root directory containing NetCDF (.nc / .nc4) files.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        self._reader = NCReader(self._data_dir)

        # Cached after load_all()
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # File discovery & loading
    # ------------------------------------------------------------------

    def scan(self) -> pd.DataFrame:
        """Scan the data directory and return file names + sizes.

        Returns
        -------
        pd.DataFrame
            Columns: ``name``, ``size_mb``.
        """
        return self._reader.scan_files_with_sizes()

    def load_all(self) -> "MarineDataPipeline":
        """Load all NetCDF files and auto-detect data sources.

        Returns self for chaining.
        """
        self._reader.load_all()
        self._loaded = True
        return self

    # ------------------------------------------------------------------
    # Source inventory
    # ------------------------------------------------------------------

    def sources(self) -> Dict[str, List[str]]:
        """Return data sources found, grouped by source name.

        Example::

            {"ROMS": ["roms_avg.nc"], "CMEMS": ["file1.nc", "file2.nc"]}

        Returns
        -------
        dict[str, list[str]]
            Source name → list of dataset keys (filenames).
        """
        if not self._loaded:
            self.load_all()

        groups: Dict[str, List[str]] = defaultdict(list)
        for key in self._reader.datasets:
            try:
                meta = self._reader.meta(key)
                groups[meta.source_name].append(key)
            except KeyError:
                groups["UNKNOWN"].append(key)
        return dict(groups)

    def keys_for(self, source: str) -> List[str]:
        """Return all dataset keys belonging to *source* (case-insensitive).

        Parameters
        ----------
        source : str
            Source name, e.g. ``"ROMS"``, ``"CMEMS"``.

        Returns
        -------
        list[str]
        """
        src_lower = source.lower()
        result = []
        for src_name, keys in self.sources().items():
            if src_name.lower() == src_lower:
                result.extend(keys)
        return result

    def meta_for(self, key: str) -> SourceMeta:
        """Return the SourceMeta for a loaded dataset key."""
        return self._reader.meta(key)

    def ds_for(self, key: str) -> xr.Dataset:
        """Return the xarray Dataset for a loaded key."""
        return self._reader[key]

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def inspect(self, *, key: str | None = None, source: str | None = None) -> None:
        """Print metadata for one or more datasets.

        Parameters
        ----------
        key : str or None
            Inspect a specific dataset by filename.
        source : str or None
            Inspect all datasets of this source (e.g. ``"CMEMS"``).
            Ignored if *key* is provided.
        """
        if not self._loaded:
            self.load_all()

        keys: List[str]
        if key is not None:
            keys = [key]
        elif source is not None:
            keys = self.keys_for(source)
            if not keys:
                print(f"No datasets found for source '{source}'.")
                print(f"Available sources: {list(self.sources().keys())}")
                return
        else:
            keys = list(self._reader.datasets.keys())

        for k in keys:
            print(f"\n{'='*60}")
            print(f"  {k}")
            print(f"{'='*60}")
            try:
                meta = self._reader.meta(k)
                print(f"  Source:      {meta.source_name}")
                print(f"  Grid:        {meta.grid_type.name}")
                print(f"  Vertical:    {meta.vertical_type.name}")
                print(f"  Variables:   {sorted(meta.available_variables())}")
                print(f"  Coord map:   {meta.coord_map}")
                print(f"  Time dim:    {meta.time_dim}")
                # Print coordinate ranges
                ds = self._reader[k]
                for canon, src_name in meta.coord_map.items():
                    if src_name in ds.coords:
                        vals = ds[src_name].values
                        if vals.size <= 100:
                            print(f"  {canon} ({src_name}): {vals.size} pts, "
                                  f"[{vals.min():.4f}, {vals.max():.4f}]")
                        else:
                            print(f"  {canon} ({src_name}): {vals.size} pts")
            except KeyError:
                print(f"  [UNKNOWN SOURCE — no adapter matched]")

    def list_variables(self, *, source: str | None = None) -> Dict[str, Set[str]]:
        """Return canonical variable names grouped by dataset key.

        Parameters
        ----------
        source : str or None
            Filter to a specific source (e.g. ``"CMEMS"``). If None, all sources.

        Returns
        -------
        dict[str, set[str]]
        """
        if not self._loaded:
            self.load_all()

        keys = self.keys_for(source) if source else list(self._reader.datasets.keys())
        result: Dict[str, Set[str]] = {}
        for k in keys:
            try:
                meta = self._reader.meta(k)
                result[k] = meta.available_variables()
            except KeyError:
                result[k] = set()
        return result

    # ------------------------------------------------------------------
    # Processing — snapshot maps
    # ------------------------------------------------------------------

    def snapshot(
        self,
        key: str,
        output_dir: str | Path,
        *,
        time_idx: int = 0,
        level_idx: int = 0,
        cmap: str = "Spectral_r",
        dpi: int = 200,
    ) -> List[Path]:
        """Plot all available fields from a single dataset as map snapshots.

        Parameters
        ----------
        key : str
            Dataset key (filename).
        output_dir : str or Path
        time_idx : int
        level_idx : int
        cmap : str
        dpi : int

        Returns
        -------
        list[Path]
            Saved file paths.
        """
        if not self._loaded:
            self.load_all()

        ds = self._reader[key]
        meta = self._reader.meta(key)
        return snapshot_all_fields(
            ds, meta, output_dir, time_idx, level_idx, cmap, dpi,
        )

    def snapshot_variable(
        self,
        key: str,
        canonical_name: str,
        output_path: str | Path,
        *,
        time_idx: int = 0,
        level_idx: int = 0,
        cmap: str = "Spectral_r",
        dpi: int = 200,
    ) -> Path:
        """Plot a single canonical variable from one dataset.

        Parameters
        ----------
        key : str
        canonical_name : str
            e.g. ``"temperature"``, ``"chlorophyll"``.
        output_path : str or Path
        time_idx : int
        level_idx : int
        cmap : str
        dpi : int

        Returns
        -------
        Path
        """
        if not self._loaded:
            self.load_all()

        ds = self._reader[key]
        meta = self._reader.meta(key)

        da, lon, lat = extract_field(ds, meta, canonical_name, time_idx, level_idx)

        output_path = Path(output_path)
        title = f"{meta.source_name} — {meta.display_label(canonical_name)}"

        plot_map(
            da, lon, lat,
            title=title,
            cmap=cmap,
            output_path=output_path,
            output_dpi=dpi,
        )
        return output_path

    # ------------------------------------------------------------------
    # Full pipeline — process all files of a given source
    # ------------------------------------------------------------------

    def process(
        self,
        source: str,
        output_dir: str | Path = "output",
        *,
        time_idx: int = 0,
        level_idx: int = 0,
        cmap: str = "Spectral_r",
        dpi: int = 200,
    ) -> Dict[str, List[Path]]:
        """Run the full pipeline on all datasets of a given source.

        For each matching dataset, produces:
        - Console metadata summary
        - Snapshot map for every available field

        Parameters
        ----------
        source : str
            Source name, e.g. ``"ROMS"`` or ``"CMEMS"``.
        output_dir : str or Path
            Root output directory (each dataset gets a subfolder).
        time_idx : int
        level_idx : int
        cmap : str
        dpi : int

        Returns
        -------
        dict[str, list[Path]]
            Dataset key → list of saved figure paths.
        """
        if not self._loaded:
            self.load_all()

        keys = self.keys_for(source)
        if not keys:
            print(f"[WARN] No datasets found for source '{source}'.")
            print(f"  Available: {list(self.sources().keys())}")
            return {}

        output_dir = Path(output_dir)

        print(f"╔{'═'*58}╗")
        print(f"║  Pipeline: {source}  —  {len(keys)} dataset(s)                      ║")
        print(f"╚{'═'*58}╝")

        all_saved: Dict[str, List[Path]] = {}

        for key in keys:
            meta = self._reader.meta(key)
            print(f"\n{'─'*60}")
            print(f"  {key}")
            print(f"  Source: {meta.source_name} | "
                  f"Grid: {meta.grid_type.name} | "
                  f"Vert: {meta.vertical_type.name}")
            print(f"  Variables: {sorted(meta.available_variables())}")

            # Subfolder per dataset
            stem = Path(key).stem
            out_sub = output_dir / source.lower() / stem
            out_sub.mkdir(parents=True, exist_ok=True)

            saved = self.snapshot(key, out_sub, time_idx=time_idx,
                                  level_idx=level_idx, cmap=cmap, dpi=dpi)
            all_saved[key] = saved

        # Summary
        total = sum(len(v) for v in all_saved.values())
        print(f"\n{'─'*60}")
        print(f"  Total: {total} figure(s) saved to {output_dir / source.lower()}/")

        return all_saved


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def quick_pipeline(
    data_dir: str | Path,
    source: str,
    output_dir: str | Path = "output",
    time_idx: int = 0,
    level_idx: int = 0,
) -> Dict[str, List[Path]]:
    """One-liner: load, detect, and process all files of a source.

    Usage::

        quick_pipeline("D:/data/roms", "ROMS")
        quick_pipeline("D:/data/cemes", "CMEMS", output_dir="output/cemes")
    """
    pipe = MarineDataPipeline(data_dir)
    return pipe.process(source, output_dir=output_dir,
                        time_idx=time_idx, level_idx=level_idx)
