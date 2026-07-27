"""
CMEMS → canonical adapter.

CMEMS (Copernicus Marine Environment Monitoring Service) uses:
- Standard depth levels (depth, deptht)
- Rectilinear horizontal grid (longitude, latitude are 1-D)
- CF-compliant variable names (thetao, so, uo, vo, …)
- Time variable named ``time``
"""

from typing import Optional, Dict

import xarray as xr

from src.core.adapters.base import DataSourceAdapter
from src.core.canonical import SourceMeta, GridType, VerticalType


class CMEMSAdapter(DataSourceAdapter):
    """Adapter for CMEMS / Copernicus Marine NetCDF products."""

    # ------------------------------------------------------------------
    # Source → canonical variable mapping
    # ------------------------------------------------------------------
    # CMEMS uses CF Standard Names; we map all known ocean variables.
    _VAR_MAP: Dict[str, str] = {
        # Physical — T/S
        "thetao":         "temperature",
        "so":             "salinity",

        # Physical — currents
        "uo":             "u_current",
        "vo":             "v_current",
        "wo":             "w_velocity",

        # Physical — surface / mixing
        "zos":            "sea_surface_height",
        "mlotst":         "mixed_layer_thickness",

        # Biogeochemical
        "chl":            "chlorophyll",
        "o2":             "dissolved_oxygen",
        "no3":            "nitrate",
        "po4":            "phosphate",
        "ph":             "ph",
        "pp":             "primary_production",

        # Additional CMEMS variables (less common)
        "so2":            "salinity",        # some products use so2
        "utide":          "u_current",       # tidal component
        "vtide":          "v_current",       # tidal component
        "sossheig":       "sea_surface_height",
    }

    # ------------------------------------------------------------------
    # Coordinate mapping (CMEMS is straightforward)
    # ------------------------------------------------------------------
    _COORD_MAP: Dict[str, str] = {
        "time":      "time",
        "depth":     "depth",
        "longitude": "longitude",
        "latitude":  "latitude",
    }

    # CMEMS uses multiple common coordinate aliases
    _COORD_ALIASES: Dict[str, list] = {
        "depth":     ["depth", "deptht", "z", "lev"],
        "longitude": ["longitude", "lon", "long"],
        "latitude":  ["latitude", "lat"],
    }

    @property
    def source_name(self) -> str:
        return "CMEMS"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @classmethod
    def detect(cls, ds: xr.Dataset, file_path: Optional[str] = None) -> bool:
        """Detect CMEMS by CF-compliant coords OR filename pattern."""
        # Method A: look for CF-standard coordinates
        has_time = cls._find_coord(ds, "time") is not None
        has_lon = cls._find_coord(ds, "longitude", "lon", "long") is not None
        has_lat = cls._find_coord(ds, "latitude", "lat") is not None

        if has_time and has_lon and has_lat:
            # Further check: is this NOT ROMS? (ROMS has ocean_time)
            if "ocean_time" in ds.coords or "ocean_time" in ds.dims:
                return False
            return True

        # Method B: filename-based (cmems_*.nc)
        if file_path:
            import os
            fname = os.path.basename(file_path).lower()
            if fname.startswith("cmems_"):
                return True

        return False

    # ------------------------------------------------------------------
    # Adaptation
    # ------------------------------------------------------------------

    def adapt(self, ds: xr.Dataset) -> SourceMeta:
        """Build SourceMeta for a CMEMS dataset."""

        # Determine vertical type
        depth_name = self._find_coord(ds, *self._COORD_ALIASES["depth"])
        vert = VerticalType.DEPTH if depth_name else VerticalType.NONE

        # Filter var_map to variables actually present
        var_map: Dict[str, str] = {}
        for src, canon in self._VAR_MAP.items():
            if src in ds.data_vars:
                var_map[canon] = src

        # Build coord_map with actual names found in dataset
        coord_map: Dict[str, str] = {}

        # Time
        time_name = self._find_coord(ds, "time")
        if time_name:
            coord_map["time"] = time_name

        # Depth
        if depth_name:
            coord_map["depth"] = depth_name

        # Longitude
        lon_name = self._find_coord(ds, *self._COORD_ALIASES["longitude"])
        if lon_name:
            coord_map["longitude"] = lon_name

        # Latitude
        lat_name = self._find_coord(ds, *self._COORD_ALIASES["latitude"])
        if lat_name:
            coord_map["latitude"] = lat_name

        # Extra CMEMS metadata
        extra: Dict[str, object] = {
            "is_rectilinear": self._check_rectilinear(ds, lon_name, lat_name),
            "depth_name": depth_name,
        }

        # Record original variable attributes
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
            time_dim=time_name,
            extra_attrs=extra,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_rectilinear(
        ds: xr.Dataset,
        lon_name: Optional[str],
        lat_name: Optional[str],
    ) -> bool:
        """Heuristic: if lon/lat are 1-D, the grid is rectilinear."""
        if lon_name and lon_name in ds.coords:
            if ds[lon_name].ndim == 1:
                return True
        return False
