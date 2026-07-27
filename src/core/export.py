"""
Data export utilities.

Supported output formats:
- CSV (flat table)
- Excel (.xlsx) — multi-sheet
- NetCDF (.nc) — round-trip for processed data
- PNG/SVG — for matplotlib figures (handled in viz module)
"""

from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import xarray as xr
import numpy as np


# ---------------------------------------------------------------------------
# DataFrame exporters
# ---------------------------------------------------------------------------

def to_csv(df: pd.DataFrame, path: str | Path, **kwargs) -> Path:
    """Export DataFrame to CSV.

    Parameters
    ----------
    df : pd.DataFrame
    path : str or Path
        Output file path.

    Returns
    -------
    Path
        The written file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("index", False)
    kwargs.setdefault("encoding", "utf-8-sig")
    df.to_csv(path, **kwargs)
    return path


def to_excel(
    data: Dict[str, pd.DataFrame],
    path: str | Path,
    **kwargs,
) -> Path:
    """Export multiple DataFrames to a multi-sheet Excel workbook.

    Parameters
    ----------
    data : dict[str, pd.DataFrame]
        Sheet name → DataFrame mapping.
    path : str or Path
        Output .xlsx path.

    Returns
    -------
    Path
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in data.items():
            # Sheet names are max 31 chars
            safe_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=kwargs.pop("index", False))

    return path


# ---------------------------------------------------------------------------
# NetCDF round-trip
# ---------------------------------------------------------------------------

def to_netcdf(ds: xr.Dataset, path: str | Path, **kwargs) -> Path:
    """Write an xarray Dataset to a NetCDF file.

    Parameters
    ----------
    ds : xr.Dataset
    path : str or Path

    Returns
    -------
    Path
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("engine", "netcdf4")
    ds.to_netcdf(path, **kwargs)
    return path


# ---------------------------------------------------------------------------
# Convenience: Dataset → DataFrame
# ---------------------------------------------------------------------------

def dataset_to_dataframe(ds: xr.Dataset) -> pd.DataFrame:
    """Convert an xarray Dataset to a flat (tidy) DataFrame.

    Multi-dimensional variables are stacked; the result is suitable
    for CSV/Excel export.
    """
    return ds.to_dataframe().reset_index()
