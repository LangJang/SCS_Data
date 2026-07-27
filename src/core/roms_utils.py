"""
ROMS ocean model utilities.

ROMS (Regional Ocean Modeling System) uses a staggered Arakawa-C grid
with curvilinear horizontal coordinates.  This module provides:

- Field extraction at a given time index and vertical layer
- u/v → ρ-grid interpolation (for current speed calculation)
- Batch snapshot plotting via :mod:`viz.map_plotter`
"""

from pathlib import Path
from typing import Optional, Dict, Tuple, List

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# ROMS coordinate naming conventions
# ---------------------------------------------------------------------------

# ROMS uses distinct grid coordinates:
#   ρ-grid (cell centres): lon_rho, lat_rho   → temp, salt, zeta, w
#   u-grid (u-velocity):   lon_u,   lat_u     → u, ubar
#   v-grid (v-velocity):   lon_v,   lat_v     → v, vbar

# Time dimension name (ROMS uses 'ocean_time' instead of 'time')
_ROMS_TIME = "ocean_time"

# Vertical coordinate names
_ROMS_S_RHO = "s_rho"   # vertical layers at ρ-points
_ROMS_S_W   = "s_w"     # vertical layers at w-points (interfaces)


# ---------------------------------------------------------------------------
# Field specification
# ---------------------------------------------------------------------------

# Each entry: (display_name, grid_type, zmatch)
#   grid_type: 'rho' | 'u' | 'v'
#   zmatch:    's_rho' | 's_w' | 'none'  — which vertical dim the variable uses
ROMS_FIELD_SPEC: Dict[str, Tuple[str, str, str]] = {
    "zeta":  ("Sea Surface Height",       "rho", "none"),
    "ubar":  ("Depth-Averaged U-Current", "u",   "none"),
    "vbar":  ("Depth-Averaged V-Current", "v",   "none"),
    "temp":  ("Temperature",              "rho", "s_rho"),
    "salt":  ("Salinity",                 "rho", "s_rho"),
    "u":     ("U-Current (eastward)",     "u",   "s_rho"),
    "v":     ("V-Current (northward)",    "v",   "s_rho"),
    "w":     ("W-Velocity (vertical)",    "rho", "s_w"),
}


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def extract_field(
    ds: xr.Dataset,
    varname: str,
    time_idx: int = 0,
    s_idx: Optional[int] = None,
) -> Tuple[xr.DataArray, np.ndarray, np.ndarray]:
    """Extract a single ROMS field at a given time and sigma layer.

    Parameters
    ----------
    ds : xr.Dataset
        ROMS output dataset.
    varname : str
        Variable name (e.g., ``"temp"``, ``"u"``, ``"zeta"``).
    time_idx : int
        Index along the ocean_time dimension.
    s_idx : int or None
        Index along the vertical dimension. Ignored for 2-D fields (zeta, ubar, vbar).

    Returns
    -------
    (DataArray, lon, lat) : (xr.DataArray, np.ndarray, np.ndarray)
        The sliced 2-D field and its longitude/latitude arrays.

    Raises
    ------
    KeyError
        If *varname* is not found in *ds* or its ROMS_FIELD_SPEC entry is missing.
    ValueError
        If *s_idx* is ``None`` for a 3-D variable.
    """
    if varname not in ds.data_vars:
        raise KeyError(
            f"Variable '{varname}' not found in dataset. "
            f"Available: {list(ds.data_vars.keys())}"
        )

    spec = ROMS_FIELD_SPEC.get(varname)
    if spec is None:
        raise KeyError(f"Unknown ROMS variable '{varname}'. Add it to ROMS_FIELD_SPEC.")

    _display, grid_type, zmatch = spec

    da = ds[varname]

    # Slice time
    if _ROMS_TIME in da.dims:
        da = da.isel({_ROMS_TIME: time_idx})

    # Slice vertical layer
    if zmatch != "none":
        if s_idx is None:
            raise ValueError(
                f"'{varname}' is a 3-D variable (zmatch={zmatch}); s_idx must be provided."
            )
        da = da.isel({zmatch: s_idx})

    # Resolve lon/lat by grid type
    lon, lat = _grid_coords(ds, grid_type)

    return da, lon, lat


def _grid_coords(ds: xr.Dataset, grid_type: str) -> Tuple[np.ndarray, np.ndarray]:
    """Return (lon, lat) arrays for a ROMS grid type."""
    if grid_type == "rho":
        return ds["lon_rho"].values, ds["lat_rho"].values
    elif grid_type == "u":
        return ds["lon_u"].values, ds["lat_u"].values
    elif grid_type == "v":
        return ds["lon_v"].values, ds["lat_v"].values
    else:
        raise ValueError(f"Unknown grid_type '{grid_type}' (expected 'rho'|'u'|'v').")


def extract_all_fields(
    ds: xr.Dataset,
    time_idx: int = 0,
    s_idx: Optional[int] = None,
) -> Dict[str, Tuple[xr.DataArray, np.ndarray, np.ndarray]]:
    """Extract all known ROMS fields as 2-D slices.

    Parameters
    ----------
    ds : xr.Dataset
    time_idx : int
    s_idx : int or None
        Vertical layer index. Only required if any 3-D field is in the dataset.

    Returns
    -------
    dict[str, (DataArray, lon, lat)]
        Variable name → (field, lon, lat). Variables not found in *ds* are skipped.
    """
    result: Dict[str, Tuple[xr.DataArray, np.ndarray, np.ndarray]] = {}
    for varname, (_display, _grid, zmatch) in ROMS_FIELD_SPEC.items():
        if varname not in ds.data_vars:
            continue
        # Only require s_idx for 3-D variables present in the dataset
        field_s_idx = s_idx if zmatch != "none" else None
        # If s_idx is None but a 3-D variable is present, raise
        if zmatch != "none" and s_idx is None:
            raise ValueError(
                f"Variable '{varname}' requires s_idx (vertical layer). "
                f"Pass s_idx= or call extract_field() individually."
            )
        result[varname] = extract_field(ds, varname, time_idx, field_s_idx)
    return result


# ---------------------------------------------------------------------------
# u/v → ρ-grid interpolation (for current speed)
# ---------------------------------------------------------------------------

def interpolate_uv_to_rho(
    ds: xr.Dataset,
    time_idx: int = 0,
    s_idx: int = 0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate u and v velocities from staggered grids onto ρ-points.

    ROMS uses a staggered Arakawa-C grid:
    - u is staggered in xi only (xi_u = xi_rho - 1)
    - v is staggered in eta only (eta_v = eta_rho - 1)

    Interior points are linearly averaged; boundary points copy the
    nearest edge value. Both outputs have shape (eta_rho, xi_rho).

    Parameters
    ----------
    ds : xr.Dataset
    time_idx : int
    s_idx : int
        Vertical (s_rho) layer index.

    Returns
    -------
    (u_rho, v_rho, lon_rho, lat_rho) : tuple of np.ndarray
        u and v interpolated to ρ-points, plus the ρ-grid coordinates.

    Raises
    ------
    KeyError
        If ``"u"`` or ``"v"`` is missing from the dataset.
    """
    if "u" not in ds.data_vars or "v" not in ds.data_vars:
        raise KeyError("Dataset must contain both 'u' and 'v' variables.")

    u_raw = ds["u"].isel({_ROMS_TIME: time_idx, _ROMS_S_RHO: s_idx}).values  # (eta_rho, xi_u)
    v_raw = ds["v"].isel({_ROMS_TIME: time_idx, _ROMS_S_RHO: s_idx}).values  # (eta_v, xi_rho)

    # ROMS Arakawa-C: u is staggered in xi only, v is staggered in eta only.
    # Interpolate each to ρ-points with boundary extrapolation.
    eta_rho, xi_rho = ds.sizes["eta_rho"], ds.sizes["xi_rho"]

    # u: xi_u → xi_rho  (interior average; boundaries copy edge value)
    u_rho = np.empty((eta_rho, xi_rho), dtype=u_raw.dtype)
    u_rho[:, 0] = u_raw[:, 0]
    u_rho[:, 1:-1] = 0.5 * (u_raw[:, :-1] + u_raw[:, 1:])
    u_rho[:, -1] = u_raw[:, -1]

    # v: eta_v → eta_rho  (interior average; boundaries copy edge value)
    v_rho = np.empty((eta_rho, xi_rho), dtype=v_raw.dtype)
    v_rho[0, :] = v_raw[0, :]
    v_rho[1:-1, :] = 0.5 * (v_raw[:-1, :] + v_raw[1:, :])
    v_rho[-1, :] = v_raw[-1, :]

    lon_rho = ds["lon_rho"].values
    lat_rho = ds["lat_rho"].values

    return u_rho, v_rho, lon_rho, lat_rho


def current_speed(
    ds: xr.Dataset,
    time_idx: int = 0,
    s_idx: int = 0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute current speed (magnitude) on ρ-points.

    Parameters
    ----------
    ds : xr.Dataset
    time_idx : int
    s_idx : int

    Returns
    -------
    (speed, lon_rho, lat_rho) : tuple of np.ndarray
        Current speed (m/s) and ρ-grid coordinates.
    """
    u_rho, v_rho, lon_rho, lat_rho = interpolate_uv_to_rho(ds, time_idx, s_idx)
    speed = np.sqrt(u_rho**2 + v_rho**2)
    return speed, lon_rho, lat_rho


# ---------------------------------------------------------------------------
# Batch snapshot plots
# ---------------------------------------------------------------------------

def snapshot_all_fields(
    ds: xr.Dataset,
    output_dir: str | Path,
    time_idx: int = 0,
    s_idx: int = 36,
    cmap: str = "Spectral_r",
    dpi: int = 200,
    show: bool = False,
) -> List[Path]:
    """Plot all available ROMS fields as map snapshots and save to disk.

    Parameters
    ----------
    ds : xr.Dataset
        ROMS dataset.
    output_dir : str or Path
        Directory for output PNG files.
    time_idx : int
        Ocean-time index.
    s_idx : int
        Vertical layer index (36 = surface layer in a typical 36-level ROMS).
    cmap : str
        Colormap name.
    dpi : int
        Output DPI.
    show : bool
        If True, display each figure interactively.

    Returns
    -------
    list[Path]
        Paths to saved figures.
    """
    from src.viz.map_plotter import plot_map

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved: List[Path] = []

    for varname, (display_name, _grid, _zmatch) in ROMS_FIELD_SPEC.items():
        if varname not in ds.data_vars:
            continue

        try:
            da, lon, lat = extract_field(ds, varname, time_idx, s_idx)
        except (KeyError, ValueError) as exc:
            print(f"[SKIP] {varname}: {exc}")
            continue

        title = f"ROMS {varname} — {display_name}\nt={time_idx}, σ={s_idx}"
        out_path = output_dir / f"roms_{varname}_snapshot.png"

        plot_map(
            da, lon, lat,
            title=title,
            cmap=cmap,
            output_path=out_path,
            output_dpi=dpi,
            show=show,
        )
        saved.append(out_path)
        print(f"[OK] {varname} → {out_path}")

    return saved
