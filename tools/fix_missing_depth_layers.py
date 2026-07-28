"""
Fix missing 0 m and 400 m depth layers in standardized CMEMS files.

Problem:
    The standardized CMEMS files have 14 depth levels (0–400 m), but the
    shallowest (0 m) and deepest (400 m) layers are 100% NaN.  This is
    because the interpolation pipeline could not extrapolate to depths
    outside the original data range (0.5–5902 m).

Approach:
    1. Load the *original* CMEMS file and extract the depth layer closest
       to each missing target (0.5 m → 0 m, 411.8 m → 400 m).
    2. Spatially interpolate those layers from the original 0.25° grid
       (175 × 118) to the standardized 0.05° grid (872 × 586).
    3. Match time steps between original and standardized (both daily,
       2023-01-01 start; standardized = 365 days, original = 1096 days).
    4. Write the interpolated values back into the standardized NetCDF file
       at depth index 0 (0 m) and depth index -1 (400 m).

Usage:
    cd D:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe tools/fix_missing_depth_layers.py

    # Dry-run (print what would happen, don't modify files):
    D:\PYTHON\envs\scs_marine\python.exe tools/fix_missing_depth_layers.py --dry-run

Files affected:
    D:/ChatWithAI/Downloading_CEMES/output/SCS_cmems_do_chl.nc
    D:/ChatWithAI/Downloading_CEMES/output/SCS_cmems_no3_po4_si.nc
    D:/ChatWithAI/Downloading_CEMES/output/SCS_cmems_ph.nc

Original sources (read-only):
    D:/ChatWithAI/Downloading_CEMES/SCS_BGC_DO_CHL_2025.nc
    D:/ChatWithAI/Downloading_CEMES/SCS_BGC_no3_po4_si_2023-2025.nc
    D:/ChatWithAI/Downloading_CEMES/SCS_BGC_PH_2023-2025.nc
"""

import os
import shutil
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from netCDF4 import Dataset as NC4Dataset
from scipy.interpolate import RegularGridInterpolator


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Target depths in the standardized file
TARGET_DEPTHS_M = [0.0, 400.0]

# Mapping: standardized file → (original file, variable name mapping)
FILE_MAP = {
    "SCS_cmems_do_chl.nc": {
        "original": "SCS_BGC_DO_CHL_2025.nc",
        "var_map": {"o2": "o2", "chl": "chl"},
    },
    "SCS_cmems_no3_po4_si.nc": {
        "original": "SCS_BGC_no3_po4_si_2023-2025.nc",
        "var_map": {"no3": "no3", "po4": "po4", "si": "si"},
    },
    "SCS_cmems_ph.nc": {
        "original": "SCS_BGC_PH_2023-2025.nc",
        "var_map": {"ph": "ph"},
    },
}

BASE = Path("D:/ChatWithAI/Downloading_CEMES")
STD_DIR = BASE / "output"
ORIG_DIR = BASE


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_closest_depth_idx(depth_array: np.ndarray, target_m: float) -> int:
    """Return the index of *depth_array* closest to *target_m*."""
    return int(np.argmin(np.abs(depth_array - target_m)))


def interpolate_layer(
    values_2d: np.ndarray,
    src_lon: np.ndarray,
    src_lat: np.ndarray,
    tgt_lon: np.ndarray,
    tgt_lat: np.ndarray,
) -> np.ndarray:
    """Bilinear interpolation from source grid to target grid.

    Parameters
    ----------
    values_2d : np.ndarray, shape (nlat_src, nlon_src)
    src_lon, src_lat : 1-D arrays of source coordinates
    tgt_lon, tgt_lat : 1-D arrays of target coordinates

    Returns
    -------
    np.ndarray, shape (nlat_tgt, nlon_tgt)
    """
    # RegularGridInterpolator expects (z, y, x) ordering; here y = lat, x = lon
    interp = RegularGridInterpolator(
        (src_lat, src_lon),
        values_2d,
        method="linear",
        bounds_error=False,
        fill_value=np.nan,
    )

    tgt_lon2d, tgt_lat2d = np.meshgrid(tgt_lon, tgt_lat)
    pts = np.column_stack((tgt_lat2d.ravel(), tgt_lon2d.ravel()))
    result = interp(pts).reshape(tgt_lat2d.shape)
    return result.astype(values_2d.dtype)


def fix_one_file(
    std_path: Path,
    orig_path: Path,
    var_map: dict[str, str],
    dry_run: bool = False,
) -> None:
    """Fix missing depth layers in one standardized file.

    Parameters
    ----------
    std_path : Path
        Path to the standardized NetCDF file (will be modified in-place).
    orig_path : Path
        Path to the original (raw) NetCDF file (read-only).
    var_map : dict[str, str]
        Mapping ``{std_varname: orig_varname}``.
    dry_run : bool
        If True, only print what would be done.
    """
    print(f"\n{'='*60}")
    print(f"  {std_path.name}")
    print(f"{'='*60}")

    # Load original (read-only)
    ds_orig = xr.open_dataset(orig_path, engine="netcdf4")
    src_lon = ds_orig.longitude.values.astype(np.float64)
    src_lat = ds_orig.latitude.values.astype(np.float64)
    src_depths = ds_orig.depth.values
    n_t_orig = ds_orig.sizes["time"]

    # Load standardized (read-only, we'll re-open later for writing)
    ds_std = xr.open_dataset(std_path, engine="netcdf4")
    tgt_lon = ds_std.longitude.values.astype(np.float64)
    tgt_lat = ds_std.latitude.values.astype(np.float64)
    std_depths = ds_std.depth.values
    n_t_std = ds_std.sizes["time"]

    print(f"  Time steps: std={n_t_std}, orig={n_t_orig}")

    # ---- Collect interpolated data (keep ds_orig open, read ds_std) ----
    fill_data: dict[str, dict[int, np.ndarray]] = {}  # {var: {depth_idx: array(t, y, x)}}

    for std_var, orig_var in var_map.items():
        print(f"\n  Variable: {std_var} (orig: {orig_var})")
        fill_data[std_var] = {}

        for target_m in TARGET_DEPTHS_M:
            orig_d_idx = find_closest_depth_idx(src_depths, target_m)
            orig_d_m = float(src_depths[orig_d_idx])
            std_d_idx = find_closest_depth_idx(std_depths, target_m)
            std_d_m = float(std_depths[std_d_idx])

            print(f"    Target {target_m:.0f} m:")
            print(f"      Original depth[{orig_d_idx}] = {orig_d_m:.1f} m")
            print(f"      Standard  depth[{std_d_idx}] = {std_d_m:.0f} m")

            if dry_run:
                current = ds_std[std_var].isel(depth=std_d_idx, time=0).values
                n_valid = (~np.isnan(current)).sum()
                print(f"      Current valid cells: {n_valid} / {current.size}")
                continue

            # Process all time steps
            layers = np.empty((n_t_std, len(tgt_lat), len(tgt_lon)), dtype=np.float32)
            for t in range(n_t_std):
                orig_layer = ds_orig[orig_var].isel(
                    depth=orig_d_idx, time=t
                ).values.astype(np.float64)
                layers[t] = interpolate_layer(
                    orig_layer, src_lon, src_lat, tgt_lon, tgt_lat,
                )

            fill_data[std_var][std_d_idx] = layers

            n_valid_after = (~np.isnan(layers[0])).sum()
            print(f"      After fill: {n_valid_after} valid cells "
                  f"({100 * n_valid_after / layers[0].size:.1f}%)")

    ds_std.close()
    ds_orig.close()

    if dry_run:
        return

    # ---- Copy file then patch layers with native netCDF4 (memory-safe) ----
    print(f"\n  Writing {std_path.name} ...")
    tmp_path = std_path.with_suffix(".nc.tmp")
    shutil.copy2(std_path, tmp_path)

    nc = NC4Dataset(str(tmp_path), mode="a")
    for std_var, depth_map in fill_data.items():
        nc_var = nc.variables[std_var]
        for d_idx, layers in depth_map.items():
            for t in range(layers.shape[0]):
                nc_var[t, d_idx, :, :] = layers[t]
    nc.close()

    os.replace(tmp_path, std_path)
    print(f"  Done.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=== DRY RUN — no files will be modified ===\n")

    for std_fname, info in FILE_MAP.items():
        std_path = STD_DIR / std_fname
        orig_path = ORIG_DIR / info["original"]

        if not std_path.exists():
            print(f"[SKIP] {std_fname} — not found at {std_path}")
            continue
        if not orig_path.exists():
            print(f"[SKIP] {std_fname} — original not found at {orig_path}")
            continue

        fix_one_file(std_path, orig_path, info["var_map"], dry_run=dry_run)

    if dry_run:
        print("\n=== Dry run complete. Run without --dry-run to apply. ===")
    else:
        print("\n=== All files fixed. ===")


if __name__ == "__main__":
    main()
