"""
Ocean model field extraction and manipulation utilities.

Source-aware: works with ROMS, CMEMS, or any data source that has been
normalized through a :class:`SourceMeta` adapter.

ROMS-specific features (staggered-grid interpolation) are guarded by
source checks and fail with a clear message for non-ROMS sources.
"""

from pathlib import Path
from typing import Optional, Dict, Tuple, List, Union

import numpy as np
import pandas as pd
import xarray as xr

from src.core.canonical import SourceMeta, GridType, VerticalType


# ---------------------------------------------------------------------------
# ROMS internal coordinate names (kept private for staggered-grid logic)
# ---------------------------------------------------------------------------

_ROMS_TIME  = "ocean_time"
_ROMS_S_RHO = "s_rho"
_ROMS_S_W   = "s_w"


# ---------------------------------------------------------------------------
# Field extraction (source-agnostic via SourceMeta)
# ---------------------------------------------------------------------------

def extract_field(
    ds: xr.Dataset,
    meta: SourceMeta,
    canonical_name: str,
    time_idx: int = 0,
    level_idx: int | None = None,
) -> Tuple[xr.DataArray, np.ndarray, np.ndarray]:
    """Extract a 2-D slice from a dataset using canonical variable names.

    Parameters
    ----------
    ds : xr.Dataset
        The raw dataset (source-native variable names).
    meta : SourceMeta
        Canonical metadata produced by the appropriate adapter.
    canonical_name : str
        Canonical variable name (e.g. ``"temperature"``, ``"u_current"``).
    time_idx : int
        Index along the time dimension.
    level_idx : int or None
        Index along the vertical dimension. Required for 3-D variables,
        ignored for 2-D variables.

    Returns
    -------
    (DataArray, lon, lat) : (xr.DataArray, np.ndarray, np.ndarray)
        The 2-D slice and its lon/lat coordinate arrays.

    Raises
    ------
    KeyError
        If the canonical variable is not available in this dataset.
    ValueError
        If *level_idx* is ``None`` for a 3-D variable.
    """
    # Resolve source variable name
    src_var = meta.source_var(canonical_name)
    da = ds[src_var]

    # Resolve time dimension
    time_name = meta.time_dim
    if time_name and time_name in da.dims:
        da = da.isel({time_name: time_idx})

    # Slice vertical dimension if present
    vert_dims = _vertical_dims(da, meta)
    if vert_dims:
        if level_idx is None:
            raise ValueError(
                f"Variable '{canonical_name}' ({src_var}) has vertical "
                f"dimension(s) {vert_dims}; level_idx must be provided."
            )
        # Use the first vertical dim
        da = da.isel({vert_dims[0]: level_idx})

    # Resolve lon/lat — delegate to source-specific logic
    lon, lat = _resolve_coords(ds, meta, src_var)

    return da, lon, lat


def _vertical_dims(da: xr.DataArray, meta: SourceMeta) -> List[str]:
    """Return vertical dimension names present in *da*."""
    if meta.vertical_type == VerticalType.SIGMA:
        candidates = [_ROMS_S_RHO, _ROMS_S_W]
    elif meta.vertical_type == VerticalType.DEPTH:
        depth_name = meta.coord_map.get("depth", "depth")
        candidates = [depth_name]
    else:
        candidates = []
    return [c for c in candidates if c in da.dims]


def _resolve_coords(
    ds: xr.Dataset,
    meta: SourceMeta,
    src_var: str,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (lon, lat) arrays for *src_var*, handling staggered grids.

    ROMS uses staggered grids: u/ubar are on lon_u/lat_u, v/vbar on lon_v/lat_v.
    All other variables use lon_rho/lat_rho.
    """
    if meta.source_name in ("ROMS", "ROMS-Standard"):
        return _resolve_roms_coords(ds, src_var)
    else:
        # Generic: use canonical lon/lat
        lon_name = meta.coord_map.get("longitude", "longitude")
        lat_name = meta.coord_map.get("latitude", "latitude")
        return ds[lon_name].values, ds[lat_name].values


def _resolve_roms_coords(
    ds: xr.Dataset,
    src_var: str,
) -> Tuple[np.ndarray, np.ndarray]:
    """ROMS-specific: pick lon/lat by grid type."""
    # Variables on u-grid
    if src_var in ("u", "ubar", "u_eastward"):
        return ds["lon_u"].values, ds["lat_u"].values
    # Variables on v-grid
    if src_var in ("v", "vbar", "v_northward"):
        return ds["lon_v"].values, ds["lat_v"].values
    # Default: ρ-grid
    return ds["lon_rho"].values, ds["lat_rho"].values


# ---------------------------------------------------------------------------
# Canonical field iteration
# ---------------------------------------------------------------------------

def available_fields(meta: SourceMeta) -> Dict[str, str]:
    """Return {canonical_name: display_label} for all extractable fields."""
    return {
        canon: meta.display_label(canon)
        for canon in meta.available_variables()
    }


def extract_all_fields(
    ds: xr.Dataset,
    meta: SourceMeta,
    time_idx: int = 0,
    level_idx: int | None = None,
) -> Dict[str, Tuple[xr.DataArray, np.ndarray, np.ndarray]]:
    """Extract all available 2-D field slices from a dataset.

    Parameters
    ----------
    ds : xr.Dataset
    meta : SourceMeta
    time_idx : int
    level_idx : int or None
        Vertical level index. Required if any 3-D variable is present.

    Returns
    -------
    dict[str, (DataArray, lon, lat)]
        Canonical variable name → (field, lon, lat).
    """
    result: Dict[str, Tuple[xr.DataArray, np.ndarray, np.ndarray]] = {}
    for canon in meta.available_variables():
        src_var = meta.source_var(canon)
        da_full = ds[src_var]

        # Skip scalar/metadata-only variables (no spatial dims)
        if da_full.ndim < 2:
            continue

        # Determine if variable has a vertical dim and needs level_idx
        vert_dims = [d for d in da_full.dims if d in (_ROMS_S_RHO, _ROMS_S_W)
                     or d == meta.coord_map.get("depth", "depth")]
        needs_level = len(vert_dims) > 0

        try:
            field_level = level_idx if needs_level else None
            result[canon] = extract_field(
                ds, meta, canon, time_idx, field_level,
            )
        except (KeyError, ValueError) as exc:
            print(f"[SKIP] {canon}: {exc}")
            continue

    return result


# ---------------------------------------------------------------------------
# u/v → ρ-grid interpolation (ROMS-specific)
# ---------------------------------------------------------------------------

def interpolate_uv_to_rho(
    ds: xr.Dataset,
    meta: SourceMeta,
    time_idx: int = 0,
    level_idx: int = 0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate u and v velocities onto ρ-points (ROMS only).

    ROMS uses a staggered Arakawa-C grid:
    - u is staggered in xi only (xi_u = xi_rho - 1)
    - v is staggered in eta only (eta_v = eta_rho - 1)

    Interior points are linearly averaged; boundary points copy the
    nearest edge value. Both outputs have shape (eta_rho, xi_rho).

    Parameters
    ----------
    ds : xr.Dataset
    meta : SourceMeta
        Must have ``source_name == "ROMS"``.
    time_idx : int
    level_idx : int
        Vertical (s_rho) layer index.

    Returns
    -------
    (u_rho, v_rho, lon_rho, lat_rho) : tuple of np.ndarray

    Raises
    ------
    ValueError
        If the source is not ROMS.
    KeyError
        If ``"u"`` or ``"v"`` is missing.
    """
    if meta.source_name not in ("ROMS", "ROMS-Standard"):
        raise ValueError(
            f"Staggered-grid interpolation is ROMS-specific. "
            f"Current source: {meta.source_name}. "
            f"For CMEMS, uo/vo are already on a common grid — "
            f"extract them directly with extract_field()."
        )

    if "u" not in ds.data_vars or "v" not in ds.data_vars:
        raise KeyError("Dataset must contain both 'u' and 'v' variables.")

    # Detect vertical coordinate: s_rho (legacy) or depth (standardized)
    vert_dim = "s_rho" if "s_rho" in ds.dims else "depth"

    u_raw = ds["u"].isel({_ROMS_TIME: time_idx, vert_dim: level_idx}).values
    v_raw = ds["v"].isel({_ROMS_TIME: time_idx, vert_dim: level_idx}).values

    eta_rho, xi_rho = ds.sizes["eta_rho"], ds.sizes["xi_rho"]

    # u: xi_u → xi_rho  (interior avg; boundaries copy edge)
    u_rho = np.empty((eta_rho, xi_rho), dtype=u_raw.dtype)
    u_rho[:, 0] = u_raw[:, 0]
    u_rho[:, 1:-1] = 0.5 * (u_raw[:, :-1] + u_raw[:, 1:])
    u_rho[:, -1] = u_raw[:, -1]

    # v: eta_v → eta_rho  (interior avg; boundaries copy edge)
    v_rho = np.empty((eta_rho, xi_rho), dtype=v_raw.dtype)
    v_rho[0, :] = v_raw[0, :]
    v_rho[1:-1, :] = 0.5 * (v_raw[:-1, :] + v_raw[1:, :])
    v_rho[-1, :] = v_raw[-1, :]

    lon_rho = ds["lon_rho"].values
    lat_rho = ds["lat_rho"].values

    return u_rho, v_rho, lon_rho, lat_rho


def current_speed(
    ds: xr.Dataset,
    meta: SourceMeta,
    time_idx: int = 0,
    level_idx: int = 0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute ocean current speed (magnitude) on a common grid.

    For ROMS: interpolates u/v from staggered grids to ρ-points, then
    computes sqrt(u² + v²).

    For CMEMS: extracts uo/vo directly (already on the same grid) and
    computes sqrt(uo² + vo²).

    Parameters
    ----------
    ds : xr.Dataset
    meta : SourceMeta
    time_idx : int
    level_idx : int
        Vertical level index.

    Returns
    -------
    (speed, lon, lat) : tuple of np.ndarray
        Current speed and the grid coordinates.
    """
    if meta.source_name in ("ROMS", "ROMS-Standard"):
        u_rho, v_rho, lon, lat = interpolate_uv_to_rho(ds, meta, time_idx, level_idx)
        speed = np.sqrt(u_rho**2 + v_rho**2)
        return speed, lon, lat

    # CMEMS / generic: uo & vo are on the same rectilinear grid
    da_u, lon, lat = extract_field(ds, meta, "u_current", time_idx, level_idx)
    da_v, _, _    = extract_field(ds, meta, "v_current", time_idx, level_idx)
    speed = np.sqrt(da_u.values**2 + da_v.values**2)
    return speed, lon, lat


# ---------------------------------------------------------------------------
# Batch snapshot plots (source-agnostic)
# ---------------------------------------------------------------------------

def snapshot_all_fields(
    ds: xr.Dataset,
    meta: SourceMeta,
    output_dir: str | Path,
    time_idx: int = 0,
    level_idx: int = 36,
    cmap: str = "Spectral_r",
    dpi: int = 200,
    show: bool = False,
) -> List[Path]:
    """Plot all available fields as map snapshots and save to disk.

    Works with any recognized data source (ROMS, CMEMS, …).

    Parameters
    ----------
    ds : xr.Dataset
    meta : SourceMeta
    output_dir : str or Path
    time_idx : int
    level_idx : int
        Vertical level index.
    cmap : str
    dpi : int
    show : bool

    Returns
    -------
    list[Path]
        Paths to saved figures.
    """
    from src.viz.map_plotter import plot_map

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved: List[Path] = []

    for canon, display_label in available_fields(meta).items():
        try:
            da, lon, lat = extract_field(ds, meta, canon, time_idx, level_idx)
        except (KeyError, ValueError) as exc:
            print(f"[SKIP] {canon}: {exc}")
            continue

        title = f"{meta.source_name} {canon} — {display_label}\n"
        if meta.vertical_type != VerticalType.NONE:
            title += f"t={time_idx}, level={level_idx}"

        out_path = output_dir / f"{meta.source_name.lower()}_{canon}_snapshot.png"

        plot_map(
            da, lon, lat,
            title=title,
            cmap=cmap,
            output_path=out_path,
            output_dpi=dpi,
            show=show,
        )
        saved.append(out_path)
        print(f"[OK] {canon} → {out_path}")

    return saved


# ---------------------------------------------------------------------------
# Time-series extraction (v2 — multi-timestep support)
# ---------------------------------------------------------------------------

def extract_timeseries(
    ds: xr.Dataset,
    meta: SourceMeta,
    canonical_name: str,
    level_idx: int | None = None,
    *,
    lat_range: Tuple[float, float] | None = None,
    lon_range: Tuple[float, float] | None = None,
    time_slice: slice | None = None,
    reduce: str = "mean",
) -> "TimeseriesResult":
    """Extract a spatially-averaged time series from a multi-timestep dataset.

    Selects a spatial sub-region (or the whole domain), applies a reduction
    (mean, sum, etc.), and returns a 1-D time series.

    Parameters
    ----------
    ds : xr.Dataset
        Multi-timestep dataset (e.g. from :class:`TimeAssembler.assemble`).
    meta : SourceMeta
    canonical_name : str
        Canonical variable name.
    level_idx : int or None
        Vertical level index.  ``None`` for 2-D variables.
    lat_range : (float, float) or None
        Latitude bounds ``(min, max)``.  If None, uses full domain.
    lon_range : (float, float) or None
        Longitude bounds ``(min, max)``.  If None, uses full domain.
    time_slice : slice or None
        If None, uses all timesteps.
    reduce : str
        Reduction operation: ``"mean"``, ``"sum"``, ``"min"``, ``"max"``,
        ``"std"``.

    Returns
    -------
    TimeseriesResult
        Named tuple with ``values``, ``times``, ``label``, ``units`` fields.
    """
    src_var = meta.source_var(canonical_name)
    da = ds[src_var]

    # Slice time
    time_name = meta.time_dim
    if time_name and time_name in da.dims:
        if time_slice is not None:
            da = da.isel({time_name: time_slice})
        time_vals = da[time_name].values
    else:
        time_vals = None

    # Slice vertical
    vert_dims = _vertical_dims(da, meta)
    if vert_dims:
        if level_idx is None:
            raise ValueError(
                f"Variable '{canonical_name}' has vertical dim(s) "
                f"{vert_dims}; level_idx must be provided."
            )
        da = da.isel({vert_dims[0]: level_idx})

    # Spatial subset
    lon_coord, lat_coord = _resolve_coords(ds, meta, src_var)

    if lon_range is not None:
        lon_mask = (lon_coord >= lon_range[0]) & (lon_coord <= lon_range[1])
        if lon_coord.ndim == 2:
            da = da.where(lon_mask)
        else:
            da = da.where(lon_mask, drop=True)

    if lat_range is not None:
        lat_mask = (lat_coord >= lat_range[0]) & (lat_coord <= lat_range[1])
        if lat_coord.ndim == 2:
            da = da.where(lat_mask)
        else:
            da = da.where(lat_mask, drop=True)

    # Reduce spatially over all remaining spatial dims
    spatial_dims = [d for d in da.dims
                    if d not in (time_name,) and d not in vert_dims]

    if spatial_dims:
        if reduce == "mean":
            da = da.mean(dim=spatial_dims)
        elif reduce == "sum":
            da = da.sum(dim=spatial_dims)
        elif reduce == "min":
            da = da.min(dim=spatial_dims)
        elif reduce == "max":
            da = da.max(dim=spatial_dims)
        elif reduce == "std":
            da = da.std(dim=spatial_dims)
        else:
            raise ValueError(f"Unknown reduce: {reduce}")

    values = da.values
    if values is None:
        values = da.compute().values

    return TimeseriesResult(
        values=np.asarray(values).ravel(),
        times=time_vals,
        label=meta.display_label(canonical_name),
        units=meta.standard_units(canonical_name),
    )


def extract_point(
    ds: xr.Dataset,
    meta: SourceMeta,
    canonical_name: str,
    lon: float,
    lat: float,
    level_idx: int | None = None,
    *,
    time_slice: slice | None = None,
) -> "TimeseriesResult":
    """Extract a time series at the grid point nearest to *(lon, lat)*.

    Parameters
    ----------
    ds : xr.Dataset
    meta : SourceMeta
    canonical_name : str
    lon, lat : float
        Target geographic coordinates.
    level_idx : int or None
    time_slice : slice or None

    Returns
    -------
    TimeseriesResult
    """
    src_var = meta.source_var(canonical_name)
    da = ds[src_var]

    # Slice time
    time_name = meta.time_dim
    if time_name and time_name in da.dims:
        if time_slice is not None:
            da = da.isel({time_name: time_slice})
        time_vals = da[time_name].values
    else:
        time_vals = None

    # Slice vertical
    vert_dims = _vertical_dims(da, meta)
    if vert_dims:
        if level_idx is None:
            raise ValueError(
                f"Variable '{canonical_name}' requires level_idx."
            )
        da = da.isel({vert_dims[0]: level_idx})

    # Find nearest grid point
    lon_arr, lat_arr = _resolve_coords(ds, meta, src_var)

    if lon_arr.ndim == 2 and lat_arr.ndim == 2:
        # Curvilinear — 2-D distance
        dist = np.sqrt((lon_arr - lon) ** 2 + (lat_arr - lat) ** 2)
        j, i = np.unravel_index(np.argmin(dist), dist.shape)
        spatial_dims = [d for d in da.dims
                        if d not in (time_name,) and d not in vert_dims]
        if len(spatial_dims) == 2:
            da = da.isel({spatial_dims[0]: j, spatial_dims[1]: i})
        else:
            da = da.isel({spatial_dims[0]: j, spatial_dims[-1]: i})
    else:
        # Rectilinear
        j = np.argmin(np.abs(lat_arr - lat))
        i = np.argmin(np.abs(lon_arr - lon))
        spatial_dims = [d for d in da.dims
                        if d not in (time_name,) and d not in vert_dims]
        if len(spatial_dims) >= 2:
            da = da.isel({spatial_dims[0]: j, spatial_dims[1]: i})
        else:
            da = da.isel({spatial_dims[0]: i})

    values = da.values
    if values is None:
        values = da.compute().values

    return TimeseriesResult(
        values=np.asarray(values).ravel(),
        times=time_vals,
        label=f"{meta.display_label(canonical_name)} at ({lon:.2f}, {lat:.2f})",
        units=meta.standard_units(canonical_name),
    )


def time_stats(
    ds: xr.Dataset,
    meta: SourceMeta,
    canonical_name: str,
    level_idx: int | None = None,
    *,
    time_slice: slice | None = None,
    lat_range: Tuple[float, float] | None = None,
    lon_range: Tuple[float, float] | None = None,
) -> Dict[str, float]:
    """Compute temporal statistics for a canonical variable.

    Returns a dict with keys: ``mean``, ``std``, ``min``, ``max``,
    ``trend_per_day`` (linear trend slope in units/day), ``n_timesteps``.

    Parameters
    ----------
    ds : xr.Dataset
    meta : SourceMeta
    canonical_name : str
    level_idx : int or None
    time_slice : slice or None
    lat_range, lon_range : (float, float) or None

    Returns
    -------
    dict[str, float]
    """
    result = extract_timeseries(
        ds, meta, canonical_name, level_idx,
        lat_range=lat_range, lon_range=lon_range,
        time_slice=time_slice, reduce="mean",
    )
    vals = result.values
    stats: Dict[str, float] = {
        "mean": float(np.nanmean(vals)),
        "std": float(np.nanstd(vals)),
        "min": float(np.nanmin(vals)),
        "max": float(np.nanmax(vals)),
        "n_timesteps": len(vals),
    }

    # Linear trend (units/day)
    if len(vals) >= 3:
        x = np.arange(len(vals), dtype=float)
        mask = ~np.isnan(vals)
        if mask.sum() >= 3:
            slope, _ = np.polyfit(x[mask], vals[mask], 1)
            stats["trend_per_day"] = float(slope)

    return stats


def extract_field_range(
    ds: xr.Dataset,
    meta: SourceMeta,
    canonical_name: str,
    time_slice: slice,
    level_idx: int | None = None,
) -> Tuple[xr.DataArray, np.ndarray, np.ndarray]:
    """Like :func:`extract_field`, but preserves the time dimension.

    Returns a 3-D DataArray ``(time, y, x)`` instead of a 2-D snapshot.
    For 2-D variables (no vertical dim), returns ``(time, y, x)``.
    For 3-D variables with *level_idx*, returns ``(time, y, x)``.

    Parameters
    ----------
    ds : xr.Dataset
    meta : SourceMeta
    canonical_name : str
    time_slice : slice
        Time range.  Use ``slice(None)`` for all timesteps.
    level_idx : int or None

    Returns
    -------
    (DataArray, lon, lat)
    """
    src_var = meta.source_var(canonical_name)
    da = ds[src_var]

    # Slice time (but KEEP the dimension)
    time_name = meta.time_dim
    if time_name and time_name in da.dims:
        da = da.isel({time_name: time_slice})

    # Slice vertical
    vert_dims = _vertical_dims(da, meta)
    if vert_dims:
        if level_idx is None:
            raise ValueError(
                f"Variable '{canonical_name}' ({src_var}) has vertical "
                f"dimension(s) {vert_dims}; level_idx must be provided."
            )
        da = da.isel({vert_dims[0]: level_idx})

    lon, lat = _resolve_coords(ds, meta, src_var)
    return da, lon, lat


# ---------------------------------------------------------------------------
# TimeseriesResult — lightweight named container
# ---------------------------------------------------------------------------

class TimeseriesResult:
    """Result of a time-series extraction.

    Attributes
    ----------
    values : np.ndarray
        1-D array of variable values in native units.
    times : np.ndarray or None
        1-D array of datetime64 values (None if dataset had no time dim).
    label : str
        Human-readable variable label.
    units : str
        Standard units for the variable.
    """

    __slots__ = ("values", "times", "label", "units")

    def __init__(
        self,
        values: np.ndarray,
        times: np.ndarray | None,
        label: str,
        units: str,
    ) -> None:
        self.values = np.asarray(values)
        self.times = times
        self.label = label
        self.units = units

    @property
    def time_labels(self) -> List[str] | None:
        """YYYY-MM-DD strings for each timestep."""
        if self.times is None:
            return None
        return [pd.Timestamp(t).strftime("%Y-%m-%d") for t in self.times]

    @property
    def n(self) -> int:
        """Number of timesteps."""
        return len(self.values)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to a :class:`pd.DataFrame` with ``time`` and ``value`` cols."""
        if self.times is not None:
            return pd.DataFrame({
                "time": pd.to_datetime(self.times),
                "value": self.values,
            })
        return pd.DataFrame({"value": self.values})

    def __repr__(self) -> str:
        return (f"<TimeseriesResult: {self.label}, {self.n} steps, "
                f"range=[{np.nanmin(self.values):.4g}, "
                f"{np.nanmax(self.values):.4g}]>")
