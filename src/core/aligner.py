"""
Temporal and spatial alignment between ROMS and CMEMS data sources.

Handles the three alignment dimensions identified in
:file:`tools/compare_sources.py`:

1. **Temporal** — ROMS ``ocean_time`` at 12:00Z matched to the nearest
   CMEMS ``time`` at 00:00Z (same calendar day by default).
2. **Spatial** — ROMS curvilinear :math:`{lon_rho, lat_rho}` regridded
   to the CMEMS rectilinear grid via nearest-neighbor or linear
   interpolation.
3. **Vertical** — (deferred) ROMS sigma→depth conversion.  Phase 4
   does surface-level alignment only.

Typical usage::

    from src.core.aligner import SourceAligner
    aligner = SourceAligner(roms_ds, roms_meta, cmems_ds, cmems_meta)
    matched = aligner.match_dates()
    print(f"Overlapping dates: {len(matched)}")
    ts_roms, ts_cmems = aligner.compare_point("temperature", lon=115, lat=13)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, List, Tuple

import numpy as np
import pandas as pd
import xarray as xr

from src.core.canonical import SourceMeta, GridType
from src.core.roms_utils import (
    extract_timeseries, extract_point, extract_field,
    TimeseriesResult,
)


# ---------------------------------------------------------------------------
# Temporal matching
# ---------------------------------------------------------------------------

def find_overlapping_period(
    times_a: np.ndarray,
    times_b: np.ndarray,
) -> Tuple[slice, slice] | None:
    """Return ``(slice_a, slice_b)`` for the overlapping time range.

    Parameters
    ----------
    times_a, times_b : np.ndarray
        Datetime64 arrays.

    Returns
    -------
    (slice, slice) or None
        ``None`` if there is no overlap.
    """
    t_a = pd.to_datetime(times_a)
    t_b = pd.to_datetime(times_b)

    start = max(t_a.min(), t_b.min())
    end = min(t_a.max(), t_b.max())

    if start > end:
        return None

    idx_a_start = np.searchsorted(t_a, start)
    idx_a_end = np.searchsorted(t_a, end, side="right")
    idx_b_start = np.searchsorted(t_b, start)
    idx_b_end = np.searchsorted(t_b, end, side="right")

    return slice(idx_a_start, idx_a_end), slice(idx_b_start, idx_b_end)


def match_nearest_timestep(
    target_date: np.datetime64,
    candidate_times: np.ndarray,
    max_hours: int = 24,
) -> int | None:
    """Find the index of the nearest timestep in *candidate_times*.

    Parameters
    ----------
    target_date : np.datetime64
    candidate_times : np.ndarray
    max_hours : int
        Maximum allowed time difference in hours.  If the nearest match
        is farther than this, returns ``None``.

    Returns
    -------
    int or None
    """
    target_ns = target_date.astype("datetime64[ns]").astype(np.int64)
    cand_ns = candidate_times.astype("datetime64[ns]").astype(np.int64)
    diffs = np.abs(cand_ns - target_ns)
    idx = int(np.argmin(diffs))
    if diffs[idx] > max_hours * 3600 * 1e9:
        return None
    return idx


def build_date_mapping(
    roms_times: np.ndarray,
    cmems_times: np.ndarray,
    max_hours: int = 24,
) -> Dict[int, int]:
    """Map each ROMS time index to the nearest CMEMS time index.

    Parameters
    ----------
    roms_times : np.ndarray
    cmems_times : np.ndarray
    max_hours : int

    Returns
    -------
    dict[int, int]
        ``{roms_idx: cmems_idx}`` for each ROMS timestep that has a
        matching CMEMS timestep within *max_hours*.
    """
    mapping: Dict[int, int] = {}
    for ri, rt in enumerate(roms_times):
        ci = match_nearest_timestep(rt, cmems_times, max_hours)
        if ci is not None:
            mapping[ri] = ci
    return mapping


# ---------------------------------------------------------------------------
# Spatial regridding — ROMS curvilinear → CMEMS rectilinear
# ---------------------------------------------------------------------------

def regrid_curvilinear_to_rectilinear(
    src_values: np.ndarray,
    src_lon: np.ndarray,
    src_lat: np.ndarray,
    target_lon: np.ndarray,
    target_lat: np.ndarray,
    method: str = "nearest",
) -> np.ndarray:
    """Regrid a 2-D curvilinear field onto a 1-D rectilinear grid.

    Parameters
    ----------
    src_values : np.ndarray
        2-D array on the source grid ``(ny, nx)``.
    src_lon, src_lat : np.ndarray
        2-D arrays of source grid coordinates.
    target_lon, target_lat : np.ndarray
        1-D arrays of target grid coordinates.
    method : str
        ``"nearest"`` (via KDTree) or ``"linear"``.

    Returns
    -------
    np.ndarray
        2-D array on the target grid ``(len(target_lat), len(target_lon))``.
    """
    if method == "nearest":
        return _regrid_nearest(src_values, src_lon, src_lat,
                               target_lon, target_lat)
    elif method == "linear":
        return _regrid_linear(src_values, src_lon, src_lat,
                              target_lon, target_lat)
    else:
        raise ValueError(f"Unknown regridding method: {method}")


def _regrid_nearest(
    src_values: np.ndarray,
    src_lon: np.ndarray,
    src_lat: np.ndarray,
    target_lon: np.ndarray,
    target_lat: np.ndarray,
) -> np.ndarray:
    """KDTree-based nearest-neighbor regridding."""
    from scipy.spatial import cKDTree

    # Build target mesh
    t_lon2d, t_lat2d = np.meshgrid(target_lon, target_lat)

    # Build KDTree on source points
    src_pts = np.column_stack((src_lon.ravel(), src_lat.ravel()))
    tree = cKDTree(src_pts)

    # Query for each target point
    tgt_pts = np.column_stack((t_lon2d.ravel(), t_lat2d.ravel()))
    _, indices = tree.query(tgt_pts)

    return src_values.ravel()[indices].reshape(t_lon2d.shape)


def _regrid_linear(
    src_values: np.ndarray,
    src_lon: np.ndarray,
    src_lat: np.ndarray,
    target_lon: np.ndarray,
    target_lat: np.ndarray,
) -> np.ndarray:
    """Linear-interpolation regridding via :class:`scipy.interpolate.griddata`."""
    from scipy.interpolate import griddata

    t_lon2d, t_lat2d = np.meshgrid(target_lon, target_lat)

    return griddata(
        (src_lon.ravel(), src_lat.ravel()),
        src_values.ravel(),
        (t_lon2d, t_lat2d),
        method="linear",
        fill_value=np.nan,
    )


# ---------------------------------------------------------------------------
# SourceAligner — high-level comparison interface
# ---------------------------------------------------------------------------

class SourceAligner:
    """Align ROMS and CMEMS datasets for point-by-point comparison.

    Parameters
    ----------
    roms_ds : xr.Dataset
        ROMS dataset (may be multi-timestep from :class:`TimeAssembler`).
    roms_meta : SourceMeta
    cmems_ds : xr.Dataset
        CMEMS single-file dataset.
    cmems_meta : SourceMeta
    max_hours : int
        Maximum hours between matched timesteps (default 24h for daily data).
    """

    def __init__(
        self,
        roms_ds: xr.Dataset,
        roms_meta: SourceMeta,
        cmems_ds: xr.Dataset,
        cmems_meta: SourceMeta,
        max_hours: int = 24,
    ) -> None:
        self._roms_ds = roms_ds
        self._roms_meta = roms_meta
        self._cmems_ds = cmems_ds
        self._cmems_meta = cmems_meta
        self._max_hours = max_hours

        self._date_map: Dict[int, int] | None = None
        self._common_vars: List[str] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def common_variables(self) -> List[str]:
        """Canonical variables present in BOTH datasets."""
        if self._common_vars is None:
            a = self._roms_meta.available_variables()
            b = self._cmems_meta.available_variables()
            self._common_vars = sorted(a & b)
        return self._common_vars

    @property
    def roms_only_variables(self) -> List[str]:
        """Variables only in ROMS."""
        a = self._roms_meta.available_variables()
        b = self._cmems_meta.available_variables()
        return sorted(a - b)

    @property
    def cmems_only_variables(self) -> List[str]:
        """Variables only in CMEMS."""
        a = self._roms_meta.available_variables()
        b = self._cmems_meta.available_variables()
        return sorted(b - a)

    # ------------------------------------------------------------------
    # Date matching
    # ------------------------------------------------------------------

    def match_dates(self) -> Dict[int, int]:
        """Build the ROMS→CMEMS date index mapping.

        Returns
        -------
        dict[int, int]
            ``{roms_time_idx: cmems_time_idx}``.
        """
        roms_times = self._roms_ds[self._roms_meta.time_dim].values
        cmems_times = self._cmems_ds[self._cmems_meta.time_dim].values
        self._date_map = build_date_mapping(
            roms_times, cmems_times, self._max_hours,
        )
        return self._date_map

    @property
    def n_matched(self) -> int:
        """Number of matched date pairs."""
        if self._date_map is None:
            self.match_dates()
        return len(self._date_map)

    def matched_dates(self) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """Return list of ``(roms_date, cmems_date)`` pairs."""
        if self._date_map is None:
            self.match_dates()
        roms_times = self._roms_ds[self._roms_meta.time_dim].values
        cmems_times = self._cmems_ds[self._cmems_meta.time_dim].values
        return [
            (pd.Timestamp(roms_times[ri]), pd.Timestamp(cmems_times[ci]))
            for ri, ci in self._date_map.items()
        ]

    def matched_date_labels(self) -> List[str]:
        """Return ``"YYYY-MM-DD"`` strings for the ROMS dates that have a match."""
        if self._date_map is None:
            self.match_dates()
        roms_times = self._roms_ds[self._roms_meta.time_dim].values
        return [pd.Timestamp(roms_times[ri]).strftime("%Y-%m-%d")
                for ri in sorted(self._date_map.keys())]

    # ------------------------------------------------------------------
    # Point comparison
    # ------------------------------------------------------------------

    def compare_point(
        self,
        canonical_var: str,
        lon: float,
        lat: float,
        level_idx_roms: int | None = None,
        level_idx_cmems: int | None = None,
    ) -> Tuple[TimeseriesResult, TimeseriesResult]:
        """Extract time series at a common geographic point from both sources.

        Only timesteps that have a match in both datasets are included.

        Parameters
        ----------
        canonical_var : str
            Must be in :attr:`common_variables`.
        lon, lat : float
        level_idx_roms : int or None
            Vertical level for ROMS (sigma layer index).  ``None`` for
            2-D variables.
        level_idx_cmems : int or None
            Vertical level for CMEMS (depth index).  ``None`` for 2-D
            variables.

        Returns
        -------
        (TimeseriesResult, TimeseriesResult)
            ROMS result, CMEMS result — aligned to the same dates.
        """
        if canonical_var not in self.common_variables:
            raise ValueError(
                f"'{canonical_var}' is not shared by both sources.\n"
                f"  ROMS-only:  {self.roms_only_variables}\n"
                f"  CMEMS-only: {self.cmems_only_variables}\n"
                f"  Common:     {self.common_variables}"
            )

        if self._date_map is None:
            self.match_dates()

        # Extract ROMS time series at the point
        roms_pt = extract_point(
            self._roms_ds, self._roms_meta,
            canonical_var, lon, lat, level_idx_roms,
        )

        # Extract CMEMS time series
        cmems_pt = extract_point(
            self._cmems_ds, self._cmems_meta,
            canonical_var, lon, lat, level_idx_cmems,
        )

        # Subset to matched dates
        matched_ri = sorted(self._date_map.keys())
        matched_ci = [self._date_map[ri] for ri in matched_ri]

        return (
            TimeseriesResult(
                values=roms_pt.values[matched_ri],
                times=roms_pt.times[matched_ri] if roms_pt.times is not None else None,
                label=f"ROMS {roms_pt.label}",
                units=roms_pt.units,
            ),
            TimeseriesResult(
                values=cmems_pt.values[matched_ci],
                times=cmems_pt.times[matched_ci] if cmems_pt.times is not None else None,
                label=f"CMEMS {cmems_pt.label}",
                units=cmems_pt.units,
            ),
        )

    def compare_timeseries(
        self,
        canonical_var: str,
        level_idx_roms: int | None = None,
        level_idx_cmems: int | None = None,
        *,
        lat_range: tuple | None = None,
        lon_range: tuple | None = None,
    ) -> Tuple[TimeseriesResult, TimeseriesResult]:
        """Spatially-averaged time series from both sources.

        The ROMS data is first interpolated to the CMEMS grid for a
        fair spatial-mean comparison.

        Parameters
        ----------
        canonical_var : str
        level_idx_roms, level_idx_cmems : int or None
        lat_range, lon_range : tuple or None

        Returns
        -------
        (TimeseriesResult, TimeseriesResult)
        """
        if self._date_map is None:
            self.match_dates()

        # CMEMS — direct extraction (rectilinear)
        cmems_ts = extract_timeseries(
            self._cmems_ds, self._cmems_meta,
            canonical_var, level_idx_cmems,
            lat_range=lat_range, lon_range=lon_range,
        )

        # ROMS — extract per-timestep, regrid to CMEMS grid, then average
        # This is memory-efficient: one timestep at a time
        cmems_lon = self._cmems_ds["longitude"].values
        cmems_lat = self._cmems_ds["latitude"].values

        src_var = self._roms_meta.source_var(canonical_var)
        roms_times = self._roms_ds[self._roms_meta.time_dim]
        n_t = roms_times.size
        roms_time_vals = roms_times.values
        roms_values = np.full(n_t, np.nan)

        for ti in range(n_t):
            da, rlon, rlat = extract_field(
                self._roms_ds, self._roms_meta,
                canonical_var, ti, level_idx_roms,
            )
            regridded = regrid_curvilinear_to_rectilinear(
                da.values, rlon, rlat, cmems_lon, cmems_lat,
                method="nearest",
            )

            # Apply spatial bounds
            if lat_range is not None or lon_range is not None:
                mask = np.ones_like(regridded, dtype=bool)
                if lat_range is not None:
                    lat2d = cmems_lat[:, np.newaxis] if cmems_lat.ndim == 1 else cmems_lat
                    # Broadcast lat
                    for j in range(len(cmems_lat)):
                        if cmems_lat[j] < lat_range[0] or cmems_lat[j] > lat_range[1]:
                            mask[j, :] = False
                if lon_range is not None:
                    for i in range(len(cmems_lon)):
                        if cmems_lon[i] < lon_range[0] or cmems_lon[i] > lon_range[1]:
                            mask[:, i] = False
                regridded = regridded[mask]

            roms_values[ti] = np.nanmean(regridded)

        return (
            TimeseriesResult(
                values=roms_values,
                times=roms_time_vals,
                label=f"ROMS {self._roms_meta.display_label(canonical_var)} (regridded)",
                units=self._roms_meta.standard_units(canonical_var),
            ),
            cmems_ts,
        )

    def regrid_roms_field(
        self,
        canonical_var: str,
        time_idx: int,
        level_idx: int | None = None,
        method: str = "nearest",
    ) -> np.ndarray:
        """Regrid a single ROMS timestep to the CMEMS grid.

        Parameters
        ----------
        canonical_var : str
        time_idx : int
            ROMS time index.
        level_idx : int or None
        method : str

        Returns
        -------
        np.ndarray
            2-D array on the CMEMS grid ``(len(lat), len(lon))``.
        """
        da, rlon, rlat = extract_field(
            self._roms_ds, self._roms_meta,
            canonical_var, time_idx, level_idx,
        )
        cmems_lon = self._cmems_ds["longitude"].values
        cmems_lat = self._cmems_ds["latitude"].values
        return regrid_curvilinear_to_rectilinear(
            da.values, rlon, rlat, cmems_lon, cmems_lat, method=method,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a human-readable summary of the alignment."""
        common = self.common_variables
        r_only = self.roms_only_variables
        c_only = self.cmems_only_variables

        lines = [
            f"ROMS-CMEMS Alignment Summary",
            f"{'='*40}",
            f"ROMS  time dim:  {self._roms_meta.time_dim} "
            f"({self._roms_ds.sizes.get(self._roms_meta.time_dim, 0)} steps)",
            f"CMEMS time dim:  {self._cmems_meta.time_dim} "
            f"({self._cmems_ds.sizes.get(self._cmems_meta.time_dim, 0)} steps)",
            f"ROMS  grid:      {self._roms_meta.grid_type.name}",
            f"CMEMS grid:      {self._cmems_meta.grid_type.name}",
            f"ROMS  vertical:  {self._roms_meta.vertical_type.name}",
            f"CMEMS vertical:  {self._cmems_meta.vertical_type.name}",
            f"",
            f"Matched dates:   {self.n_matched}",
            f"Common vars:     {common}",
            f"ROMS-only vars:  {r_only}",
            f"CMEMS-only vars: {c_only}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<SourceAligner: {self.n_matched} matched dates, "
                f"{len(self.common_variables)} shared vars>")
