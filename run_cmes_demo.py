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
# Config — change these to control which day and variables are plotted
# ---------------------------------------------------------------------------
DATA_DIR   = DATA_DIR_CMEMS
OUT_DIR    = OUTPUT_DIR / "cemes_demo"
START_DATE = "2023-01-02"  # which day to plot (None = first available)
DEPTH_IDX  = 0             # vertical level: 0=surface, -1=bottom

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
# 3. Resolve time index from START_DATE, then plot
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"  Surface Maps  (depth_idx={DEPTH_IDX})")
print(f"{'=' * 60}")

OUT_DIR.mkdir(parents=True, exist_ok=True)

for key in reader.datasets:
    try:
        meta = reader.meta(key)
        ds = reader[key]
    except KeyError:
        continue

    # Resolve time index from START_DATE
    t_vals = ds[meta.time_dim].values
    if START_DATE is not None:
        target = pd.Timestamp(START_DATE)
        t_ns = t_vals.astype("datetime64[ns]").astype(np.int64)
        target_ns = target.asm8.astype("datetime64[ns]").astype(np.int64)
        time_idx = int(np.argmin(np.abs(t_ns - target_ns)))
    else:
        time_idx = 0

    t_val = pd.Timestamp(t_vals[time_idx])
    depth_val = float(ds[meta.coord_map.get("depth", "depth")].values[DEPTH_IDX])

    print(f"\n  {key}")
    print(f"    Date:  {t_val.date()}")
    print(f"    Depth: {depth_val:.1f} m")

    for canon_name in sorted(meta.available_variables()):
        da, lon, lat = extract_field(ds, meta, canon_name, time_idx, DEPTH_IDX)

        title = (f"CMEMS Surface {meta.display_label(canon_name)}\n"
                 f"{t_val.date()}  |  depth={depth_val:.1f} m")

        stem = Path(key).stem
        date_dir = OUT_DIR / str(t_val.date())
        date_dir.mkdir(parents=True, exist_ok=True)
        out_path = date_dir / f"{stem}_{canon_name}.png"
        cmap = CMAPS.get(canon_name, "Spectral_r")

        plot_map(da, lon, lat, title=title, cmap=cmap, output_path=out_path)

        v = da.values
        print(f"    {canon_name:<20s}  "
              f"range=[{float(np.nanmin(v)):.4g}, {float(np.nanmax(v)):.4g}]  "
              f"→ {out_path.name}")

figs = sorted(OUT_DIR.rglob("*.png"))
print(f"\nDone — {len(figs)} figures saved to {OUT_DIR}/")
for d in sorted(OUT_DIR.glob("*/")):
    n = len(list(d.glob("*.png")))
    print(f"    {d.name}/  ({n} plots)")
