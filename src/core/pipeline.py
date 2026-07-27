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

    # ------------------------------------------------------------------
    # Time-series pipeline (v2)
    # ------------------------------------------------------------------

    def load_roms_collection(
        self,
        pattern: str = "roms_avg_*.nc",
        label: str = "roms_daily",
        chunks: Dict[str, int] | None = None,
    ) -> "MarineDataPipeline":
        """Load all ROMS daily files as a single lazy time-series Dataset.

        Uses :class:`~src.core.time_assembler.TimeAssembler` for
        dask-backed multi-file concatenation.

        Parameters
        ----------
        pattern : str
            Glob pattern for ROMS daily files.
        label : str
            Logical name for the assembled collection.
        chunks : dict or None
            Dask chunking.  Default: ``{"ocean_time": 1}``.

        Returns
        -------
        MarineDataPipeline
            Self, for chaining.
        """
        from src.core.time_assembler import TimeAssembler

        if not hasattr(self, "_assemblers"):
            self._assemblers: Dict[str, TimeAssembler] = {}
            self._collections: Dict[str, xr.Dataset] = {}
            self._collection_metas: Dict[str, any] = {}

        assembler = TimeAssembler(self._data_dir, source="ROMS")
        assembler.scan(pattern=pattern)
        self._assemblers[label] = assembler

        if chunks is None:
            chunks = {"ocean_time": 1}

        ds = assembler.assemble(chunks=chunks)
        self._collections[label] = ds
        self._collection_metas[label] = assembler.assembled_meta
        self._loaded = True

        return self

    @property
    def collections(self) -> Dict[str, xr.Dataset]:
        """Assembled multi-file collections."""
        if not hasattr(self, "_collections"):
            self._collections = {}
        return self._collections

    @property
    def collection_metas(self) -> Dict[str, any]:
        """Metadata for assembled collections."""
        if not hasattr(self, "_collection_metas"):
            self._collection_metas = {}
        return self._collection_metas

    def process_timeseries(
        self,
        collection_label: str = "roms_daily",
        variables: List[str] | None = None,
        output_dir: str | Path = "output/timeseries",
        *,
        level_idx: int = -1,
        output_dpi: int = 200,
    ) -> Dict[str, Path]:
        """Generate time-series products from an assembled collection.

        Produces:
        - Multi-variable time series panel plot
        - Daily map grid for the first variable (or SST)

        Parameters
        ----------
        collection_label : str
            Key for the assembled collection.
        variables : list[str] or None
            Canonical variables to include.  If None, all available.
        output_dir : str or Path
        level_idx : int
        output_dpi : int

        Returns
        -------
        dict[str, Path]
            Product name → saved file path.
        """
        from src.viz.time_plotter import (
            plot_timeseries, plot_daily_maps, plot_multi_variable_timeseries,
        )
        from src.core.roms_utils import extract_timeseries

        if collection_label not in self.collections:
            raise KeyError(
                f"No collection '{collection_label}'. "
                f"Available: {list(self.collections.keys())}. "
                f"Call load_roms_collection() first."
            )

        ds = self.collections[collection_label]
        meta = self.collection_metas[collection_label]

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved: Dict[str, Path] = {}

        # Determine variables
        if variables is None:
            variables = sorted(meta.base_meta.available_variables())

        # --- 1. Multi-variable time series summary ---
        print("\n--- Multi-variable time series ---")
        try:
            out_path = output_dir / "timeseries_summary.png"
            plot_multi_variable_timeseries(
                ds, meta.base_meta, variables,
                level_idx=level_idx,
                missing_indices=meta.missing_indices,
                output_path=out_path, output_dpi=output_dpi,
            )
            saved["timeseries_summary"] = out_path
            print(f"  [OK] timeseries_summary → {out_path}")
        except Exception as e:
            print(f"  [FAIL] timeseries_summary: {e}")

        # --- 2. Individual variable time series ---
        print("\n--- Individual time series ---")
        for var in variables:
            try:
                ts = extract_timeseries(ds, meta.base_meta, var, level_idx)
                out_path = output_dir / f"ts_{var}.png"
                plot_timeseries(
                    ts, missing_indices=meta.missing_indices,
                    output_path=out_path, output_dpi=output_dpi,
                )
                saved[f"ts_{var}"] = out_path
                print(f"  [OK] ts_{var} → {out_path}")
            except Exception as e:
                print(f"  [SKIP] ts_{var}: {e}")

        # --- 3. Daily map grid (every 7th day for readability) ---
        if variables:
            var = "temperature" if "temperature" in variables else variables[0]
            step = max(1, meta.n_timesteps // 8)  # at most ~8 panels
            indices = list(range(0, meta.n_timesteps, step))
            labels = [meta.time_labels[i] for i in indices]
            out_path = output_dir / f"daily_maps_{var}.png"
            try:
                plot_daily_maps(
                    ds, meta.base_meta, var, indices,
                    time_labels=labels, level_idx=level_idx,
                    output_path=out_path, output_dpi=output_dpi,
                )
                saved[f"daily_maps_{var}"] = out_path
                print(f"  [OK] daily_maps_{var} → {out_path}")
            except Exception as e:
                print(f"  [FAIL] daily_maps_{var}: {e}")

        print(f"\n  Total: {len(saved)} product(s) saved to {output_dir}/")
        return saved

    def compare_roms_cmems(
        self,
        collection_label: str = "roms_daily",
        cmems_key: str | None = None,
        output_dir: str | Path = "output/comparison",
        *,
        lon: float = 115.0,
        lat: float = 13.0,
        level_idx_roms: int = -1,
        level_idx_cmems: int = 0,
        output_dpi: int = 200,
    ) -> Dict[str, Path]:
        """Compare ROMS and CMEMS time series for overlapping variables.

        Parameters
        ----------
        collection_label : str
            ROMS collection key.
        cmems_key : str or None
            CMEMS dataset key (filename).  If None, uses the first
            CMEMS dataset found.
        output_dir : str or Path
        lon, lat : float
            Comparison point (default: central SCS).
        level_idx_roms : int
            ROMS sigma layer (-1 = surface).
        level_idx_cmems : int
            CMEMS depth index (0 = surface).
        output_dpi : int

        Returns
        -------
        dict[str, Path]
        """
        from src.core.aligner import SourceAligner
        from src.viz.time_plotter import plot_comparison_timeseries

        if collection_label not in self.collections:
            raise KeyError(
                f"No ROMS collection '{collection_label}'. "
                f"Call load_roms_collection() first."
            )

        # Find a CMEMS dataset
        if cmems_key is None:
            cmems_keys = self.keys_for("CMEMS")
            if not cmems_keys:
                raise RuntimeError(
                    "No CMEMS datasets loaded. "
                    "Run load_all() or ensure CMEMS files are in the data dir."
                )
            cmems_key = cmems_keys[0]

        roms_ds = self.collections[collection_label]
        roms_meta = self.collection_metas[collection_label].base_meta
        cmems_ds = self._reader[cmems_key]
        cmems_meta = self._reader.meta(cmems_key)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        aligner = SourceAligner(roms_ds, roms_meta, cmems_ds, cmems_meta)
        print(aligner.summary())

        saved: Dict[str, Path] = {}

        # Compare each common variable
        for var in aligner.common_variables:
            try:
                ts_r, ts_c = aligner.compare_point(
                    var, lon, lat,
                    level_idx_roms=level_idx_roms,
                    level_idx_cmems=level_idx_cmems,
                )
                out_path = output_dir / f"comparison_{var}.png"
                plot_comparison_timeseries(
                    ts_r, ts_c, source_names=("ROMS", "CMEMS"),
                    output_path=out_path, output_dpi=output_dpi,
                )
                saved[f"comparison_{var}"] = out_path
                print(f"  [OK] {var} → {out_path}")
            except Exception as e:
                print(f"  [SKIP] {var}: {e}")

        # Scatter comparison for the first common variable
        if aligner.common_variables:
            var = aligner.common_variables[0]
            ts_r, ts_c = aligner.compare_point(
                var, lon, lat,
                level_idx_roms=level_idx_roms,
                level_idx_cmems=level_idx_cmems,
            )
            out_path = output_dir / f"scatter_{var}.png"
            _save_scatter(ts_r, ts_c, var, out_path, output_dpi)
            saved[f"scatter_{var}"] = out_path
            print(f"  [OK] scatter_{var} → {out_path}")

        return saved


def _save_scatter(
    ts_a: "TimeseriesResult",
    ts_b: "TimeseriesResult",
    variable: str,
    output_path: Path,
    dpi: int = 200,
) -> None:
    """Save a scatter plot comparing two aligned time series."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(ts_a.values, ts_b.values, alpha=0.7, edgecolors="k", linewidth=0.3)
    ax.set_xlabel(f"ROMS {ts_a.label} ({ts_a.units})")
    ax.set_ylabel(f"CMEMS {ts_b.label} ({ts_b.units})")
    ax.set_title(f"ROMS vs CMEMS — {variable}")
    ax.grid(True, alpha=0.3)

    # 1:1 line
    all_vals = np.concatenate([ts_a.values, ts_b.values])
    lo, hi = np.nanmin(all_vals), np.nanmax(all_vals)
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=0.8, alpha=0.5)

    # R²
    mask = ~np.isnan(ts_a.values) & ~np.isnan(ts_b.values)
    if mask.sum() >= 3:
        corr = np.corrcoef(ts_a.values[mask], ts_b.values[mask])[0, 1]
        ax.text(0.05, 0.95, f"r = {corr:.4f}", transform=ax.transAxes,
                va="top", fontsize=10)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


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
