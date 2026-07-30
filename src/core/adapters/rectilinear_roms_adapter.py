"""
Rectilinear ROMS → canonical adapter.

Post-regridded ROMS output with:
- 1-D rectilinear grid (longitude, latitude), same as CMEMS standardized
- Absolute depth levels (0–400 m)
- CF-compliant time coordinate (``time``, not ``ocean_time``)
- ROMS-style variable names (temp, salt, u, v, w)
"""

from typing import Optional, Dict

import xarray as xr

from src.core.adapters.base import DataSourceAdapter
from src.core.canonical import SourceMeta, GridType, VerticalType


class RectilinearROMSAdapter(DataSourceAdapter):
    """Adapter for regridded ROMS output on a 1-D rectilinear grid."""

    _VAR_MAP: Dict[str, str] = {
        "temp":  "temperature",
        "salt":  "salinity",
        "u":     "u_current",
        "v":     "v_current",
        "w":     "w_velocity",
    }

    _COORD_MAP: Dict[str, str] = {
        "time":      "time",
        "depth":     "depth",
        "longitude": "longitude",
        "latitude":  "latitude",
    }

    @property
    def source_name(self) -> str:
        return "SCSIO-Rectilinear"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @classmethod
    def detect(cls, ds: xr.Dataset, file_path: Optional[str] = None) -> bool:
        """Detect rectilinear ROMS: CF-compliant 1-D coords + ROMS variables.

        Must have: ``time``, ``longitude``, ``latitude`` (1-D), ``depth``,
        and at least one ROMS-style variable (``temp``, ``salt``).
        Must NOT have ``ocean_time`` or ``lon_rho`` (those are handled by
        the curvilinear ROMS adapters).
        """
        # Exclude curvilinear ROMS
        if "ocean_time" in ds.coords or "ocean_time" in ds.dims:
            return False
        if "lon_rho" in ds.coords:
            return False

        # Must have CF 1-D coordinates
        has_time = "time" in ds.coords or "time" in ds.dims
        has_depth = "depth" in ds.coords or "depth" in ds.dims
        has_lon = "longitude" in ds.coords and ds.longitude.ndim == 1
        has_lat = "latitude" in ds.coords and ds.latitude.ndim == 1

        # Must have ROMS-style variable names
        has_roms_var = any(
            v in ds.data_vars for v in ("temp", "salt", "u", "v", "w")
        )

        return has_time and has_depth and has_lon and has_lat and has_roms_var

    # ------------------------------------------------------------------
    # Adaptation
    # ------------------------------------------------------------------

    def adapt(self, ds: xr.Dataset) -> SourceMeta:
        """Build SourceMeta for rectilinear ROMS data."""

        vert = VerticalType.DEPTH

        var_map: Dict[str, str] = {}
        for src, canon in self._VAR_MAP.items():
            if src in ds.data_vars:
                var_map[canon] = src

        coord_map: Dict[str, str] = {}
        for canon, src in self._COORD_MAP.items():
            if src in ds.coords or src in ds.dims:
                coord_map[canon] = src

        extra = {
            "grid_dims": {
                "time":  ds.sizes.get("time"),
                "depth": ds.sizes.get("depth"),
                "lat":   ds.sizes.get("latitude"),
                "lon":   ds.sizes.get("longitude"),
            },
            "is_rectilinear": True,
            "is_regridded": True,
        }

        extra["var_attrs"] = {
            canon: dict(ds[src].attrs)
            for canon, src in var_map.items()
        }

        return SourceMeta(
            source_name=self.source_name,
            grid_type=GridType.RECTILINEAR,
            vertical_type=vert,
            var_map=var_map,
            coord_map=coord_map,
            time_dim="time",
            extra_attrs=extra,
        )
