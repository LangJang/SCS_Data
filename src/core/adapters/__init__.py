"""
Data-source adapters.

Each adapter normalizes a specific data source (ROMS, CMEMS, …)
into the canonical variable/coordinate schema.
"""

from src.core.adapters.base import DataSourceAdapter
from src.core.adapters.roms_adapter import ROMSAdapter
from src.core.adapters.standard_roms_adapter import StandardROMSAdapter
from src.core.adapters.rectilinear_roms_adapter import RectilinearROMSAdapter
from src.core.adapters.cmems_adapter import CMEMSAdapter

# Ordered by priority: earlier adapters are tried first in detect()
# StandardROMSAdapter: ROMS with depth (no s_rho) on 2-D curvilinear grid
# ROMSAdapter:          ROMS with s_rho on 2-D curvilinear grid (legacy)
# RectilinearROMSAdapter: ROMS on 1-D rectilinear grid (regridded)
# CMEMSAdapter:         CMEMS / any CF-compliant 1-D data
REGISTERED_ADAPTERS = [
    StandardROMSAdapter,
    ROMSAdapter,
    RectilinearROMSAdapter,
    CMEMSAdapter,
]

# Expose a convenience function
def detect_source(ds, file_path=None):
    """Return the first matching adapter class, or None."""
    for adapter_cls in REGISTERED_ADAPTERS:
        if adapter_cls.detect(ds, file_path):
            return adapter_cls
    return None


__all__ = [
    "DataSourceAdapter",
    "ROMSAdapter",
    "CMEMSAdapter",
    "REGISTERED_ADAPTERS",
    "detect_source",
]
