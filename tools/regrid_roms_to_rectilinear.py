"""
Regrid standardized ROMS data from 2-D curvilinear → 1-D rectilinear.

Uses the **exact same grid coordinates** as the standardized CMEMS files
(872 longitudes × 586 latitudes at 0.05°), so ROMS and CMEMS become
pixel-perfect aligned after regridding.

Method: scipy.spatial.cKDTree nearest-neighbor.
Variables on ρ-grid  (temp, salt, w) use lon_rho / lat_rho.
Variables on u-grid  (u)          use lon_u   / lat_u.
Variables on v-grid  (v)          use lon_v   / lat_v.

Output: one merged NetCDF file with all 27 days, 14 depth levels,
        5 variables, on the 586 × 872 rectilinear grid.

Usage:
    cd D:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe tools/regrid_roms_to_rectilinear.py
"""

import sys
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.spatial import cKDTree

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROMS_DIR = Path("D:/ChatWithAI/Downloading_CEMES/output/roms")
CMEMS_REF = Path("D:/ChatWithAI/Downloading_CEMES/output/SCS_cmems_do_chl.nc")
OUT_PATH = ROMS_DIR / "roms_rectilinear_005deg.nc"

# Variables to regrid: (source_name, grid_type)
# grid_type: "rho" → lon_rho/lat_rho,  "u" → lon_u/lat_u,  "v" → lon_v/lat_v
VARIABLES = [
    ("temp", "rho"),
    ("salt", "rho"),
    ("u",    "u"),
    ("v",    "v"),
    ("w",    "rho"),
]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- Load target grid from CMEMS reference ----
    ref = xr.open_dataset(CMEMS_REF, engine="netcdf4")
    tgt_lon = ref.longitude.values.astype(np.float64)
    tgt_lat = ref.latitude.values.astype(np.float64)
    ref.close()

    tgt_lon2d, tgt_lat2d = np.meshgrid(tgt_lon, tgt_lat)
    tgt_pts = np.column_stack((tgt_lon2d.ravel(), tgt_lat2d.ravel()))
    n_lat, n_lon = len(tgt_lat), len(tgt_lon)
    print(f"Target grid: {n_lat} × {n_lon}  ({n_lat * n_lon:,} cells)")
    print(f"Lon: {tgt_lon[0]:.2f} → {tgt_lon[-1]:.2f}")
    print(f"Lat: {tgt_lat[0]:.2f} → {tgt_lat[-1]:.2f}")

    # ---- Discover ROMS files ----
    roms_files = sorted(ROMS_DIR.glob("roms_avg_*.nc"))
    if not roms_files:
        print(f"No ROMS files found in {ROMS_DIR}")
        sys.exit(1)
    print(f"\nROMS files: {len(roms_files)}")

    # ---- Check first file for depth / time structure ----
    first = xr.open_dataset(roms_files[0], engine="netcdf4")
    depth_vals = first.depth.values
    # Filter out fill values (< 0)
    valid_depths = [(i, float(d)) for i, d in enumerate(depth_vals) if float(d) >= 0]
    depth_indices = [i for i, _ in valid_depths]
    depth_meters = [d for _, d in valid_depths]
    n_depth = len(valid_depths)
    n_files = len(roms_files)
    print(f"Depth levels (valid): {n_depth}")
    print(f"Depths: {[f'{d:.0f}' for d in depth_meters]}")
    first.close()

    # ---- Create output file skeleton with native netCDF4 ----
    print(f"\nCreating output file ...", end=" ", flush=True)
    from netCDF4 import Dataset as NC4Dataset

    nc = NC4Dataset(str(OUT_PATH), "w", format="NETCDF4")
    nc.createDimension("time", n_files)
    nc.createDimension("depth", n_depth)
    nc.createDimension("latitude", n_lat)
    nc.createDimension("longitude", n_lon)

    nc_time = nc.createVariable("time", "f8", ("time",))
    nc_time.units = "days since 1900-01-01"
    nc_time.calendar = "gregorian"
    nc_depth = nc.createVariable("depth", "f4", ("depth",))
    nc_depth.units = "m"
    nc_lat = nc.createVariable("latitude", "f8", ("latitude",))
    nc_lat.units = "degrees_north"
    nc_lon = nc.createVariable("longitude", "f8", ("longitude",))
    nc_lon.units = "degrees_east"

    unit_map = {"temp": "Celsius", "salt": "PSU",
                "u": "m s-1", "v": "m s-1", "w": "m s-1"}
    long_name_map = {"temp": "potential temperature", "salt": "salinity",
                     "u": "u-momentum component", "v": "v-momentum component",
                     "w": "vertical momentum component"}

    nc_vars = {}
    for var_name, _ in VARIABLES:
        v = nc.createVariable(var_name, "f4",
                              ("time", "depth", "latitude", "longitude"),
                              zlib=True, complevel=4)
        v.units = unit_map.get(var_name, "")
        v.long_name = long_name_map.get(var_name, var_name)
        nc_vars[var_name] = v

    nc_lat[:] = tgt_lat
    nc_lon[:] = tgt_lon
    nc_depth[:] = np.array(depth_meters, dtype=np.float32)
    print("Done.")

    # ---- Process each file → write immediately ----
    from netCDF4 import date2num

    for fi, fpath in enumerate(roms_files):
        ds = xr.open_dataset(fpath, engine="netcdf4")
        t_val = ds.ocean_time.values[0]
        nc_time[fi] = date2num(
            np.datetime64(t_val, "us").astype(object), nc_time.units,
        )

        date_label = str(t_val)[:10]
        print(f"\n[{fi+1}/{n_files}] {fpath.name}  ({date_label})")

        for var_name, grid in VARIABLES:
            print(f"  {var_name} ({grid} grid) ...", end=" ", flush=True)

            if grid == "rho":
                src_lon = ds.lon_rho.values.astype(np.float64).ravel()
                src_lat = ds.lat_rho.values.astype(np.float64).ravel()
            elif grid == "u":
                src_lon = ds.lon_u.values.astype(np.float64).ravel()
                src_lat = ds.lat_u.values.astype(np.float64).ravel()
            else:  # v
                src_lon = ds.lon_v.values.astype(np.float64).ravel()
                src_lat = ds.lat_v.values.astype(np.float64).ravel()

            src_pts = np.column_stack((src_lon, src_lat))
            tree = cKDTree(src_pts)
            _, indices = tree.query(tgt_pts)
            del tree, src_pts

            for di, src_di in enumerate(depth_indices):
                src_values = ds[var_name].values[0, src_di].ravel()
                nc_vars[var_name][fi, di] = src_values[indices].reshape(
                    n_lat, n_lon,
                )

            n_valid = (~np.isnan(nc_vars[var_name][fi, 0, :, :])).sum()
            print(f"{n_valid:,} valid  "
                  f"({100 * n_valid / (n_lat * n_lon):.1f}%)")

        ds.close()

    nc.close()
    print(f"\nDone.  →  {OUT_PATH}")
    print(f"Shape: {n_files} time × {n_depth} depth × {n_lat} lat × {n_lon} lon")


if __name__ == "__main__":
    main()
