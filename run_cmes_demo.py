"""
CMEMS data demo — surface maps with date in titles, auto-handles all files.

Usage:
    cd d:\ChatWithAI\SCS_data
    set PYTHONIOENCODING=utf-8
    D:\PYTHON\envs\scs_marine\python.exe run_cmes_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from src.core.nc_reader import NCReader
from src.core.roms_utils import extract_field
from src.core.config import DATA_DIR_CMEMS, OUTPUT_DIR
from src.viz.map_plotter import plot_map

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR  = DATA_DIR_CMEMS
OUT_DIR   = OUTPUT_DIR / "cemes_demo"
TIME_IDX  = 0              # first time step (2023-01-01 for all 3 files)
DEPTH_IDX = 0              # surface (depth=0)

# Per-variable colormap (canonical_name → cmap)
CMAPS = {
    "chlorophyll":       "Greens",
    "dissolved_oxygen":  "Blues",
    "ph":                "RdYlBu_r",
    "nitrate":           "YlOrBr",
    "phosphate":         "YlOrRd",
}

reader = NCReader(DATA_DIR)

# ---------------------------------------------------------------------------
# 1. Scan & load
# ---------------------------------------------------------------------------
print("=" * 60)
print("  CMEMS Data Demo")
print("=" * 60)

print(f"\n  Data dir:  {DATA_DIR}")
for _, row in reader.scan_files_with_sizes().iterrows():
    print(f"    {row['name']:<45s} {row['size_mb']:.0f} MB")

reader.load_all()

# ---------------------------------------------------------------------------
# 2. Source detection & metadata
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"  Source Detection & Metadata")
print(f"{'=' * 60}")

for key in reader.datasets:
    try:
        meta = reader.meta(key)
        ds = reader[key]
        t_vals = ds[meta.time_dim].values
        print(f"\n  {key}")
        print(f"    Source:     {meta.source_name}")
        print(f"    Grid:       {meta.grid_type.name}  "
              f"{ds.sizes.get('longitude', '?'):} x {ds.sizes.get('latitude', '?'):}")
        print(f"    Vertical:   {meta.vertical_type.name}  "
              f"{ds.sizes.get('depth', '?'):} levels")
        print(f"    Time:       {len(t_vals)} steps  "
              f"({pd.Timestamp(t_vals[0]).date()} → {pd.Timestamp(t_vals[-1]).date()})")
        print(f"    Variables:  {sorted(meta.available_variables())}")
    except KeyError as e:
        print(f"  {key}  — {e}")

# ---------------------------------------------------------------------------
# 3. Extract & plot — one map per variable per file
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"  Surface Maps  (time_idx={TIME_IDX}, depth_idx={DEPTH_IDX})")
print(f"{'=' * 60}")

OUT_DIR.mkdir(parents=True, exist_ok=True)

for key in reader.datasets:
    try:
        meta = reader.meta(key)
        ds = reader[key]
    except KeyError:
        continue

    t_val = pd.Timestamp(ds[meta.time_dim].values[TIME_IDX])
    depth_val = float(ds[meta.coord_map.get("depth", "depth")].values[DEPTH_IDX])

    for canon_name in sorted(meta.available_variables()):
        da, lon, lat = extract_field(ds, meta, canon_name, TIME_IDX, DEPTH_IDX)

        title = (f"CMEMS Surface {meta.display_label(canon_name)}\n"
                 f"{t_val.date()}  |  depth={depth_val:.1f} m")

        stem = Path(key).stem
        out_path = OUT_DIR / f"{stem}_{canon_name}_{t_val.date()}.png"
        cmap = CMAPS.get(canon_name, "Spectral_r")

        plot_map(da, lon, lat, title=title, cmap=cmap, output_path=out_path)

        v = da.values
        print(f"  {canon_name:<20s}  "
              f"range=[{float(np.nanmin(v)):.4g}, {float(np.nanmax(v)):.4g}]  "
              f"→ {out_path.name}")

print(f"\nDone — {len(list(OUT_DIR.glob('*.png')))} figures saved to {OUT_DIR}/")
