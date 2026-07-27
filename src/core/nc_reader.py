"""
NetCDF file reader for SCS marine environmental data.

Handles .nc / .nc4 files via xarray with netCDF4 backend.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List

import xarray as xr
import numpy as np
import pandas as pd


class NCReader:
    """Reader for NetCDF oceanographic data files.

    Parameters
    ----------
    data_dir : str or Path
        Root directory containing .nc files.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        self._datasets: Dict[str, xr.Dataset] = {}

    # ------------------------------------------------------------------
    # File Discovery
    # ------------------------------------------------------------------

    def scan_files(self, pattern: str = "*.nc") -> List[Path]:
        """Return sorted list of NetCDF files in the data directory.

        Parameters
        ----------
        pattern : str
            Glob pattern to match (also matches .nc4 when ``*.nc`` is used).

        Returns
        -------
        list[Path]
            Absolute paths to matching files, sorted alphabetically.
        """
        files = sorted(self._data_dir.glob(pattern))
        # Also pick up .nc4 if pattern was *.nc
        if pattern == "*.nc":
            files += sorted(self._data_dir.glob("*.nc4"))
            files = sorted(set(files))
        return files

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, file_path: str | Path) -> xr.Dataset:
        """Load a single NetCDF file into an xarray Dataset.

        Parameters
        ----------
        file_path : str or Path
            Path to the NetCDF file.

        Returns
        -------
        xr.Dataset
        """
        path = Path(file_path)
        key = path.name
        ds = xr.open_dataset(path, engine="netcdf4")
        self._datasets[key] = ds
        return ds

    def load_all(self) -> Dict[str, xr.Dataset]:
        """Scan data_dir and load every NetCDF file found.

        Returns
        -------
        dict[str, xr.Dataset]
            Mapping of filename → Dataset.
        """
        for fp in self.scan_files():
            self.load(fp)
        return self._datasets

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def summary(self) -> pd.DataFrame:
        """Return a summary DataFrame of all loaded datasets.

        Columns: file, variables, dimensions, time_range, size_mb
        """
        rows = []
        for name, ds in self._datasets.items():
            rows.append({
                "file": name,
                "variables": ", ".join(list(ds.data_vars.keys())),
                "dimensions": dict(ds.dims),
                "time_range": self._time_range(ds),
                "size_mb": ds.nbytes / (1024 * 1024),
            })
        return pd.DataFrame(rows)

    @staticmethod
    def _time_range(ds: xr.Dataset) -> Optional[str]:
        """Extract min/max time string from a dataset if 'time' dim exists."""
        if "time" not in ds.coords and "time" not in ds.dims:
            return None
        try:
            t = ds.time.values
            return f"{pd.Timestamp(t[0])} → {pd.Timestamp(t[-1])}"
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @property
    def datasets(self) -> Dict[str, xr.Dataset]:
        return self._datasets

    def __getitem__(self, key: str) -> xr.Dataset:
        return self._datasets[key]

    def __len__(self) -> int:
        return len(self._datasets)

    def __repr__(self) -> str:
        n = len(self._datasets)
        return f"<NCReader: {n} dataset(s) loaded from {self._data_dir}>"
