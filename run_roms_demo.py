"""
Quick demo — exercise all modules against real NC data.

Usage:
    cd d:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core.nc_reader import NCReader
from src.core.roms_utils import extract_field, current_speed, available_fields
from src.viz.map_plotter import plot_map

DATA_DIR = Path("D:/ChatWithAI")
reader = NCReader(DATA_DIR)

# --- 1. Scan & load (auto-detect source) ---
print("=== Files found ===")
for _, row in reader.scan_files_with_sizes().iterrows():
    print(f"  {row['name']:<50s} {row['size_mb']:.1f} MB")

reader.load_all()
print(f"Loaded {len(reader)} dataset(s)")
print(f"Unmatched sources: {reader.unmatched}")

# --- 2. Source metadata ---
key = list(reader.datasets.keys())[0]
meta = reader.meta(key)
print(f"\n=== Source: {meta.source_name} ===")
print(f"  Grid type:    {meta.grid_type.name}")
print(f"  Vertical:     {meta.vertical_type.name}")
print(f"  Variables:    {meta.available_variables()}")
print(f"  Coord map:    {meta.coord_map}")

# --- 3. Available canonical fields ---
print(f"\n=== Canonical fields ===")
for canon, label in available_fields(meta).items():
    print(f"  {canon:<30s} {label}")

# --- 4. Extract fields via canonical names ---
ds = reader[key]
print(f"\n=== Field extraction (canonical) ===")
for canon in ["sea_surface_height", "temperature", "salinity",
              "u_current", "v_current", "u_barotropic", "v_barotropic"]:
    if meta.has_variable(canon):
        da, lon, lat = extract_field(ds, meta, canon, time_idx=0, level_idx=36)
        print(f"  {canon:<25s} shape={da.shape}, range=[{da.values.min():.4g}, {da.values.max():.4g}]")

# --- 5. Current speed (source-aware) ---
if meta.has_variable("u_current") and meta.has_variable("v_current"):
    speed, lon_s, lat_s = current_speed(ds, meta, time_idx=0, level_idx=36)
    print(f"\nCurrent speed: shape={speed.shape}, range=[{speed.min():.4g}, {speed.max():.4g}]")

# --- 6. Plot one map ---
if meta.has_variable("temperature"):
    print(f"\n=== Plotting temperature map ===")
    da, lon, lat = extract_field(ds, meta, "temperature", time_idx=0, level_idx=36)
    plot_map(
        da, lon, lat,
        title=f"{meta.source_name} Temperature — Surface Layer",
        cmap="Spectral_r",
        output_path=Path("output/demo_temp_surface.png"),
    )
    print("  → output/demo_temp_surface.png")

# --- 7. Batch snapshots ---
print(f"\n=== Batch snapshot (all fields) ===")
from src.core.roms_utils import snapshot_all_fields
saved = snapshot_all_fields(ds, meta, Path("output"), time_idx=0, level_idx=36)
print(f"\nSaved {len(saved)} figures to output/")

print("\nDone — everything works!")
