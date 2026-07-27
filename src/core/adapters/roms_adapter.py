"""
ROMS → canonical adapter.

ROMS (Regional Ocean Modeling System) uses:
- Terrain-following sigma coordinates (s_rho, s_w)
- Curvilinear horizontal grid (lon_rho, lat_rho are 2-D)
- Staggered Arakawa-C grid (ρ, u, v, ψ points)
- Time variable named ``ocean_time``
"""

from typing import Optional, Dict

import xarray as xr

from src.core.adapters.base import DataSourceAdapter
from src.core.canonical import SourceMeta, GridType, VerticalType


class ROMSAdapter(DataSourceAdapter):
    """Adapter for ROMS model output."""

    # ------------------------------------------------------------------
    # Source → canonical variable mapping
    # ------------------------------------------------------------------
    # ROMS variable      → canonical name
    _VAR_MAP: Dict[str, str] = {
        "temp":           "temperature",
        "salt":           "salinity",
        "u":              "u_current",
        "v":              "v_current",
        "w":              "w_velocity",
        "ubar":           "u_barotropic",
        "vbar":           "v_barotropic",
        "zeta":           "sea_surface_height",
        # ROMS often also has zeta_detided, chlorophyll, etc.
        "zeta_detided":   "sea_surface_height",  # same canonical, source attr marks detided
        "chlorophyll":    "chlorophyll",
        "oxygen":         "dissolved_oxygen",
        "no3":            "nitrate",
        "po4":            "phosphate",
        "ph":             "ph",
    }

    # ------------------------------------------------------------------
    # Coordinate mapping
    # ------------------------------------------------------------------
    _COORD_MAP: Dict[str, str] = {
        "time":      "ocean_time",
        "sigma":     "s_rho",          # ρ-point layers
        "longitude": "lon_rho",        # 2-D curvilinear
        "latitude":  "lat_rho",        # 2-D curvilinear
    }

    # Additional staggered-grid coord names (exposed for grid-aware plotting)
    STAGGERED_COORDS = {
        "lon_u": "lon_u",
        "lat_u": "lat_u",
        "lon_v": "lon_v",
        "lat_v": "lat_v",
        "s_w":   "s_w",       # w-point vertical layers
    }

    @property
    def source_name(self) -> str:
        return "ROMS"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @classmethod
    def detect(cls, ds: xr.Dataset, file_path: Optional[str] = None) -> bool:
        """Detect ROMS by presence of ``ocean_time`` and ``s_rho`` coords."""
        has_ocean_time = "ocean_time" in ds.coords or "ocean_time" in ds.dims
        has_s_rho = "s_rho" in ds.coords or "s_rho" in ds.dims
        has_lon_rho = "lon_rho" in ds.coords
        return has_ocean_time and has_s_rho and has_lon_rho

    # ------------------------------------------------------------------
    # Adaptation
    # ------------------------------------------------------------------

    def adapt(self, ds: xr.Dataset) -> SourceMeta:
        """Build SourceMeta for a ROMS dataset."""

        # Determine vertical type
        vert = VerticalType.SIGMA if ("s_rho" in ds.dims or "s_rho" in ds.coords) \
               else VerticalType.NONE

        # Filter var_map to variables actually present in ds
        var_map: Dict[str, str] = {}
        for src, canon in self._VAR_MAP.items():
            if src in ds.data_vars:
                var_map[canon] = src

        # Filter coord_map
        coord_map: Dict[str, str] = {}
        for canon, src in self._COORD_MAP.items():
            if src in ds.coords or src in ds.dims:
                coord_map[canon] = src

        # If no sigma coord, remove it (2-D-only ROMS file)
        if vert == VerticalType.NONE:
            coord_map.pop("sigma", None)

        # Extra ROMS-specific metadata
        extra = {
            "staggered_coords": {
                k: v for k, v in self.STAGGERED_COORDS.items()
                if v in ds.coords
            },
            "grid_dims": {
                "eta_rho": ds.sizes.get("eta_rho"),
                "xi_rho":  ds.sizes.get("xi_rho"),
                "s_rho":   ds.sizes.get("s_rho"),
                "s_w":     ds.sizes.get("s_w"),
            },
        }

        # Record original variable attributes for units
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
