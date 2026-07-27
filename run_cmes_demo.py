"""
CMEMS quick demo — chlorophyll, dissolved oxygen, pH maps.

Usage:
    cd d:\ChatWithAI\SCS_data
    D:\PYTHON\envs\scs_marine\python.exe demo_cemes.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core.nc_reader import NCReader
from src.core.roms_utils import extract_field
from src.core.config import DATA_DIR_CMEMS, OUTPUT_DIR
from src.viz.map_plotter import plot_map

DATA_DIR = DATA_DIR_CMEMS
OUT_DIR  = OUTPUT_DIR / "cemes_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

reader = NCReader(DATA_DIR)

# --- 1. Scan ---
print("=== CMEMS Files ===")
for _, row in reader.scan_files_with_sizes().iterrows():
    print(f"  {row['name']:<40s} {row['size_mb']:.0f} MB")

# --- 2. Load & detect ---
print("\n=== Loading & source detection ===")
reader.load_all()

for key in reader.datasets:
    try:
        meta = reader.meta(key)
        print(f"  {key}")
        print(f"    Source: {meta.source_name}  Grid: {meta.grid_type.name}  Vert: {meta.vertical_type.name}")
        print(f"    Variables: {sorted(meta.available_variables())}")
        print(f"    Time dim: {meta.time_dim}  Depth dim: {meta.coord_map.get('depth', 'N/A')}")
    except KeyError as e:
        print(f"  {key}  — {e}")

# --- 3. Get datasets and metas ---
ds_bgc = reader["SCS_BGC_DO_CHL_2025.nc"]
meta_bgc = reader.meta("SCS_BGC_DO_CHL_2025.nc")

ds_ph = reader["SCS_BGC_PH_2023-2025.nc"]
meta_ph = reader.meta("SCS_BGC_PH_2023-2025.nc")

# --- Quick time/depth inspection ---
for label, ds, meta in [
    ("BGC (DO+CHL)", ds_bgc, meta_bgc),
    ("PH", ds_ph, meta_ph),
]:
    t_name = meta.time_dim
    n_t = ds.sizes[t_name]
    t0 = ds[t_name].values[0]
    t_end = ds[t_name].values[-1]
    print(f"\n  {label}: time={n_t} steps ({t0} → {t_end})")
    d_name = meta.coord_map.get("depth", "depth")
    depths = ds[d_name].values
    print(f"    depth: {len(depths)} levels, [{depths[0]:.1f}, {depths[-1]:.1f}] m")

# --- 4. Extract surface fields (depth_idx=0) ---
print("\n=== Extracting surface fields ===")
time_idx = 0    # first time step
depth_idx = 0   # surface

# Chlorophyll
da_chl, lon, lat = extract_field(ds_bgc, meta_bgc, "chlorophyll", time_idx, depth_idx)
print(f"  chlorophyll: shape={da_chl.shape}, range=[{da_chl.values.min():.4g}, {da_chl.values.max():.4g}]")

# Dissolved oxygen
da_o2, _, _ = extract_field(ds_bgc, meta_bgc, "dissolved_oxygen", time_idx, depth_idx)
print(f"  dissolved_oxygen: shape={da_o2.shape}, range=[{da_o2.values.min():.4g}, {da_o2.values.max():.4g}]")

# pH
da_ph, _, _ = extract_field(ds_ph, meta_ph, "ph", time_idx, depth_idx)
print(f"  ph: shape={da_ph.shape}, range=[{da_ph.values.min():.4g}, {da_ph.values.max():.4g}]")

# --- 5. Plot three maps ---
print("\n=== Plotting ===")

# 5a — Chlorophyll
plot_map(
    da_chl, lon, lat,
    title="CMEMS — Surface Chlorophyll-a\nSouth China Sea, 2025-01",
    cmap="Greens",
    output_path=OUT_DIR / "cemes_chlorophyll_surface.png",
)
print("  → cemes_chlorophyll_surface.png")

# 5b — Dissolved Oxygen
plot_map(
    da_o2, lon, lat,
    title="CMEMS — Surface Dissolved Oxygen\nSouth China Sea, 2025-01",
    cmap="Blues",
    output_path=OUT_DIR / "cemes_dissolved_oxygen_surface.png",
)
print("  → cemes_dissolved_oxygen_surface.png")

# 5c — pH
plot_map(
    da_ph, lon, lat,
    title="CMEMS — Surface pH\nSouth China Sea, 2023-01",
    cmap="RdYlBu_r",
    output_path=OUT_DIR / "cemes_ph_surface.png",
)
print("  → cemes_ph_surface.png")

print(f"\nDone — 3 figures saved to {OUT_DIR}/")
