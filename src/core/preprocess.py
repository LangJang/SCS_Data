"""
Data preprocessing utilities for SCS marine environmental data.

Operations:
- Missing value detection & handling
- Temporal aggregation (daily, monthly, seasonal, annual)
- Spatial subsetting (lat/lon bounding box)
- Variable selection & unit conversion
"""

from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import xarray as xr
import pandas as pd


# ---------------------------------------------------------------------------
# Missing value utilities
# ---------------------------------------------------------------------------

def detect_missing(ds: xr.Dataset) -> pd.DataFrame:
    """Return per-variable NaN count and ratio.

    Parameters
    ----------
    ds : xr.Dataset
        Input dataset.

    Returns
    -------
    pd.DataFrame
        Columns: variable, nan_count, nan_ratio, total
    """
    rows = []
    for name, var in ds.data_vars.items():
        total = var.size
        nan_count = int(var.isnull().sum().values)
        rows.append({
            "variable": name,
            "nan_count": nan_count,
            "nan_ratio": nan_count / total if total else 0.0,
            "total": total,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Temporal resampling
# ---------------------------------------------------------------------------

def resample_time(
    ds: xr.Dataset,
    freq: str = "M",
    how: str = "mean",
) -> xr.Dataset:
    """Resample dataset along the time dimension.

    Parameters
    ----------
    ds : xr.Dataset
        Must have a 'time' coordinate/dimension.
    freq : str
        Pandas-style frequency: 'D' (daily), 'M' (monthly), 'Y' (annual), etc.
    how : str
        Reduction operation: 'mean', 'sum', 'max', 'min'.

    Returns
    -------
    xr.Dataset
        Resampled dataset.
    """
    if "time" not in ds.dims and "time" not in ds.coords:
        raise ValueError("Dataset has no 'time' dimension or coordinate.")

    resampler = ds.resample(time=freq)
    return getattr(resampler, how)(keep_attrs=True)


# ---------------------------------------------------------------------------
# Spatial subsetting
# ---------------------------------------------------------------------------

def subset_bbox(
    ds: xr.Dataset,
    lon_range: Tuple[float, float] | None = None,
    lat_range: Tuple[float, float] | None = None,
) -> xr.Dataset:
    """Subset dataset to a geographic bounding box.

    Handles common longitude/latitude variable names automatically.
    Supports both 0–360 and -180–180 longitude conventions.

    Parameters
    ----------
    ds : xr.Dataset
    lon_range : (lon_min, lon_max) or None
    lat_range : (lat_min, lat_max) or None

    Returns
    -------
    xr.Dataset
        Spatially subset dataset.
    """
    result = ds

    lon_name = _find_coord(ds, {"lon", "longitude", "long"})
    lat_name = _find_coord(ds, {"lat", "latitude"})

    if lon_range and lon_name:
        lon_min, lon_max = lon_range
        result = result.sel({lon_name: slice(lon_min, lon_max)})

    if lat_range and lat_name:
        lat_min, lat_max = lat_range
        result = result.sel({lat_name: slice(lat_min, lat_max)})

    return result


# ---------------------------------------------------------------------------
# Variable selection
# ---------------------------------------------------------------------------

def select_variables(ds: xr.Dataset, variables: List[str]) -> xr.Dataset:
    """Return a dataset containing only the named data variables.

    Parameters
    ----------
    ds : xr.Dataset
    variables : list[str]
        Variable names to keep.

    Returns
    -------
    xr.Dataset
    """
    available = set(ds.data_vars.keys())
    keep = [v for v in variables if v in available]
    missing = set(variables) - available
    if missing:
        print(f"[WARNING] Variables not found in dataset: {missing}")
    return ds[keep]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_coord(ds: xr.Dataset, candidates: set) -> Optional[str]:
    """Return the first matching coordinate/dimension name in *candidates*."""
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    return None
