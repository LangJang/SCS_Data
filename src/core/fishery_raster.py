"""
Rasterize fishery point data onto an oceanographic grid.

Converts a DataFrame of fishery catch records (lat, lon, species,
catch_kg) into 2-D raster layers on the same geographic grid as the
ocean variables.  Points are snapped to the nearest grid cell;
multiple records in the same cell are aggregated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rasterize_fishery(
    df: pd.DataFrame,
    lon_grid: np.ndarray,  # 1-D target longitudes
    lat_grid: np.ndarray,  # 1-D target latitudes
) -> dict[str, np.ndarray]:
    """Rasterize fishery catch records onto a rectilinear grid.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns ``lon``, ``lat``, ``species``, ``catch_kg``.
    lon_grid : np.ndarray, 1-D
        Target longitude coordinates.
    lat_grid : np.ndarray, 1-D
        Target latitude coordinates.

    Returns
    -------
    dict[str, np.ndarray]
        Keys are layer names (``"catch_total"``, ``"n_records"``,
        ``"n_species"``, ``"catch_{species}"``).  Each value is a
        2-D float32 array of shape ``(len(lat_grid), len(lon_grid))``.
        Cells with no data are NaN.
    """
    n_lat, n_lon = len(lat_grid), len(lon_grid)

    # -- Per-cell accumulators --
    catch_total = np.full((n_lat, n_lon), np.nan, dtype=np.float32)
    n_records   = np.zeros((n_lat, n_lon), dtype=np.int32)
    n_species   = np.zeros((n_lat, n_lon), dtype=np.int32)
    species_acc: dict[str, np.ndarray] = {}

    for _, row in df.iterrows():
        lat, lon = row["lat"], row["lon"]
        species = str(row["species"])
        kg = float(row["catch_kg"])

        # Nearest grid cell
        j = int(np.argmin(np.abs(lat_grid - lat)))
        i = int(np.argmin(np.abs(lon_grid - lon)))

        # Total catch
        if np.isnan(catch_total[j, i]):
            catch_total[j, i] = 0.0
        catch_total[j, i] += kg

        n_records[j, i] += 1

        # Species accumulator
        key = _safe_name(species)
        if key not in species_acc:
            species_acc[key] = np.full((n_lat, n_lon), np.nan, dtype=np.float32)
        if np.isnan(species_acc[key][j, i]):
            species_acc[key][j, i] = 0.0
        species_acc[key][j, i] += kg

    # Species count per cell
    for key in species_acc:
        n_species += (~np.isnan(species_acc[key])).astype(np.int32)

    layers = {
        "catch_total": catch_total,
        "n_records":   n_records.astype(np.float32),
        "n_species":   n_species.astype(np.float32),
    }
    for key, arr in species_acc.items():
        layers[f"catch_{key}"] = arr

    return layers


def _safe_name(species: str) -> str:
    """Convert species name to a valid NetCDF-safe variable name."""
    return (
        species.replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .replace("-", "_")
    )
