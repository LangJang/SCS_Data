"""
Project-wide path constants for SCS Marine Data Tool.

All data-source directories are configured here. Scripts and modules
should import from this module rather than hardcoding paths.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Project root (resolved from the location of THIS file)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Data source directories
# ---------------------------------------------------------------------------

# CMEMS / Copernicus Marine data — downloaded products
DATA_DIR_CMEMS = Path("D:/ChatWithAI/Downloading_CEMES")

# ROMS model output — placed in the project's data/ directory
DATA_DIR_ROMS = PROJECT_ROOT / "data"

# ---------------------------------------------------------------------------
# Legacy / ad-hoc paths (for backward compatibility)
# ---------------------------------------------------------------------------

# Original ROMS directory (used before data/ was set up)
DATA_DIR_ROMS_LEGACY = Path("D:/ChatWithAI")

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
OUTPUT_DIR = PROJECT_ROOT / "output"

# ---------------------------------------------------------------------------
# Quick lookup
# ---------------------------------------------------------------------------
SOURCE_DIRS = {
    "ROMS":  DATA_DIR_ROMS,
    "CMEMS": DATA_DIR_CMEMS,
}


def get_source_dir(source: str) -> Path:
    """Return the configured data directory for a source name.

    Parameters
    ----------
    source : str
        Source name, case-insensitive (e.g. ``"ROMS"``, ``"CMEMS"``).

    Returns
    -------
    Path

    Raises
    ------
    KeyError
        If the source is not configured.
    """
    key = source.upper()
    if key not in SOURCE_DIRS:
        raise KeyError(
            f"Unknown source '{source}'. Known sources: {list(SOURCE_DIRS.keys())}"
        )
    return SOURCE_DIRS[key]
