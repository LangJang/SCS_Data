"""
Bilinear-interpolate extracted 0 m / 400 m layers from 0.25° → 0.05°.

Reads the 2-layer extracted files and spatially interpolates each
variable × depth × timestep to the standardized 0.05° grid (872 × 586),
matching the spatial extent of the existing standardized CMEMS files.

Usage:
    cd D:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe tools/interp_to_005deg.py
"""

import sys
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.interpolate import RegularGridInterpolator


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INPUT_DIR = Path("D:/ChatWithAI/Downloading_CEMES/output")

# Extracted 2-layer files (produced by extract_missing_depth_layers.py)
INPUT_FILES = [
    "extracted_0m_400m_do_chl.nc",
    "extracted_0m_400m_SCS_BGC_no3_po4_si.nc",
    "extracted_0m_400m_SCS_BGC_PH.nc",
]

# Reference standardized file — provides the target 0.05° grid
REF_FILE = INPUT_DIR / "SCS_cmems_do_chl.nc"


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- Target grid ----
    ref = xr.open_dataset(REF_FILE, engine="netcdf4")
    tgt_lon = ref.longitude.values.astype(np.float64)
    tgt_lat = ref.latitude.values.astype(np.float64)
    ref.close()

    tgt_lon2d, tgt_lat2d = np.meshgrid(tgt_lon, tgt_lat)
    tgt_pts = np.column_stack((tgt_lat2d.ravel(), tgt_lon2d.ravel()))
    n_lat, n_lon = len(tgt_lat), len(tgt_lon)
    print(f"Target grid: {n_lat} × {n_lon}  ({n_lat * n_lon:,} cells)")

    for fname in INPUT_FILES:
        src_path = INPUT_DIR / fname
        if not src_path.exists():
            print(f"\n[SKIP] {fname} — not found")
            continue

        src = xr.open_dataset(src_path, engine="netcdf4")
        src_lon = src.longitude.values.astype(np.float64)
        src_lat = src.latitude.values.astype(np.float64)
        n_time = src.sizes["time"]
        n_depth = src.sizes["depth"]
        print(
            f"\n{fname}: "
            f"src {src.sizes['latitude']}×{src.sizes['longitude']}  "
            f"{n_depth} layers  {n_time} timesteps"
        )

        # ---- Interpolate each variable ----
        data_vars = {}
        for var_name in src.data_vars:
            da = src[var_name]
            out = np.empty((n_time, n_depth, n_lat, n_lon), dtype=np.float32)

            for d in range(n_depth):
                d_m = float(src.depth.values[d])
                print(f"  {var_name}  depth={d_m:.1f}m ...", end=" ", flush=True)

                for t in range(n_time):
                    interp = RegularGridInterpolator(
                        (src_lat, src_lon),
                        da.values[t, d].astype(np.float64),
                        method="linear",
                        bounds_error=False,
                        fill_value=np.nan,
                    )
                    out[t, d] = (
                        interp(tgt_pts)
                        .reshape(n_lat, n_lon)
                        .astype(np.float32)
                    )

                n_valid = (~np.isnan(out[0, d])).sum()
                print(f"{n_valid:,} valid  "
                      f"({100 * n_valid / out[0, d].size:.1f}%)")

            data_vars[var_name] = (
                ["time", "depth", "latitude", "longitude"],
                out,
            )

        # ---- Save ----
        out_ds = xr.Dataset(
            data_vars=data_vars,
            coords={
                "time": src.time.values,
                "depth": src.depth.values,
                "latitude": tgt_lat,
                "longitude": tgt_lon,
            },
        )

        out_name = fname.replace(".nc", "_005deg.nc")
        out_path = INPUT_DIR / out_name
        print(f"  Saving {out_name} ...", end=" ", flush=True)
        out_ds.to_netcdf(out_path, engine="netcdf4")
        print("Done.")
        src.close()

    print("\nAll files interpolated.")


if __name__ == "__main__":
    main()
