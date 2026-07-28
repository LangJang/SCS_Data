"""
Replace the 0 m and 400 m layers in standardized CMEMS files with
interpolated values from the extracted 0.05° layers.

Mapping:
    extracted_0m_400m_do_chl_005deg.nc          → SCS_cmems_do_chl.nc
    extracted_0m_400m_SCS_BGC_no3_po4_si_005deg.nc → SCS_cmems_no3_po4_si.nc
    extracted_0m_400m_SCS_BGC_PH_005deg.nc      → SCS_cmems_ph.nc

For each variable, the extracted depth[0] replaces std depth[0] (0 m)
and extracted depth[1] replaces std depth[-1] (400 m).

Memory-safe: uses native netCDF4 I/O, one timestep at a time.

Usage:
    cd D:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe tools/merge_depth_layers.py
"""

import os
import shutil
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset as NC4Dataset


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUT_DIR = Path("D:/ChatWithAI/Downloading_CEMES/output")

# (extracted_file, standardized_file, variables)
JOBS = [
    (
        "extracted_0m_400m_do_chl_005deg.nc",
        "SCS_cmems_do_chl.nc",
        ["o2", "chl"],
    ),
    (
        "extracted_0m_400m_SCS_BGC_no3_po4_si_005deg.nc",
        "SCS_cmems_no3_po4_si.nc",
        ["no3", "po4", "si"],
    ),
    (
        "extracted_0m_400m_SCS_BGC_PH_005deg.nc",
        "SCS_cmems_ph.nc",
        ["ph"],
    ),
]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def main() -> None:
    for extracted_name, std_name, var_names in JOBS:
        extracted_path = OUT_DIR / extracted_name
        std_path = OUT_DIR / std_name

        if not extracted_path.exists():
            print(f"[SKIP] {extracted_name} — not found")
            continue
        if not std_path.exists():
            print(f"[SKIP] {std_name} — not found")
            continue

        print(f"\n{'='*60}")
        print(f"  {extracted_name}  →  {std_name}")
        print(f"  Variables: {var_names}")
        print(f"{'='*60}")

        # ---- Copy standardized file to temp ----
        tmp_path = std_path.with_suffix(".nc.tmp")
        print(f"  Copying {std_name} → temp ...", end=" ", flush=True)
        shutil.copy2(std_path, tmp_path)
        print("Done.")

        # ---- Open both files with native netCDF4 ----
        nc_src = NC4Dataset(str(extracted_path), mode="r")
        nc_dst = NC4Dataset(str(tmp_path), mode="a")

        n_time = nc_dst.dimensions["time"].size
        n_depth_src = nc_src.dimensions["depth"].size  # should be 2

        # Map: source depth index → destination depth index
        # depth[0] (≈0.5 m) → std depth[0] (0 m)
        # depth[1] (≈400 m) → std depth[-1] (400 m)
        dst_depth_indices = [0, nc_dst.dimensions["depth"].size - 1]

        for var_name in var_names:
            print(f"\n  Variable: {var_name}")

            src_var = nc_src.variables[var_name]
            dst_var = nc_dst.variables[var_name]

            for sd in range(n_depth_src):
                dd = dst_depth_indices[sd]
                src_depth_m = float(nc_src.variables["depth"][sd])
                dst_depth_m = float(nc_dst.variables["depth"][dd])
                print(f"    src depth[{sd}]={src_depth_m:.1f}m  "
                      f"→  dst depth[{dd}]={dst_depth_m:.0f}m ...",
                      end=" ", flush=True)

                for t in range(n_time):
                    dst_var[t, dd, :, :] = src_var[t, sd, :, :]

                # Verify
                n_valid = (~np.isnan(dst_var[0, dd, :, :])).sum()
                total = dst_var[0, dd].size
                print(f"{n_valid:,} / {total:,} valid  "
                      f"({100 * n_valid / total:.1f}%)")

        nc_src.close()
        nc_dst.close()

        # ---- Replace original with patched copy ----
        print(f"\n  Replacing {std_name} ...", end=" ", flush=True)
        os.replace(tmp_path, std_path)
        print("Done.")

    print(f"\n{'='*60}")
    print("  All files merged.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
