"""
Machine-specific data paths — the single file to edit when data moves.

Every hardcoded absolute path in this project is defined here.  Python
modules import these constants directly; ``config.yaml`` references them
with ``{NAME}`` placeholders that ``config_reader`` substitutes at load.

When you move data or change machines, edit the three roots below and
everything else follows.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Raw absolute roots — edit these when data moves
# ---------------------------------------------------------------------------

# CMEMS / Copernicus Marine download directory
CMEMS_DIR = Path("D:/ChatWithAI/Downloading_CEMES")

# Legacy ROMS directory (used before the project-local data/ was set up)
ROMS_LEGACY_DIR = Path("D:/ChatWithAI")

# South China Sea project directory (the repo root)
SCS_DATA_DIR = Path("D:/ChatWithAI/SCS_data")

# ---------------------------------------------------------------------------
# Derived paths — built from the roots above; usually no need to edit
# ---------------------------------------------------------------------------

CMEMS_OUTPUT_DIR = CMEMS_DIR / "output"
CMEMS_STD_ROMS_DIR = CMEMS_OUTPUT_DIR / "roms"

# ---------------------------------------------------------------------------
# Placeholder map for config.yaml.
#
# In config.yaml write e.g.   path: "{CMEMS_OUTPUT}/roms/"
# and config_reader.py substitutes the real path at load time.
# ---------------------------------------------------------------------------

PATH_ALIASES: dict[str, Path] = {
    "CMEMS_DIR":      CMEMS_DIR,
    "CMEMS_OUTPUT":   CMEMS_OUTPUT_DIR,
    "CMEMS_STD_ROMS": CMEMS_STD_ROMS_DIR,
    "ROMS_LEGACY":    ROMS_LEGACY_DIR,
    "SCS_DATA":       SCS_DATA_DIR,
}


def resolve_path_string(value: str) -> str:
    """Replace ``{NAME}`` placeholders in *value* with their real paths."""
    for name, path in PATH_ALIASES.items():
        value = value.replace("{" + name + "}", str(path))
    return value
