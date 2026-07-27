"""
Canonical variable and coordinate schema for multi-source ocean data.

All adapters translate source-specific names to these canonical names.
Downstream modules (viz, export, preprocess) operate on canonical names
and are agnostic to the original data source.

Convention choices follow CF Standard Names where applicable.
"""

from typing import Dict, Set, Optional, Tuple

# ---------------------------------------------------------------------------
# Canonical coordinate names
# ---------------------------------------------------------------------------

CANONICAL_COORDS: Set[str] = {
    "time",
    "depth",
    "sigma",       # terrain-following vertical coordinate (ROMS s_rho/s_w)
    "longitude",
    "latitude",
}

# ---------------------------------------------------------------------------
# Canonical variable definitions
# ---------------------------------------------------------------------------

# Each entry: (canonical_name, display_label, standard_units)
CANONICAL_VARIABLES: Dict[str, Tuple[str, str]] = {
    # Physical — temperature & salinity
    "temperature":              ("Potential Temperature", "°C"),
    "salinity":                 ("Salinity", "PSU"),

    # Physical — currents
    "u_current":                ("Eastward Current", "m s⁻¹"),
    "v_current":                ("Northward Current", "m s⁻¹"),
    "w_velocity":               ("Vertical Velocity", "m s⁻¹"),
    "u_barotropic":             ("Depth-Averaged U-Current", "m s⁻¹"),
    "v_barotropic":             ("Depth-Averaged V-Current", "m s⁻¹"),

    # Physical — surface
    "sea_surface_height":       ("Sea Surface Height", "m"),
    "mixed_layer_thickness":    ("Mixed Layer Thickness", "m"),

    # Biogeochemical
    "chlorophyll":              ("Chlorophyll-a", "mg m⁻³"),
    "dissolved_oxygen":         ("Dissolved Oxygen", "mmol m⁻³"),
    "nitrate":                  ("Nitrate", "mmol m⁻³"),
    "phosphate":                ("Phosphate", "mmol m⁻³"),
    "ph":                       ("pH", ""),
    "primary_production":       ("Primary Production", "mg C m⁻² day⁻¹"),

    # Derived
    "current_speed":            ("Current Speed", "m s⁻¹"),
}

# ---------------------------------------------------------------------------
# Grid type
# ---------------------------------------------------------------------------

from enum import Enum, auto


class GridType(Enum):
    """Horizontal grid structure."""
    RECTILINEAR = auto()   # lon/lat are 1-D (CMEMS)
    CURVILINEAR = auto()   # lon/lat are 2-D (ROMS)
    UNKNOWN      = auto()


class VerticalType(Enum):
    """Vertical coordinate type."""
    DEPTH = auto()         # standard depth levels (z, depth)
    SIGMA = auto()         # terrain-following sigma (s_rho, s_w)
    NONE  = auto()         # 2-D field (no vertical dimension)


# ---------------------------------------------------------------------------
# Source metadata
# ---------------------------------------------------------------------------

class SourceMeta:
    """Metadata produced by an adapter describing a loaded dataset."""

    def __init__(
        self,
        source_name: str,
        grid_type: GridType,
        vertical_type: VerticalType,
        var_map: Dict[str, str],       # canonical_name → source_variable_name
        coord_map: Dict[str, str],     # canonical_coord → source_coord_name
        time_dim: Optional[str] = None,
        extra_attrs: Optional[Dict[str, object]] = None,
    ) -> None:
        self.source_name = source_name
        self.grid_type = grid_type
        self.vertical_type = vertical_type
        self.var_map = var_map
        self.coord_map = coord_map
        self.time_dim = time_dim
        self.extra_attrs = extra_attrs or {}

    def has_variable(self, canonical_name: str) -> bool:
        return canonical_name in self.var_map

    def available_variables(self) -> Set[str]:
        return set(self.var_map.keys())

    def source_var(self, canonical_name: str) -> str:
        """Return the source-side variable name for a canonical name."""
        if canonical_name not in self.var_map:
            raise KeyError(
                f"Canonical variable '{canonical_name}' not available "
                f"in {self.source_name} dataset."
            )
        return self.var_map[canonical_name]

    def canonical_var(self, source_name: str) -> Optional[str]:
        """Reverse lookup: source variable → canonical name."""
        for canon, src in self.var_map.items():
            if src == source_name:
                return canon
        return None

    def display_label(self, canonical_name: str) -> str:
        info = CANONICAL_VARIABLES.get(canonical_name)
        return info[0] if info else canonical_name

    def standard_units(self, canonical_name: str) -> str:
        info = CANONICAL_VARIABLES.get(canonical_name)
        return info[1] if info else ""

    def __repr__(self) -> str:
        return (
            f"<SourceMeta:{self.source_name} "
            f"grid={self.grid_type.name} "
            f"vert={self.vertical_type.name} "
            f"vars={len(self.var_map)}>"
        )
