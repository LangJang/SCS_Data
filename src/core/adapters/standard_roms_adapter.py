"""
Standardized ROMS → canonical adapter.

Post-processing ROMS output with:
- Absolute depth levels (0–400 m, 14 layers) instead of terrain-following sigma
- Same variable mapping as original ROMSAdapter
- Detectable by ``ocean_time`` + ``lon_rho`` + ``depth`` (no ``s_rho``)
"""

from typing import Optional, Dict

import xarray as xr

from src.core.adapters.base import DataSourceAdapter
from src.core.canonical import SourceMeta, GridType, VerticalType


class StandardROMSAdapter(DataSourceAdapter):
    """Adapter for standardized (depth-interpolated) ROMS output."""

    # Source variable → canonical (same var names as original ROMS)
    _VAR_MAP: Dict[str, str] = {
        "temp":  "temperature",
        "salt":  "salinity",
        "u":     "u_current",
        "v":     "v_current",
        "w":     "w_velocity",
        "ubar":  "u_barotropic",
        "vbar":  "v_barotropic",
        "zeta":  "sea_surface_height",
        "chlorophyll": "chlorophyll",
        "oxygen":      "dissolved_oxygen",
        "no3":   "nitrate",
        "po4":   "phosphate",
        "ph":    "ph",
    }

    # Coordinate mapping (depth replaces sigma)
    _COORD_MAP: Dict[str, str] = {
        "time":      "ocean_time",
        "depth":     "depth",
        "longitude": "lon_rho",
        "latitude":  "lat_rho",
    }

    STAGGERED_COORDS = {
        "lon_u": "lon_u",
        "lat_u": "lat_u",
        "lon_v": "lon_v",
        "lat_v": "lat_v",
    }

    @property
    def source_name(self) -> str:
        return "SCSIO-Standard"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @classmethod
    def detect(cls, ds: xr.Dataset, file_path: Optional[str] = None) -> bool:
        """Detect standardized ROMS: ``ocean_time`` + ``lon_rho`` + ``depth``,
        WITHOUT ``s_rho`` (which would be legacy sigma-coordinate ROMS).
        """
        has_ocean_time = "ocean_time" in ds.coords or "ocean_time" in ds.dims
        has_lon_rho = "lon_rho" in ds.coords
        has_depth = "depth" in ds.coords or "depth" in ds.dims
        has_s_rho = "s_rho" in ds.coords or "s_rho" in ds.dims
        # Only match if depth is present AND s_rho is NOT (legacy ROMS gets
        # picked up by the original ROMSAdapter)
        return has_ocean_time and has_lon_rho and has_depth and not has_s_rho

    # ------------------------------------------------------------------
    # Adaptation
    # ------------------------------------------------------------------

    def adapt(self, ds: xr.Dataset) -> SourceMeta:
        """Build SourceMeta for standardized ROMS data."""

        # Vertical: absolute depth levels
        vert = VerticalType.DEPTH

        # Filter variable mapping to what's actually present
        var_map: Dict[str, str] = {}
        for src, canon in self._VAR_MAP.items():
            if src in ds.data_vars:
                var_map[canon] = src

        # Filter coordinate mapping
        coord_map: Dict[str, str] = {}
        for canon, src in self._COORD_MAP.items():
            if src in ds.coords or src in ds.dims:
                coord_map[canon] = src

        # Extra metadata
        extra = {
            "staggered_coords": {
                k: v for k, v in self.STAGGERED_COORDS.items()
                if v in ds.coords
            },
            "grid_dims": {
                "eta_rho": ds.sizes.get("eta_rho"),
                "xi_rho":  ds.sizes.get("xi_rho"),
                "depth":   ds.sizes.get("depth"),
            },
            "is_standardized": True,
        }

        extra["var_attrs"] = {
            canon: dict(ds[src].attrs)
            for canon, src in var_map.items()
        }

        return SourceMeta(
            source_name=self.source_name,
            grid_type=GridType.CURVILINEAR,
            vertical_type=vert,
            var_map=var_map,
            coord_map=coord_map,
            time_dim="ocean_time",
            extra_attrs=extra,
        )
