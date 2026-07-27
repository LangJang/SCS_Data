"""
Multi-file time series assembler for ROMS (and future) daily data.

Aggregates individual daily-averaged NetCDF files into a single
lazy :class:`xarray.Dataset` spanning the full time range.  Uses
``xr.open_mfdataset`` so that the ~105 GB across 27 files is never
loaded into RAM at once — slices trigger reads of only the relevant
file(s).

Typical usage::

    from src.core.time_assembler import TimeAssembler
    from src.core.config import DATA_DIR_ROMS

    assembler = TimeAssembler(DATA_DIR_ROMS)
    assembler.scan()                          # discover files & dates
    ds = assembler.assemble()                 # lazy xr.Dataset
    meta = assembler.assembled_meta           # SourceMeta + time info

    # Access a single day (only that file is read):
    sst_day1 = ds["temp"].isel(ocean_time=0, s_rho=0)

    # Extract a point time series:
    from src.core.roms_utils import extract_timeseries
    ts, times = extract_timeseries(ds, meta, "temperature", ...)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
import xarray as xr

from src.core.canonical import SourceMeta
from src.core.adapters import detect_source

# ---------------------------------------------------------------------------
# Date extraction from ROMS filenames
# ---------------------------------------------------------------------------

# Matches: roms_avg_YYYYMMDDZhh.nc  (e.g. roms_avg_20230101Z12.nc)
_ROMS_DATE_RE = re.compile(r"roms_avg_(\d{8})Z(\d{2})\.nc", re.IGNORECASE)


def derive_date_from_roms_filename(filepath: str | Path) -> pd.Timestamp | None:
    """Extract a :class:`pd.Timestamp` from a ROMS daily-average filename.

    Expects: ``roms_avg_YYYYMMDDZhh.nc``.

    Parameters
    ----------
    filepath : str or Path

    Returns
    -------
    pd.Timestamp or None
        ``None`` when the pattern does not match.
    """
    m = _ROMS_DATE_RE.match(Path(filepath).name)
    if m is None:
        return None
    date_str, hour_str = m.group(1), m.group(2)
    return pd.Timestamp(f"{date_str}T{hour_str}:00:00")


# ---------------------------------------------------------------------------
# TimeAssembler
# ---------------------------------------------------------------------------

class TimeAssembler:
    """Assemble multiple ROMS single-timestep files into one lazy time series.

    Parameters
    ----------
    data_dir : str or Path
        Directory containing the daily NetCDF files.
    source : str
        Expected source label, e.g. ``"ROMS"``.
    """

    def __init__(
        self,
        data_dir: str | Path,
        source: str = "ROMS",
    ) -> None:
        self._data_dir = Path(data_dir)
        self._source = source.upper()

        # Populated by scan()
        self._file_map: Dict[pd.Timestamp, Path] = {}  # date -> path
        self._unmatched: List[Path] = []                # files not matching pattern

        # Populated by assemble()
        self._combined_ds: xr.Dataset | None = None
        self._assembled_meta: "AssembledMeta | None" = None

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def scan(
        self,
        pattern: str = "roms_avg_*.nc",
        on_unmatched: str = "warn",
    ) -> "TimeAssembler":
        """Scan the data directory for ROMS daily files.

        Parameters
        ----------
        pattern : str
            Glob pattern to match daily files.
        on_unmatched : str
            ``"warn"``, ``"ignore"``, or ``"error"``.

        Returns
        -------
        TimeAssembler
            Self, for chaining.
        """
        files = sorted(self._data_dir.glob(pattern))
        if not files:
            raise FileNotFoundError(
                f"No files matching '{pattern}' found in {self._data_dir}"
            )

        self._file_map.clear()
        self._unmatched.clear()

        for fp in files:
            ts = derive_date_from_roms_filename(fp)
            if ts is not None:
                self._file_map[ts] = fp
            else:
                self._unmatched.append(fp)

        # Sort by date
        self._file_map = dict(sorted(self._file_map.items()))

        if self._unmatched and on_unmatched == "warn":
            print(f"[TimeAssembler] {len(self._unmatched)} file(s) did not match "
                  f"ROMS date pattern:")
            for uf in self._unmatched:
                print(f"  - {uf.name}")
        elif self._unmatched and on_unmatched == "error":
            raise ValueError(
                f"{len(self._unmatched)} file(s) did not match ROMS date pattern: "
                f"{[f.name for f in self._unmatched]}"
            )

        return self

    @property
    def n_files(self) -> int:
        """Number of matched daily files."""
        return len(self._file_map)

    @property
    def n_timesteps(self) -> int:
        """Number of timesteps (= number of matched files)."""
        return len(self._file_map)

    @property
    def dates(self) -> List[pd.Timestamp]:
        """Sorted list of dates discovered by :meth:`scan`."""
        return list(self._file_map.keys())

    def date_range(self) -> Tuple[pd.Timestamp, pd.Timestamp]:
        """Return ``(first_date, last_date)``."""
        dates = self.dates
        return dates[0], dates[-1]

    def missing_dates(self) -> List[pd.Timestamp]:
        """Return dates that are missing from the expected daily sequence.

        For example, if files exist for Jan 1–3 and Jan 5, the result
        is ``[2023-01-04]``.
        """
        dates = self.dates
        if len(dates) < 2:
            return []
        expected = pd.date_range(dates[0], dates[-1], freq="D")
        existing = set(d.date() for d in dates)
        missing = [d for d in expected if d.date() not in existing]
        return missing

    def file_list(self) -> List[Path]:
        """Return the ordered list of matched file paths."""
        return list(self._file_map.values())

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def assemble(
        self,
        chunks: Dict[str, int] | None = None,
        concat_dim: str = "ocean_time",
        preprocess=None,
    ) -> xr.Dataset:
        """Concatenate all scanned files into a single lazy time-series Dataset.

        Uses :func:`xr.open_mfdataset` with dask-backed lazy loading.
        Each file contributes one chunk along *concat_dim*, so slicing
        a single timestep typically reads exactly one file.

        Parameters
        ----------
        chunks : dict or None
            Dask chunking scheme.  Default: ``{"ocean_time": 1}`` so
            that each file is a separate chunk.
        concat_dim : str
            Dimension along which to concatenate.  ROMS uses
            ``"ocean_time"``.
        preprocess : callable or None
            Optional function applied to each file before concatenation
            (passed through to ``open_mfdataset``).

        Returns
        -------
        xr.Dataset
            Lazy (dask-backed) dataset with dimension *concat_dim*
            equal to the number of files.

        Raises
        ------
        RuntimeError
            If :meth:`scan` has not been called or found zero files.
        """
        if not self._file_map:
            raise RuntimeError(
                "No files scanned. Call assembler.scan() before assemble()."
            )

        if chunks is None:
            chunks = {concat_dim: 1}

        file_paths = [str(p) for p in self._file_map.values()]

        print(f"[TimeAssembler] Assembling {len(file_paths)} files "
              f"({self.dates[0].date()} → {self.dates[-1].date()}) "
              f"with chunks={chunks} ...")

        ds = xr.open_mfdataset(
            file_paths,
            concat_dim=concat_dim,
            combine="nested",
            engine="netcdf4",
            chunks=chunks,
            preprocess=preprocess,
            # 'override' avoids duplicating static grid coords across files
            compat="override",
            data_vars="minimal",
            coords="minimal",
        )

        self._combined_ds = ds
        self._build_meta()
        return ds

    def _build_meta(self) -> None:
        """Build an :class:`AssembledMeta` from the first file's SourceMeta."""
        if self._combined_ds is None:
            raise RuntimeError("Call assemble() first.")

        # Use first file for the base adapter metadata
        first_path = str(self._file_map[self.dates[0]])
        first_ds = xr.open_dataset(first_path, engine="netcdf4")
        adapter_cls = detect_source(first_ds, first_path)
        if adapter_cls is None:
            raise RuntimeError(
                f"Could not detect source for {Path(first_path).name}"
            )
        adapter = adapter_cls()
        base_meta = adapter.adapt(first_ds)
        first_ds.close()

        # Time info
        time_dim = base_meta.time_dim or "ocean_time"
        time_vals = self._combined_ds[time_dim].values

        self._assembled_meta = AssembledMeta(
            base_meta=base_meta,
            n_timesteps=len(time_vals),
            time_values=time_vals,
            time_dim=time_dim,
            source_files=[f.name for f in self._file_map.values()],
            date_start=self.dates[0],
            date_end=self.dates[-1],
            missing_dates=self.missing_dates(),
        )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def dataset(self) -> xr.Dataset:
        """The assembled lazy Dataset (raises if not assembled)."""
        if self._combined_ds is None:
            raise RuntimeError("Call assemble() first.")
        return self._combined_ds

    @property
    def assembled_meta(self) -> "AssembledMeta":
        """Metadata for the assembled time series (raises if not assembled)."""
        if self._assembled_meta is None:
            raise RuntimeError("Call assemble() first.")
        return self._assembled_meta

    def __repr__(self) -> str:
        n = self.n_files
        status = "assembled" if self._combined_ds is not None else "scanned"
        if n == 0:
            return f"<TimeAssembler: no files scanned (source={self._source})>"
        dr = self.date_range()
        return (f"<TimeAssembler: {n} files, {dr[0].date()}→{dr[1].date()}, "
                f"source={self._source}, status={status}>")


# ---------------------------------------------------------------------------
# AssembledMeta
# ---------------------------------------------------------------------------

class AssembledMeta:
    """Metadata for a multi-file assembled time series.

    Wraps the single-file :class:`SourceMeta` with the additional
    temporal context needed for time-series operations.

    Attributes
    ----------
    base_meta : SourceMeta
        Canonical metadata from the first file (variable mappings, grid
        type, vertical type, coordinate names — identical across files).
    n_timesteps : int
    time_values : np.ndarray
        1-D array of datetime64 values.
    time_dim : str
    source_files : list[str]
        Ordered list of source filenames.
    date_start : pd.Timestamp
    date_end : pd.Timestamp
    missing_dates : list[pd.Timestamp]
        Dates in the expected daily range for which no file exists.
    missing_indices : list[int]
        Indices where a gap occurs (the index of the day *before* the gap).
    """

    def __init__(
        self,
        base_meta: SourceMeta,
        n_timesteps: int,
        time_values: np.ndarray,
        time_dim: str,
        source_files: List[str],
        date_start: pd.Timestamp,
        date_end: pd.Timestamp,
        missing_dates: List[pd.Timestamp],
    ) -> None:
        self.base_meta = base_meta
        self.n_timesteps = n_timesteps
        self.time_values = time_values
        self.time_dim = time_dim
        self.source_files = source_files
        self.date_start = date_start
        self.date_end = date_end
        self.missing_dates = missing_dates

        # Pre-compute gap indices for shading in plots
        self.missing_indices: List[int] = []
        if len(time_values) >= 2:
            dates = pd.to_datetime(time_values)
            for i in range(len(dates) - 1):
                delta = (dates[i + 1] - dates[i]).days
                if delta > 1:
                    self.missing_indices.append(i)

    # -- Convenience --------------------------------------------------------

    @property
    def time_labels(self) -> List[str]:
        """Return ``YYYY-MM-DD`` strings for each timestep."""
        return [pd.Timestamp(t).strftime("%Y-%m-%d") for t in self.time_values]

    def time_index_for(self, date: str | pd.Timestamp) -> int:
        """Return the integer index of *date* in the time coordinate.

        Parameters
        ----------
        date : str or pd.Timestamp
            e.g. ``"2023-01-15"``.

        Returns
        -------
        int

        Raises
        ------
        ValueError
            If *date* is not found.
        """
        target = pd.Timestamp(date)
        for i, t in enumerate(self.time_values):
            if pd.Timestamp(t).date() == target.date():
                return i
        raise ValueError(f"Date {date} not found in assembled time series.")

    def describe(self) -> str:
        """Return a human-readable summary string."""
        lines = [
            f"Source:          {self.base_meta.source_name}",
            f"Grid:            {self.base_meta.grid_type.name}",
            f"Vertical:        {self.base_meta.vertical_type.name}",
            f"Time dim:        {self.time_dim}",
            f"Timesteps:       {self.n_timesteps}",
            f"Date range:      {self.date_start.date()} → {self.date_end.date()}",
            f"Variables:       {sorted(self.base_meta.available_variables())}",
            f"Source files:    {len(self.source_files)}",
        ]
        if self.missing_dates:
            md = ", ".join(d.strftime("%Y-%m-%d") for d in self.missing_dates)
            lines.append(f"Missing dates:   {md}")
        else:
            lines.append("Missing dates:   (none)")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<AssembledMeta: {self.base_meta.source_name}, "
                f"{self.n_timesteps} steps, "
                f"{self.date_start.date()}→{self.date_end.date()}>")
