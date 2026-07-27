"""
Quick demo — exercise the project modules against real NC data.

Usage:
    cd d:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe demo.py
"""

import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core.nc_reader import NCReader, group_by_product, product_label
from src.core.roms_utils import extract_field, current_speed
from src.viz.map_plotter import plot_map

# --- 1. Scan & load ---
DATA_DIR = Path("D:/ChatWithAI")
reader = NCReader(DATA_DIR)

print("=== Files found ===")
for _, row in reader.scan_files_with_sizes().iterrows():
    print(f"  {row['name']:<50s} {row['size_mb']:.1f} MB")

reader.load_all()
print(f"\nLoaded {len(reader)} dataset(s)")

# --- 2. Inspect one dataset ---
key = list(reader.datasets.keys())[0]
print(f"\n=== Inspect: {key} ===")
print(reader.inspect(key))

# --- 3. Product grouping ---
print(f"\n=== Product groups ===")
for k, flist in reader.product_groups().items():
    print(f"  {k} ({product_label(k)}): {len(flist)} file(s)")

# --- 4. ROMS: extract one field ---
ds = reader[key]
print(f"\n=== ROMS field extraction ===")
print(f"Variables in dataset: {list(ds.data_vars.keys())}")

# Try a few ROMS fields that exist in the dataset
for varname in ["zeta", "temp", "salt", "u", "v"]:
    if varname in ds.data_vars:
        da, lon, lat = extract_field(ds, varname, time_idx=0, s_idx=36)
        print(f"  {varname}: shape={da.shape}, range=[{da.values.min():.4g}, {da.values.max():.4g}]")

# --- 5. ROMS: current speed ---
if "u" in ds.data_vars and "v" in ds.data_vars:
    speed, lon_rho, lat_rho = current_speed(ds, time_idx=0, s_idx=36)
    print(f"\nCurrent speed: shape={speed.shape}, range=[{speed.min():.4g}, {speed.max():.4g}]")

# --- 6. Plot one map ---
print(f"\n=== Plotting test map ===")
da, lon, lat = extract_field(ds, "temp", time_idx=0, s_idx=36)
plot_map(
    da, lon, lat,
    title="ROMS Temperature — Surface Layer",
    cmap="Spectral_r",
    output_path=Path("output/demo_temp_surface.png"),
)
print("  → output/demo_temp_surface.png")

# --- 7. Batch snapshot ---
print(f"\n=== Batch snapshot (3 fields) ===")
from src.core.roms_utils import snapshot_all_fields
saved = snapshot_all_fields(ds, Path("output"), time_idx=0, s_idx=36)
print(f"\nSaved {len(saved)} figures to output/")

print("\nDone — everything works!")
