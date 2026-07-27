"""
Base class for data-source adapters.

Each adapter translates one data source (ROMS, CMEMS, etc.) into
the canonical variable/coordinate schema defined in :mod:`canonical`.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict

import xarray as xr

from src.core.canonical import SourceMeta


class DataSourceAdapter(ABC):
    """Abstract adapter to normalize a NetCDF dataset into canonical form.

    Subclasses must implement:
    - ``detect(ds)``   — class method: does this dataset belong to this source?
    - ``adapt(ds)``    — produce a SourceMeta from the dataset
    - ``source_name``  — property: short string identifier (e.g., "ROMS", "CMEMS")
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier for this data source (e.g., 'ROMS', 'CMEMS')."""
        ...

    @classmethod
    @abstractmethod
    def detect(cls, ds: xr.Dataset, file_path: Optional[str] = None) -> bool:
        """Return True if *ds* is from this data source.

        Parameters
        ----------
        ds : xr.Dataset
            The open dataset to inspect.
        file_path : str or None
            File path, for filename-based heuristics.
        """
        ...

    @abstractmethod
    def adapt(self, ds: xr.Dataset) -> SourceMeta:
        """Build a SourceMeta describing *ds* in canonical terms.

        Parameters
        ----------
        ds : xr.Dataset
            Dataset from this source (already validated via ``detect()``).

        Returns
        -------
        SourceMeta
        """
        ...

    # ------------------------------------------------------------------
    # Helper: find a coordinate by candidate names
    # ------------------------------------------------------------------

    @staticmethod
    def _find_coord(ds: xr.Dataset, *candidates: str) -> Optional[str]:
        """Return the first *candidate* present in ds.coords or ds.dims."""
        for name in candidates:
            if name in ds.coords or name in ds.dims:
                return name
        return None

    # ------------------------------------------------------------------
    # Helper: standardize lon array to canonical format
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_lon(ds: xr.Dataset, coord_name: str) -> tuple:
        """Return (lon_array, lon_name) ensuring the array is usable.

        If 2-D (curvilinear), returns as-is. If 1-D, returns as-is.
        """
        if coord_name not in ds.coords:
            raise KeyError(f"Coordinate '{coord_name}' not found.")
        return ds[coord_name].values, coord_name

    @staticmethod
    def _resolve_lat(ds: xr.Dataset, coord_name: str) -> tuple:
        """Return (lat_array, lat_name). See _resolve_lon."""
        if coord_name not in ds.coords:
            raise KeyError(f"Coordinate '{coord_name}' not found.")
        return ds[coord_name].values, coord_name
