"""
ROMS daily data demo — multi-timestep maps with dates in titles.

Usage:
    cd d:\ChatWithAI\SCS_data
    set PYTHONIOENCODING=utf-8
    D:\PYTHON\envs\scs_marine\python.exe run_roms_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from src.core.time_assembler import TimeAssembler
from src.core.roms_utils import extract_field
from src.core.config import DATA_DIR_ROMS, OUTPUT_DIR
from src.viz.map_plotter import plot_map

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR  = DATA_DIR_ROMS
OUT_DIR   = OUTPUT_DIR / "roms_demo"
LEVEL_IDX = -1            # surface (s_rho=-1)
N_DAYS    = 3             # how many days to plot (max 27)

# Variables to plot: (canonical_name, colormap)
VARIABLES = [
    ("temperature",          "Spectral_r"),
    ("salinity",             "RdYlBu_r"),
    ("sea_surface_height",   "RdBu_r"),
    ("u_current",            "RdBu_r"),
    ("v_current",            "RdBu_r"),
]

# ---------------------------------------------------------------------------
# 1. Scan & assemble (lazy multi-file → single time series)
# ---------------------------------------------------------------------------
print("=" * 60)
print("  ROMS Daily Data — Multi-Timestep Demo")
print("=" * 60)

assembler = TimeAssembler(DATA_DIR)
assembler.scan()

print(f"\n  Files found:   {assembler.n_files}")
dr = assembler.date_range()
print(f"  Date range:    {dr[0].date()}  →  {dr[1].date()}")
missing = assembler.missing_dates()
if missing:
    print(f"  Missing dates: {', '.join(str(d.date()) for d in missing)}")

# Use a subset for quick demo
if N_DAYS < assembler.n_files:
    print(f"  [DEMO] Using first {N_DAYS} of {assembler.n_files} days")
    dates = assembler.dates[:N_DAYS]
    assembler._file_map = {d: assembler._file_map[d] for d in dates}

ds = assembler.assemble()
meta = assembler.assembled_meta

print(f"\n  Source:     {meta.base_meta.source_name}")
print(f"  Grid:       {meta.base_meta.grid_type.name}  "
      f"{ds.sizes['eta_rho']} x {ds.sizes['xi_rho']}")
print(f"  Vertical:   {meta.base_meta.vertical_type.name}  "
      f"{ds.sizes['s_rho']} layers")
print(f"  Variables:  {sorted(meta.base_meta.available_variables())}")
print(f"  Timesteps:  {meta.n_timesteps}")
print(f"  Dates:      {meta.time_labels}")

# ---------------------------------------------------------------------------
# 2. Generate maps — one per variable per day
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"  Generating maps for {meta.n_timesteps} day(s)")
print(f"{'=' * 60}")

for time_idx in range(meta.n_timesteps):
    date_label = meta.time_labels[time_idx]
    day_dir = OUT_DIR / date_label
    day_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  ── {date_label} ──")

    for canon_name, cmap in VARIABLES:
        if not meta.base_meta.has_variable(canon_name):
            continue

        da, lon, lat = extract_field(
            ds, meta.base_meta, canon_name,
            time_idx=time_idx, level_idx=LEVEL_IDX,
        )

        title = (f"{meta.base_meta.source_name} "
                 f"{meta.base_meta.display_label(canon_name)}\n"
                 f"{date_label} 12:00Z  |  surface layer")

        out_path = day_dir / f"{canon_name}_{date_label}.png"

        plot_map(da, lon, lat, title=title, cmap=cmap, output_path=out_path)

        v = da.values
        print(f"    {canon_name:<22s}  "
              f"range=[{float(np.nanmin(v)):.4g}, {float(np.nanmax(v)):.4g}]  "
              f"→ {out_path.name}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"  SUMMARY")
print(f"{'=' * 60}")

figs = sorted(OUT_DIR.rglob("*.png"))
print(f"  {len(figs)} figures saved to {OUT_DIR}/")
for d in sorted(OUT_DIR.glob("*/")):
    n = len(list(d.glob("*.png")))
    print(f"    {d.name}/  ({n} plots)")

print("\nDone.")
